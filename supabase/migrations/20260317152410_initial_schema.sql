-- =====================
-- EXTENSIONS
-- =====================
CREATE EXTENSION IF NOT EXISTS vector SCHEMA extensions;

-- =====================
-- SESSION
-- =====================
CREATE TABLE IF NOT EXISTS public.session (
  id uuid NOT NULL DEFAULT gen_random_uuid(),
  title text NULL,
  created_at timestamp with time zone NOT NULL DEFAULT now(),
  CONSTRAINT session_pkey PRIMARY KEY (id)
) TABLESPACE pg_default;

-- =====================
-- FOLDER
-- =====================
CREATE TABLE IF NOT EXISTS public.folder (
  id uuid NOT NULL DEFAULT gen_random_uuid(),
  folder_name json NULL,
  created_at timestamp with time zone NOT NULL DEFAULT now(),
  session_id uuid NULL,
  CONSTRAINT folder_files_pkey PRIMARY KEY (id),
  CONSTRAINT folder_session_id_fkey FOREIGN KEY (session_id)
    REFERENCES session (id) ON DELETE CASCADE
) TABLESPACE pg_default;

-- =====================
-- DOCUMENTS
-- =====================
CREATE TABLE IF NOT EXISTS public.documents (
  id uuid NOT NULL DEFAULT gen_random_uuid(),
  doc_name text NULL,
  folder_id uuid NULL,
  mime_type text NULL,
  created_at timestamp with time zone NOT NULL DEFAULT now(),
  file_path text NULL,
  CONSTRAINT documents_pkey PRIMARY KEY (id),
  CONSTRAINT documents_folder_id_fkey FOREIGN KEY (folder_id)
    REFERENCES folder (id) ON DELETE CASCADE
) TABLESPACE pg_default;

-- =====================
-- CHUNKS AND EMBEDDINGS
-- =====================
CREATE TABLE IF NOT EXISTS public.chunks_and_embeddings (
  id uuid NOT NULL DEFAULT gen_random_uuid(),
  document_id uuid NULL,
  chunk_content text NOT NULL,
  chunk_index bigint NULL,
  created_at timestamp with time zone NOT NULL DEFAULT now(),
  fts tsvector GENERATED ALWAYS AS (
    to_tsvector('english'::regconfig, chunk_content)
  ) STORED,
  embedding extensions.vector NULL,
  page_no bigint NULL,
  CONSTRAINT chunks_and_embeddings_pkey PRIMARY KEY (id),
  CONSTRAINT chunks_and_embeddings_document_id_fkey FOREIGN KEY (document_id)
    REFERENCES documents (id) ON UPDATE CASCADE ON DELETE CASCADE
) TABLESPACE pg_default;

-- Indexes for full-text and vector search
CREATE INDEX IF NOT EXISTS chunks_and_embeddings_fts_idx
  ON public.chunks_and_embeddings USING gin (fts) TABLESPACE pg_default;

CREATE INDEX IF NOT EXISTS chunks_and_embeddings_embedding_idx
  ON public.chunks_and_embeddings USING hnsw (embedding extensions.vector_ip_ops) TABLESPACE pg_default;

-- =====================
-- MESSAGES
-- =====================
CREATE TABLE IF NOT EXISTS public.messages (
  id uuid NOT NULL DEFAULT gen_random_uuid(),
  session_id uuid NULL,
  message_source text NULL,
  content text NULL,
  created_at timestamp with time zone NOT NULL DEFAULT now(),
  CONSTRAINT messages_pkey PRIMARY KEY (id),
  CONSTRAINT messages_session_id_fkey FOREIGN KEY (session_id)
    REFERENCES session (id) ON DELETE CASCADE
) TABLESPACE pg_default;

-- =====================
-- HYBRID SEARCH FUNCTION
-- =====================
-- Uses Reciprocal Rank Fusion (RRF) to combine full-text and semantic search results.
-- full_text_weight and semantic_weight control the balance between the two search types.
-- rrf_k is a smoothing constant that prevents high scores from dominating.
CREATE OR REPLACE FUNCTION hybrid_search(
  document_ids uuid[],
  query_text text,
  query_embedding extensions.vector(1536),
  match_count int,
  full_text_weight float = 1,
  semantic_weight float = 1,
  rrf_k int = 50
)
RETURNS SETOF chunks_and_embeddings
LANGUAGE sql
AS $$
  WITH full_text AS (
    SELECT
      id,
      row_number() OVER (
        ORDER BY ts_rank_cd(fts, websearch_to_tsquery(query_text)) DESC
      ) AS rank_ix
    FROM chunks_and_embeddings
    WHERE
      fts @@ websearch_to_tsquery(query_text)
      AND document_id = ANY(document_ids)
    ORDER BY rank_ix
    LIMIT LEAST(match_count, 30) * 2
  ),
  semantic AS (
    SELECT
      id,
      row_number() OVER (
        ORDER BY embedding <#> query_embedding
      ) AS rank_ix
    FROM chunks_and_embeddings
    WHERE document_id = ANY(document_ids)
    ORDER BY rank_ix
    LIMIT LEAST(match_count, 30) * 2
  )
  SELECT chunks_and_embeddings.*
  FROM full_text
  FULL OUTER JOIN semantic ON full_text.id = semantic.id
  JOIN chunks_and_embeddings
    ON coalesce(full_text.id, semantic.id) = chunks_and_embeddings.id
  ORDER BY
    coalesce(1.0 / (rrf_k + full_text.rank_ix), 0.0) * full_text_weight +
    coalesce(1.0 / (rrf_k + semantic.rank_ix), 0.0) * semantic_weight
    DESC
  LIMIT LEAST(match_count, 30);
$$;