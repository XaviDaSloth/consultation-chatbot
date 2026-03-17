# 📄 PDF Consultation Chatbot

A full-stack AI-powered chatbot that lets you upload PDF documents and have intelligent conversations about their content. Built with **Next.js**, **FastAPI**, **Supabase**, and **OpenAI**.

---

## ✨ Features

- 📂 **PDF Upload & Processing** — Drag and drop PDFs, automatically chunked and embedded
- 💬 **AI Conversations** — Ask questions about your documents and get precise answers
- 🔍 **Citation Evidence** — Every AI answer includes exact quotes and page numbers from the source
- ⚡ **Streaming Responses** — Responses stream token by token like ChatGPT
- 🗂️ **Session Management** — All conversations are saved and resumable from the sidebar
- 📎 **Multiple Files** — Upload and query across multiple PDFs in a single session
- 🎨 **Modern UI** — Colorful, responsive design with dark theme

---

## 🏗️ Tech Stack

| Layer    | Technology                                        |
| -------- | ------------------------------------------------- |
| Frontend | Next.js 14 (App Router), TypeScript, Tailwind CSS |
| Backend  | FastAPI, Python                                   |
| Database | Supabase (PostgreSQL)                             |
| Storage  | Supabase Storage                                  |
| AI       | OpenAI GPT-4o Mini, text-embedding-3-small        |
| Search   | Supabase hybrid search (vector + full-text)       |

---

## 📁 Project Structure

```
consultation-chatbot/
├── frontend/chatbot/               # Next.js app
│   ├── src/
│   │   ├── app/
│   │   │   ├── page.tsx            # Main chat page
│   │   │   ├── layout.tsx          # Root layout
│   │   │   └── components/
│   │   │       ├── Sidebar.tsx     # Session list
│   │   │       ├── FileUploader.tsx # Drag & drop uploader
│   │   │       ├── FileChip.tsx    # Uploaded file tag
│   │   │       ├── ChatWindow.tsx  # Message display
│   │   │       └── CitationCard.tsx # Source citations
│   │   └── types/
│   │       └── index.ts            # Shared TypeScript types
│   ├── .env.local                  # Frontend environment variables
│   └── next.config.ts
│
└── service/                        # FastAPI backend
    ├── main.py                     # All endpoints and logic
    ├── .env                        # Backend environment variables
    └── requirements.txt
```

---

## 🗄️ Database Schema

```sql
-- Stores chat sessions
session (
  id uuid PRIMARY KEY,
  created_at timestamptz
)

-- Groups documents per session
folder (
  id uuid PRIMARY KEY,
  folder_name json,
  session_id uuid REFERENCES session(id),
  created_at timestamptz
)

-- PDF file metadata
documents (
  id uuid PRIMARY KEY,
  folder_id uuid REFERENCES folder(id),
  doc_name text,
  file_path text,
  mime_type text
)

-- Text chunks with embeddings
chunks_and_embeddings (
  id uuid PRIMARY KEY,
  document_id uuid REFERENCES documents(id),
  chunk_content text,
  page_no int,
  embedding vector(1536)
)

-- Chat messages
messages (
  id uuid PRIMARY KEY,
  session_id uuid REFERENCES session(id),
  message_source text,   -- 'user' or 'ai'
  content text,
  created_at timestamptz
)
```

---

## 🚀 Getting Started

### Prerequisites

- Node.js 18+
- Python 3.10+
- A Supabase project
- An OpenAI API key

---

### Backend Setup

```bash
cd service
python -m venv venv

# Windows
venv\Scripts\activate

# macOS/Linux
source venv/bin/activate

pip install -r requirements.txt
```

Create a `.env` file in the `service/` folder:

```env
SUPABASE_URL=your_supabase_url
SUPABASE_SERVICE_KEY=your_supabase_service_key
OPENAI_API_KEY=your_openai_api_key
```

Start the backend:

