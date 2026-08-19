-- AI Dialogue Enhancer — complete database schema
-- Run this file in the Supabase SQL editor.

CREATE EXTENSION IF NOT EXISTS vector;

-- ─────────────────────────────────────
-- documents
-- ─────────────────────────────────────
CREATE TABLE documents (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    filename TEXT NOT NULL,
    file_type TEXT NOT NULL,
    source_type TEXT,
    title TEXT,
    author TEXT,
    published_date DATE,
    word_count INTEGER,
    status TEXT DEFAULT 'processing',
    error_message TEXT,
    created_at TIMESTAMPTZ DEFAULT now()
);

-- ─────────────────────────────────────
-- document_chunks
-- ─────────────────────────────────────
CREATE TABLE document_chunks (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    document_id UUID REFERENCES documents(id) ON DELETE CASCADE,
    chunk_index INTEGER NOT NULL,
    content TEXT NOT NULL,
    token_count INTEGER,
    embedding vector(1536),
    created_at TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX document_chunks_embedding_idx
    ON document_chunks
    USING ivfflat (embedding vector_cosine_ops)
    WITH (lists = 100);

-- ─────────────────────────────────────
-- match_documents RPC
-- ─────────────────────────────────────
CREATE OR REPLACE FUNCTION match_documents(
  query_embedding vector(1536),
  match_threshold float,
  match_count int
)
RETURNS TABLE (
  id UUID,
  document_id UUID,
  content TEXT,
  similarity float
)
LANGUAGE SQL STABLE AS $$
  SELECT
    dc.id,
    dc.document_id,
    dc.content,
    1 - (dc.embedding <=> query_embedding) AS similarity
  FROM document_chunks dc
  WHERE 1 - (dc.embedding <=> query_embedding) > match_threshold
  ORDER BY similarity DESC
  LIMIT match_count;
$$;

-- ─────────────────────────────────────
-- conversations
-- ─────────────────────────────────────
CREATE TABLE conversations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    platform TEXT NOT NULL,
    post_url TEXT,
    post_author TEXT,
    original_post TEXT NOT NULL,
    full_thread TEXT,
    submitted_at TIMESTAMPTZ DEFAULT now(),
    analysis_status TEXT DEFAULT 'pending'
);

-- ─────────────────────────────────────
-- conversation_analysis
-- ─────────────────────────────────────
CREATE TABLE conversation_analysis (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    conversation_id UUID REFERENCES conversations(id) ON DELETE CASCADE,
    central_topic TEXT,
    key_tensions JSONB,
    viewpoints_represented JSONB,
    emotional_sensitivities TEXT,
    can_add_value BOOLEAN,
    value_reasoning TEXT,
    participation_recommendation TEXT,
    recommendation_reason TEXT,
    relevance_score FLOAT,
    created_at TIMESTAMPTZ DEFAULT now()
);

-- ─────────────────────────────────────
-- response_drafts
-- ─────────────────────────────────────
CREATE TABLE response_drafts (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    conversation_id UUID REFERENCES conversations(id) ON DELETE CASCADE,
    style TEXT NOT NULL,
    content TEXT NOT NULL,
    value_explanation TEXT,
    source_chunk_ids UUID[],
    source_document_titles TEXT[],
    include_link BOOLEAN DEFAULT false,
    suggested_link TEXT,
    status TEXT DEFAULT 'pending',
    edited_content TEXT,
    rejection_reason TEXT,
    approved_at TIMESTAMPTZ,
    posted_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT now()
);

-- ─────────────────────────────────────
-- feedback_log
-- ─────────────────────────────────────
CREATE TABLE feedback_log (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    draft_id UUID REFERENCES response_drafts(id),
    conversation_id UUID REFERENCES conversations(id),
    action TEXT,
    original_content TEXT,
    final_content TEXT,
    rejection_reason TEXT,
    edit_diff TEXT,
    created_at TIMESTAMPTZ DEFAULT now()
);

-- ─────────────────────────────────────
-- processing_logs
-- ─────────────────────────────────────
CREATE TABLE processing_logs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    task_type TEXT,
    reference_id UUID,
    status TEXT,
    message TEXT,
    created_at TIMESTAMPTZ DEFAULT now()
);
