from fastapi import FastAPI
from typing import Annotated, List, Optional
from fastapi import FastAPI, File, UploadFile
from io import BytesIO
from pypdf import PdfReader
import re
import logging
from langchain_text_splitters import RecursiveCharacterTextSplitter
from supabase import create_client, Client
import os
from dotenv import load_dotenv
from openai import OpenAI
from pydantic import BaseModel
import pydantic
import json
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
import asyncio
import uuid
import tiktoken

load_dotenv()
app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

url: str = os.environ.get("SUPABASE_URL")
key: str = os.environ.get("SUPABASE_SERVICE_KEY")
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")
if url:
    print(url)
supabase: Client = create_client(url, key)
client = OpenAI(api_key=OPENAI_API_KEY)

# Tokenizer for context window management
tokenizer = tiktoken.get_encoding("cl100k_base")

TOKEN_LIMIT = 2000
TOKEN_SUMMARIZE_THRESHOLD = 1950


# ─────────────────────────────────────────────
# Pydantic models
# ─────────────────────────────────────────────


class GetFile(BaseModel):
    file: UploadFile = (File(...),)
    folder_id: Optional[str] = None


class UserQuery(BaseModel):
    file_ids: List[str]
    user_query: str
    session_id: Optional[str] = None


class CitationEvidence(BaseModel):
    extracted_specific_citation: str
    chunk_id: str
    page_no: int
    doc_name: Optional[str] = None


class AIResponse(BaseModel):
    direct_answer: str
    supporting_and_evidence: List[CitationEvidence]


# ─────────────────────────────────────────────
# Token helpers
# ─────────────────────────────────────────────


def count_tokens(text: str) -> int:
    return len(tokenizer.encode(text))


def messages_to_text(messages: list[dict]) -> str:
    """Flatten message list to a single string for token counting."""
    parts = []
    for m in messages:
        role = m.get("message_source", "unknown")
        content = m.get("content", "")
        parts.append(f"{role}: {content}")
    return "\n".join(parts)


def trim_messages_to_token_limit(messages: list[dict], limit: int) -> list[dict]:
    """
    Keep the most recent messages that fit within `limit` tokens.
    Messages are assumed to be in descending order (newest first from Supabase).
    We reverse, trim from the front, then return in chronological order.
    """
    chronological = list(reversed(messages))
    while chronological:
        text = messages_to_text(chronological)
        if count_tokens(text) <= limit:
            break
        chronological.pop(0)  # drop oldest
    return chronological


def summarize_history(messages: list[dict], session_id: str) -> str:
    """
    Ask the AI to summarize the conversation history and persist it to the session.
    Returns the generated summary string.
    """
    history_text = messages_to_text(messages)
    summary_response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {
                "role": "system",
                "content": (
                    "You are a concise summarizer. "
                    "Summarize the following conversation history into a compact paragraph "
                    "that captures the key topics discussed, questions asked, and answers given. "
                    "Be specific, not generic."
                ),
            },
            {"role": "user", "content": history_text},
        ],
        max_tokens=400,
    )
    summary = summary_response.choices[0].message.content.strip()

    # Persist summary to session table
    supabase.table("session").update({"context_summary": summary}).eq(
        "id", session_id
    ).execute()

    return summary


# ─────────────────────────────────────────────
# Chunking & embedding helpers (unchanged)
# ─────────────────────────────────────────────


def chunking(pages: List[dict]):
    print("received text")
    text_splitter = RecursiveCharacterTextSplitter.from_tiktoken_encoder(
        encoding_name="cl100k_base",
        chunk_size=512,
        chunk_overlap=20,
        separators=["\n\n", "\n", ". ", " ", ""],
    )
    all_chunks = []
    for page in pages:
        chunks = text_splitter.create_documents(
            [page["chunk_content"]], metadatas=[{"page_no": page["page_no"]}]
        )
        for chunk in chunks:
            all_chunks.append(
                {"content": chunk.page_content, "page_no": chunk.metadata["page_no"]}
            )

    return all_chunks


