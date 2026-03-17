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
import funkybob
import json
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
import asyncio
import uuid

load_dotenv()
app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],  # your Next.js URL
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


class AIResponse(BaseModel):
    direct_answer: str
    supporting_and_evidence: List[CitationEvidence]


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
            # Create embedding
            embed_chunk = client.embeddings.create(
                model="text-embedding-3-small",
                input=chunk["content"],  # use attribute, not ["page_content"]
            )
            vector = embed_chunk.data[0].embedding

            # Prepare data to store in Supabase
            data = {
                "document_id": document_id,
                "chunk_content": chunk["content"],
                "page_no": chunk["page_no"],
                "embedding": vector,
            }

            # Insert into Supabase
            supabase.table("chunks_and_embeddings").insert(data).execute()
            results["success"] += 1

        except Exception as error:
            results["failed"] += 1
            results["errors"].append({"page_no": chunk["page_no"], "error": str(error)})
            print(f"Error storing chunk for page {chunk["page_no"]}: {error}")

    # Return a summary
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
        raise  # 👈 re-raise so the endpoint knows something went wrong


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
    # returns bytes, must be converted into ByteIO if it were to be passed into pydf
    fetch_response = supabase.storage.from_("research_pdf_files").download(path)

    return fetch_response


def fetch_from_public_bucket(path):
    fetch_response = supabase.storage.from_("research_pdf_files").get_public_url(path)

    return fetch_response


def read_pdf(contents):
    # converts bytes into pypdf readable format
    pdf_file = BytesIO(contents)
    reader = PdfReader(pdf_file)
    all_chunks = []
    for i, page in enumerate(reader.pages, start=1):
        text = page.extract_text()
        if text:
            all_chunks.append({"page_no": i, "chunk_content": text})
    return all_chunks


def read_text(file):
    with open(file) as f:
        open_file = f.read()


def get_embeddings(query: str, document_ids: List[str], match_count: int = 5):

    embed_query = client.embeddings.create(
        model="text-embedding-3-small",
        input=query,  # use attribute, not ["page_content"]
    )
    print("Document IDs received:", document_ids)
    print("Document IDs types:", [type(id) for id in document_ids])

    # Check what's actually in the DB
    check = supabase.table("documents").select("id").in_("id", document_ids).execute()
    print("Matching DB records:", check.data)
    output = []
    embed_response = supabase.rpc(
        "hybrid_search",
        {
            "document_ids": document_ids,
            "query_text": query,
            "query_embedding": embed_query.data[0].embedding,
            "match_count": match_count,
        },
    ).execute()
    # print("EMBEDDING RESPONSE: ", embed_response)
    for row in embed_response.data:
        output.append(
            {
                "id": row["id"],
                "chunk_content": row["chunk_content"],
                "page_no": row["page_no"],
            }
        )

    return output


def ask_ai(user_query: str, chunks: List[dict]) -> AIResponse:
    # Format chunks for the prompt

    formatted_chunks = "\n\n".join(
        [
            f"[Chunk ID: {c['id']} | Page: {c['page_no']}]\n{c['chunk_content']}"
            for c in chunks
        ]
    )

    system_prompt = """You are a precise research assistant analyzing document chunks.

Rules:
1. Read all provided chunks carefully before answering.
2. Answer the user's question directly and specifically using the chunk content.
3. Quote or reference specific details, names, dates, and facts from the chunks.
4. If the chunks genuinely do not contain relevant information, say exactly what topic the chunks DO cover instead of giving a vague non-answer.
5. Never give generic or vague answers like "the document describes the topic" — always be specific.
6. Do not use outside knowledge, but do use your reasoning to connect information within the chunks."""

    user_prompt = f"""User Query: {user_query}

Retrieved Chunks:
{formatted_chunks}

Respond with a JSON object matching this structure:
{{
  "direct_answer": "<your answer strictly based on chunks, or a message that no relevant info was found>",
  "supporting_and_evidence": [
    {{
      "extracted_specific_citation": "<exact sentence or phrase from the chunk>",
      "chunk_id": "<the chunk_id it came from>"
      "page_no": <the page number from the chunk metadata>
    }}
  ]
}}"""

    response = client.beta.chat.completions.parse(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        response_format=AIResponse,
    )

    return response.choices[0].message.parsed