```bash
uvicorn main:app --reload
```

The API will be available at `http://localhost:8000`.

---

### Frontend Setup

```bash
cd frontend/chatbot
npm install
```

Create a `.env.local` file in the `frontend/chatbot/` folder:

```env
NEXT_PUBLIC_API_URL=http://localhost:8000
```

Update `next.config.ts` if accessing from a local network device:

```ts
const nextConfig = {
  allowedDevOrigins: ["your-local-ip"],
};

export default nextConfig;
```

Start the frontend:

```bash
npm run dev
```

The app will be available at `http://localhost:3000`.

---

### Supabase Setup

### Running Migrations

All migrations are in the `supabase/migrations/` folder. Run them **in order** in your Supabase SQL editor:

1. Go to your Supabase project → **SQL Editor**
2. Open and run `001_initial_schema.sql`
3. Run any subsequent numbered files in order

Or run them all at once if you have the Supabase CLI:

```bash
supabase db push
```

```

---

## 🔌 API Endpoints

| Method | Endpoint                  | Description                |
| ------ | ------------------------- | -------------------------- |
| `POST` | `/conversation/init`      | Create a new session       |
| `POST` | `/uploadfile?session_id=` | Upload a PDF file          |
| `POST` | `/process_file?file_id=`  | Chunk and embed a file     |
| `POST` | `/conversation/stream`    | Stream an AI response      |
| `GET`  | `/sessions`               | List all sessions          |
| `GET`  | `/sessions/{id}/messages` | Get messages for a session |
| `GET`  | `/sessions/{id}/files`    | Get files for a session    |

---

## 💬 How It Works

```

1. User uploads a PDF
   ↓
2. File stored in Supabase Storage
   ↓
3. PDF parsed into pages → chunked (512 tokens) → embedded (OpenAI)
   ↓
4. Embeddings saved to Supabase with page metadata
   ↓
5. User asks a question
   ↓
6. Query embedded → hybrid search finds relevant chunks
   ↓
7. Chunks + query sent to GPT-4o Mini
   ↓
8. Response streams token by token to the frontend
   ↓
9. Structured citations extracted and displayed with page numbers

```

---

## ⚙️ Environment Variables

### Backend (`service/.env`)

| Variable               | Description                              |
| ---------------------- | ---------------------------------------- |
| `SUPABASE_URL`         | Your Supabase project URL                |
| `SUPABASE_SERVICE_KEY` | Supabase service role key (not anon key) |
| `OPENAI_API_KEY`       | Your OpenAI API key                      |

### Frontend (`frontend/chatbot/.env.local`)

| Variable              | Description                |
| --------------------- | -------------------------- |
| `NEXT_PUBLIC_API_URL` | URL of the FastAPI backend |

---

## 🧠 Key Concepts Used

- **RAG (Retrieval Augmented Generation)** — AI answers grounded in your documents
- **Vector embeddings** — Semantic search beyond simple keyword matching
- **Hybrid search** — Combines vector similarity and full-text search for better results
- **Server-Sent Events (SSE)** — Powers the streaming token-by-token response
- **Lifting state up** — React pattern used to share file IDs between components
- **File-based routing** — Next.js App Router maps folders directly to URLs

---

## 🐛 Common Issues

**`Failed to fetch` on upload**
→ Check CORS settings in `main.py`. Add your frontend origin to `allow_origins`.

**`ERR_INCOMPLETE_CHUNKED_ENCODING` on streaming**
→ Make sure `asyncio.sleep(0)` is inside the streaming loop and the `StreamingResponse` includes `X-Accel-Buffering: no` header.

**`session_id` null in folder table**
→ Ensure `/conversation/init` is called before the file upload starts, not after.

**Empty chunks / vague AI answers**
→ Verify the file was processed via `/process_file`. Check that `file_ids` is not an empty array in the request body.

---

## 📄 License

MIT
```