async def store_embeddings(all_chunks, document_id):
    results = {"success": 0, "failed": 0, "errors": []}

    for chunk in all_chunks:
        try:
            embed_chunk = client.embeddings.create(
                model="text-embedding-3-small",
                input=chunk["content"],
            )
            vector = embed_chunk.data[0].embedding

            data = {
                "document_id": document_id,
                "chunk_content": chunk["content"],
                "page_no": chunk["page_no"],
                "embedding": vector,
            }

            supabase.table("chunks_and_embeddings").insert(data).execute()
            results["success"] += 1

        except Exception as error:
            results["failed"] += 1
            results["errors"].append({"page_no": chunk["page_no"], "error": str(error)})
            print(f"Error storing chunk for page {chunk['page_no']}: {error}")

    if results["failed"] == 0:
        results["message"] = "All chunks stored successfully"
    else:
        results["message"] = (
            f"{results['success']} chunks stored successfully, {results['failed']} failed ❌"
        )

    return results


def store_to_bucket(path, file, content_type):
    try:
        store_response = supabase.storage.from_("research_pdf_files").upload(
            path=path, file=file, file_options={"content_type": content_type}
        )
        return store_response
    except Exception as error:
        print(f"Storage upload error: {error}")
        raise


def store_file(filename, filepath, folder_id, mime_type):
    try:
        store_response = (
            supabase.table("documents")
            .insert(
                {
                    "folder_id": folder_id,
                    "doc_name": filename,
                    "file_path": filepath,
                    "mime_type": mime_type,
                }
            )
            .execute()
        )

        return store_response.data[0]["id"]
    except Exception as error:
        print(f"Error: {error}")


def create_folder(name: str = None, session_id: str = None):
    print("create_folder called with session_id:", session_id)

    # If session already has a folder, reuse it
    if session_id:
        existing = (
            supabase.table("folder")
            .select("id")
            .eq("session_id", session_id)
            .limit(1)
            .execute()
        )
        if existing.data:
            print("Reusing existing folder:", existing.data[0]["id"])
            return existing.data[0]["id"]

    # Otherwise create a new one
    store_response = (
        supabase.table("folder")
        .insert(
            {
                "folder_name": name if name else "New Session",
                "session_id": session_id,
            }
        )
        .execute()
    )

    if store_response:
        return store_response.data[0]["id"]
    else:
        return "Error in storing folder"


def fetch_from_private_bucket(path):
    fetch_response = supabase.storage.from_("research_pdf_files").download(path)
    return fetch_response


def fetch_from_public_bucket(path):
    fetch_response = supabase.storage.from_("research_pdf_files").get_public_url(path)
    return fetch_response


def read_pdf(contents):
    pdf_file = BytesIO(contents)
    reader = PdfReader(pdf_file)
    all_chunks = []
    for i, page in enumerate(reader.pages, start=1):
        text = page.extract_text()
        if text:
            all_chunks.append({"page_no": i, "chunk_content": text})
    return all_chunks


def get_embeddings(query: str, document_ids: List[str], match_count: int = 5):
    print("=== GET EMBEDDINGS ===")
    print("document_ids:", document_ids)
    print("query:", query)
    embed_query = client.embeddings.create(
        model="text-embedding-3-small",
        input=query,
    )
    print("Document IDs received:", document_ids)

    embed_response = supabase.rpc(
        "hybrid_search",
        {
            "document_ids": document_ids,
            "query_text": query,
            "query_embedding": embed_query.data[0].embedding,
            "match_count": match_count,
        },
    ).execute()

    # Build a doc_id → doc_name lookup so citations can show the filename
    unique_doc_ids = list(
        {row["document_id"] for row in embed_response.data if "document_id" in row}
    )
    doc_name_map: dict[str, str] = {}
    if unique_doc_ids:
        docs = (
            supabase.table("documents")
            .select("id, doc_name")
            .in_("id", unique_doc_ids)
            .execute()
        )
        doc_name_map = {d["id"]: d["doc_name"] for d in docs.data}

    output = []
    for row in embed_response.data:
        doc_id = row.get("document_id")
        output.append(
            {
                "id": row["id"],
                "chunk_content": row["chunk_content"],
                "page_no": row["page_no"],
                "document_id": doc_id,
                "doc_name": doc_name_map.get(doc_id, "Unknown file"),
            }
        )

    return output