def check_create_session(session_id):
    if session_id is None:
        # Create a new session
        new_session = supabase.table("session").insert({}).execute()
        return {"session": new_session.data[0], "messages": []}

    # Check if session exists
    check_session = supabase.table("session").select("*").eq("id", session_id).execute()

    if not check_session.data:
        # Session not found, create a new one
        new_session = supabase.table("session").insert({}).execute()
        return {"session": new_session.data[0], "messages": []}

    # Session exists, fetch messages in descending order
    messages = (
        supabase.table("messages")
        .select("*")
        .eq("session_id", session_id)
        .order("created_at", desc=True)
        .execute()
    )

    return {"session": check_session.data[0], "messages": messages.data}


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
    print("session_id received:", session_id)  # 👈 is it arriving?
    print("file:", file.filename)
    contents = await file.read()

    # Pass session_id to folder creation
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

    # read file and add metadata(pages)
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
    get_session = check_create_session(request.session_id)
    session_id = get_session["session"]["id"]

    chunks = get_embeddings(request.user_query, request.file_ids)
    ai_response = ask_ai(request.user_query, chunks)

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

    # 👇 add session_id to the response
    return {**ai_response.model_dump(), "session_id": session_id}


@app.post("/conversation/stream")
async def conversation_stream(request: UserQuery):
    get_session = check_create_session(request.session_id)
    session_id = get_session["session"]["id"]

    chunks = get_embeddings(request.user_query, request.file_ids)

    # Format chunks for the prompt (same as ask_ai)
    formatted_chunks = "\n\n".join(
        [f"[Chunk ID: {c['id']}]\n{c['chunk_content']}" for c in chunks]
    )

    system_prompt = """You are a precise research assistant. Answer strictly based on the chunks provided.
For your response, first give a direct answer, then list your citations.
Format your response as:
ANSWER: <your answer here>
CITATIONS: <cite the exact phrases that support your answer, one per line>"""

    # Store user message first
    supabase.table("messages").insert(
        {
            "session_id": session_id,
            "message_source": "user",
            "content": request.user_query,
        }
    ).execute()

    async def generate():
        full_response = ""

        yield f"data: {json.dumps({'type': 'session', 'session_id': session_id})}\n\n"

        loop = asyncio.get_event_loop()
        stream = await loop.run_in_executor(
            None,
            lambda: client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": system_prompt},
                    {
                        "role": "user",
                        "content": f"Query: {request.user_query}\n\nChunks:\n{formatted_chunks}",
                    },
                ],
                stream=True,
            ),
        )

        for chunk in stream:
            delta = chunk.choices[0].delta.content
            if delta:
                full_response += delta
                yield f"data: {json.dumps({'type': 'token', 'value': delta})}\n\n"
                await asyncio.sleep(0)

        # After streaming is done, parse into structured format
        structured = await loop.run_in_executor(
            None,
            lambda: client.beta.chat.completions.parse(
                model="gpt-4o-mini",
                messages=[
                    {
                        "role": "user",
                        "content": f"""Extract the answer and citations from this response.
                            Original query: {request.user_query}
                            Response: {full_response}
                            Chunks used: {formatted_chunks}

                            Map each supporting point back to the exact chunk it came from.""",
                    }
                ],
                response_format=AIResponse,  # your existing Pydantic model
            ),
        )

        structured_data = structured.choices[0].message.parsed

        # Send structured data to frontend so it can show citations
        yield f"data: {json.dumps({'type': 'structured', 'data': structured_data.model_dump()})}\n\n"
        yield f"data: {json.dumps({'type': 'done'})}\n\n"

        # Save structured format to DB — same as old endpoint
        supabase.table("messages").insert(
            {
                "session_id": session_id,
                "message_source": "ai",
                "content": json.dumps(structured_data.model_dump()),
            }
        ).execute()

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",  # 👈 prevents proxy buffering
        },
    )


@app.get("/sessions/{session_id}/files")
async def get_session_files(session_id: str):
    # Get folder for this session
    folder = (
        supabase.table("folder").select("id").eq("session_id", session_id).execute()
    )

    if not folder.data:
        return []

    folder_ids = [f["id"] for f in folder.data]

    # Get all documents in those folders
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