# ─────────────────────────────────────────────
# Agent-based ask_ai (replaces old ask_ai)
# ─────────────────────────────────────────────

# Tool definition for the OpenAI tool-calling API
SEARCH_TOOL = {
    "type": "function",
    "function": {
        "name": "search_documents",
        "description": (
            "Search the user's uploaded research documents using a semantic + keyword hybrid search. "
            "Use this when the question is answerable from document content. "
            "Returns relevant text chunks with their chunk IDs and page numbers."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "search_query": {
                    "type": "string",
                    "description": (
                        "A focused search query optimised for retrieval. "
                        "Should target the specific fact or concept needed."
                    ),
                }
            },
            "required": ["search_query"],
        },
    },
}


def ask_ai(
    user_query: str,
    document_ids: List[str],
    conversation_history: list[dict],
    context_summary: Optional[str],
) -> AIResponse:
    """
    Agent loop:
      1. Evaluate the query (relevant / irrelevant / needs clarification).
      2. If relevant, call search_documents (up to MAX_TOOL_CALLS times).
      3. Synthesise a structured AIResponse.
    """
    MAX_TOOL_CALLS = 2

    # ── Build conversation history block ──────────────────────────────────
    history_block = ""
    if context_summary:
        history_block += f"[Conversation summary so far]\n{context_summary}\n\n"
    if conversation_history:
        history_block += "[Recent conversation]\n"
        for m in conversation_history:
            role = "User" if m["message_source"] == "user" else "Assistant"
            # AI messages are stored as JSON; surface only direct_answer for readability
            content = m["content"]
            try:
                parsed = json.loads(content)
                content = parsed.get("direct_answer", content)
            except Exception:
                pass
            history_block += f"{role}: {content}\n"
        history_block += "\n"

    system_prompt = f"""You are a precise research assistant with access to a document search tool.

    {history_block}## Your workflow

    ### Step 1 — Query analysis
    Before doing anything else, decide:
    - RELEVANT: The question can plausibly be answered from research documents.
    → This includes general questions like "what is this about?", "summarize this", 
        "what is this letter for?", "who wrote this?" — always attempt a search first.
    → When in doubt, ALWAYS default to RELEVANT and search.
    - IRRELEVANT: The question is clearly unrelated to documents (e.g. "What's the weather?", 
    "Tell me a joke", "What's 1+1"). Only use this for obviously off-topic questions.
    → Return immediately with a polite message explaining this.
    - NEEDS_CLARIFICATION: Only use this if there are multiple loaded documents and the question 
    is truly ambiguous about which one (e.g. "what is page 5?"). 
    → Never use this for general questions about document content.

    ### Step 2 — Search (max {MAX_TOOL_CALLS} calls)
    Call `search_documents` with a focused query. For general questions like "what is this about"
    or "what is this letter for", search using keywords from the document type or topic.
    You may refine and call again once if the first results are insufficient.

    ### Step 3 — Answer
    Using only the retrieved chunks, give a direct, specific answer with citations.
    Never fabricate information not present in the chunks.
    Never give generic answers like "the document discusses this topic."
    Always be specific — quote names, dates, amounts, and key facts from the chunks.

    ## Output format
    Always respond with a JSON object:
    {{
    "direct_answer": "<specific answer based on chunks>",
    "supporting_and_evidence": [
        {{
        "extracted_specific_citation": "<exact phrase from chunk>",
        "chunk_id": "<chunk id>",
        "page_no": <page number>,
        "doc_name": "<file name from chunk metadata>"
        }}
    ]
    }}
    If truly irrelevant or needs clarification, supporting_and_evidence should be an empty list.
    """

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_query},
    ]

    tool_calls_made = 0
    accumulated_chunks: List[dict] = []

    # ── Agent loop ────────────────────────────────────────────────────────
    while True:
        for i, msg in enumerate(messages):
            if hasattr(msg, "tool_calls") and msg.tool_calls:
                # Check if all tool_call_ids have a corresponding tool response
                tool_ids = {tc.id for tc in msg.tool_calls}
                responded_ids = {
                    m.get("tool_call_id")
                    for m in messages[i + 1 :]
                    if isinstance(m, dict) and m.get("role") == "tool"
                }
                missing = tool_ids - responded_ids
                if missing:
                    print(
                        f"[Agent] Found orphaned tool calls: {missing}, injecting empty responses"
                    )
                    for missing_id in missing:
                        messages.append(
                            {
                                "role": "tool",
                                "tool_call_id": missing_id,
                                "content": "No result available.",
                            }
                        )

        under_cap = tool_calls_made < MAX_TOOL_CALLS

        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=messages,
            tools=[SEARCH_TOOL] if under_cap else None,
            tool_choice="auto" if under_cap else None,
        )

        choice = response.choices[0]

        # ── Tool call branch ──────────────────────────────────────────────
        if choice.finish_reason == "tool_calls":
            tool_call = choice.message.tool_calls[0]
            args = json.loads(tool_call.function.arguments)
            search_query = args.get("search_query", user_query)

            print(
                f"[Agent] Tool call #{tool_calls_made + 1}: search_documents('{search_query}')"
            )

            # Append the assistant message FIRST — before any work that could
            # throw. This guarantees tool_call_id always has a paired response.
            messages.append(choice.message)

            try:
                chunks = get_embeddings(search_query, document_ids)
                accumulated_chunks.extend(chunks)
                tool_result = (
                    "\n\n".join(
                        [
                            f"[Chunk ID: {c['id']} | Page: {c['page_no']} | File: {c.get('doc_name', 'Unknown')}]\n{c['chunk_content']}"
                            for c in chunks
                        ]
                    )
                    or "No relevant chunks found."
                )
            except Exception as e:
                print(f"[Agent] search failed: {e}")
                tool_result = "Search failed. No chunks retrieved."
                chunks = []

            tool_calls_made += 1

            # Always append the tool result — even on error — so the
            # message history stays valid and OpenAI never sees an
            # orphaned tool_call_id.
            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": tool_call.id,
                    "content": tool_result,
                }
            )

            # Once the cap is hit, tell the model to wrap up.
            if tool_calls_made >= MAX_TOOL_CALLS:
                messages.append(
                    {
                        "role": "user",
                        "content": (
                            "You have used all available search calls. "
                            "Using only the chunks retrieved so far, provide your final answer "
                            "in the required JSON format."
                        ),
                    }
                )

            continue

        # ── Final answer branch ───────────────────────────────────────────
        raw_text = choice.message.content or ""

        # Strip markdown fences if present
        clean = raw_text.strip()
        if clean.startswith("```"):
            clean = re.sub(r"^```[a-z]*\n?", "", clean)
            clean = re.sub(r"\n?```$", "", clean)
            clean = clean.strip()

        try:
            parsed = json.loads(clean)
            return AIResponse(**parsed)
        except Exception as e:
            print(
                f"[Agent] Failed to parse final response as AIResponse: {e}\nRaw: {raw_text}"
            )
            # Graceful fallback
            return AIResponse(
                direct_answer=raw_text,
                supporting_and_evidence=[],
            )


# ─────────────────────────────────────────────
# Session helpers
# ─────────────────────────────────────────────


def check_create_session(session_id):
    if session_id is None:
        new_session = supabase.table("session").insert({}).execute()
        return {"session": new_session.data[0], "messages": [], "context_summary": None}

    check_session = supabase.table("session").select("*").eq("id", session_id).execute()

    if not check_session.data:
        new_session = supabase.table("session").insert({}).execute()
        return {"session": new_session.data[0], "messages": [], "context_summary": None}

    session_row = check_session.data[0]
    context_summary = session_row.get("context_summary")

    # Fetch messages descending (newest first)
    messages = (
        supabase.table("messages")
        .select("*")
        .eq("session_id", session_id)
        .order("created_at", desc=True)
        .execute()
    )

    return {
        "session": session_row,
        "messages": messages.data,
        "context_summary": context_summary,
    }


def prepare_history_and_maybe_summarize(
    messages_desc: list[dict],
    session_id: str,
    context_summary: Optional[str],
) -> tuple[list[dict], Optional[str]]:
    """
    1. Reverse to chronological order.
    2. Count tokens of the full history (+ existing summary).
    3. If over threshold: summarise + update DB, clear raw history for prompt.
    4. Otherwise: trim to TOKEN_LIMIT.
    Returns (trimmed_chronological_messages, effective_summary).
    """
    chronological = list(reversed(messages_desc))

    # Build full text for token counting
    full_text = (context_summary or "") + "\n" + messages_to_text(chronological)
    total_tokens = count_tokens(full_text)

    print(f"[Context] Total history tokens: {total_tokens}")

    if total_tokens >= TOKEN_SUMMARIZE_THRESHOLD:
        print("[Context] Threshold reached — summarising history...")
        new_summary = summarize_history(chronological, session_id)
        # After summarising, we pass an empty recent history and the new summary
        return [], new_summary

    # Otherwise trim to TOKEN_LIMIT from the oldest end
    trimmed = trim_messages_to_token_limit(chronological, TOKEN_LIMIT)
    return trimmed, context_summary


# ─────────────────────────────────────────────
# Routes
# ─────────────────────────────────────────────


@app.get("/")
async def root():
    return {"message": "Hello World"}


@app.post("/testfile")
async def analyze_file(file: UploadFile = File(...)):
    return {
        "file_name": file.filename,
        "file_type": file.content_type,
        "file_headers": file.headers,
        "file_size": file.size,
        "file": file.file,
    }


@app.get("/getFile")
async def get_file(file_path: str):
    response = fetch_from_private_bucket(file_path)
    return {"file_download_info": response}


@app.post("/uploadfile")
async def read_file(file: UploadFile = File(...), session_id: Optional[str] = None):
    print("=== UPLOAD CALLED ===")
    print("session_id received:", session_id)
    print("file:", file.filename)
    contents = await file.read()

    folder_id = create_folder(session_id=session_id)

    unique_path = f"{uuid.uuid4()}_{file.filename}"

    store_file_to_bucket = store_to_bucket(unique_path, contents, file.content_type)
    store_file_to_table = store_file(
        file.filename, store_file_to_bucket.path, folder_id, file.content_type
    )

    return {"file_id": store_file_to_table, "folder_id": folder_id}


@app.post("/process_file")
async def process_file(file_id: str):
    file_info = supabase.table("documents").select("*").eq("id", file_id).execute()

    if not file_info.data:
        return {"message": "File does not exist"}

    file = fetch_from_private_bucket(file_info.data[0]["file_path"])
    organize_file = read_pdf(file)
    chunk_file = chunking(organize_file)
    embed_and_store = await store_embeddings(chunk_file, file_id)
    return {"message": embed_and_store}


@app.get("/sessions")
async def get_sessions():
    sessions = (
        supabase.table("session").select("*").order("created_at", desc=True).execute()
    )
    return sessions.data


@app.get("/sessions/{session_id}/messages")
async def get_session_messages(session_id: str):
    messages = (
        supabase.table("messages")
        .select("*")
        .eq("session_id", session_id)
        .order("created_at", desc=True)
        .execute()
    )
    return messages.data


@app.post("/conversation")
async def conversation(request: UserQuery):
    # ── Session & history ──────────────────────────────────────────────────
    get_session = check_create_session(request.session_id)
    session_id = get_session["session"]["id"]
    raw_messages = get_session["messages"]  # newest-first from DB
    context_summary = get_session["context_summary"]

    trimmed_history, effective_summary = prepare_history_and_maybe_summarize(
        raw_messages, session_id, context_summary
    )

    # ── Agent call ─────────────────────────────────────────────────────────
    ai_response = ask_ai(
        user_query=request.user_query,
        document_ids=request.file_ids,
        conversation_history=trimmed_history,
        context_summary=effective_summary,
    )

    # ── Persist messages ───────────────────────────────────────────────────
    supabase.table("messages").insert(
        {
            "session_id": session_id,
            "message_source": "user",
            "content": request.user_query,
        }
    ).execute()

    supabase.table("messages").insert(
        {
            "session_id": session_id,
            "message_source": "ai",
            "content": json.dumps(ai_response.model_dump()),
        }
    ).execute()

    return {**ai_response.model_dump(), "session_id": session_id}


@app.post("/conversation/stream")
async def conversation_stream(request: UserQuery):
    print("=== STREAM REQUEST ===")
    print("file_ids received:", request.file_ids)
    print("session_id received:", request.session_id)
    print("user_query:", request.user_query)
    # ── Session & history ──────────────────────────────────────────────────
    get_session = check_create_session(request.session_id)
    session_id = get_session["session"]["id"]
    raw_messages = get_session["messages"]
    context_summary = get_session["context_summary"]

    trimmed_history, effective_summary = prepare_history_and_maybe_summarize(
        raw_messages, session_id, context_summary
    )

    # Build history block (same logic as ask_ai, but reused here for streaming prompt)
    history_block = ""
    if effective_summary:
        history_block += f"[Conversation summary so far]\n{effective_summary}\n\n"
    if trimmed_history:
        history_block += "[Recent conversation]\n"
        for m in trimmed_history:
            role = "User" if m["message_source"] == "user" else "Assistant"
            content = m["content"]
            try:
                parsed = json.loads(content)
                content = parsed.get("direct_answer", content)
            except Exception:
                pass
            history_block += f"{role}: {content}\n"
        history_block += "\n"

    # ── Store user message ─────────────────────────────────────────────────
    supabase.table("messages").insert(
        {
            "session_id": session_id,
            "message_source": "user",
            "content": request.user_query,
        }
    ).execute()

    async def generate():
        yield f"data: {json.dumps({'type': 'session', 'session_id': session_id})}\n\n"

        loop = asyncio.get_event_loop()

        # Run agent (sync) in executor to avoid blocking
        ai_response: AIResponse = await loop.run_in_executor(
            None,
            lambda: ask_ai(
                user_query=request.user_query,
                document_ids=request.file_ids,
                conversation_history=trimmed_history,
                context_summary=effective_summary,
            ),
        )

        # Stream the direct_answer token by token (character level for simplicity)
        answer = ai_response.direct_answer
        chunk_size = 4  # stream in small bursts
        for i in range(0, len(answer), chunk_size):
            token = answer[i : i + chunk_size]
            yield f"data: {json.dumps({'type': 'token', 'value': token})}\n\n"
            await asyncio.sleep(0.03)

        # Send structured data
        yield f"data: {json.dumps({'type': 'structured', 'data': ai_response.model_dump()})}\n\n"
        yield f"data: {json.dumps({'type': 'done'})}\n\n"

        # Persist AI message
        supabase.table("messages").insert(
            {
                "session_id": session_id,
                "message_source": "ai",
                "content": json.dumps(ai_response.model_dump()),
            }
        ).execute()

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


@app.get("/sessions/{session_id}/files")
async def get_session_files(session_id: str):
    folder = (
        supabase.table("folder").select("id").eq("session_id", session_id).execute()
    )

    if not folder.data:
        return []

    folder_ids = [f["id"] for f in folder.data]

    docs = (
        supabase.table("documents")
        .select("id, doc_name")
        .in_("folder_id", folder_ids)
        .execute()
    )

    return docs.data


@app.post("/conversation/init")
async def init_conversation():
    new_session = supabase.table("session").insert({}).execute()
    return {"session_id": new_session.data[0]["id"]}
