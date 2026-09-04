CREATE EXTENSION IF NOT EXISTS vector;
CREATE TABLE IF NOT EXISTS destination_embeddings (
    id UUID PRIMARY KEY
    ,document_id TEXT NOT NULL REFERENCES destination_documents(id) ON DELETE CASCADE
    ,chunk_index INTEGER NOT NULL
    ,chunk_text TEXT NOT NULL
    ,embedding VECTOR(384) NOT NULL
    ,model_name TEXT NOT NULL
    ,created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()

    ,CONSTRAINT uq_destination_embeddings_document_chunk
        UNIQUE (document_id, chunk_index)
);

CREATE INDEX IF NOT EXISTS idx_destination_embeddings_embedding
    ON destination_embeddings
    USING hnsw (embedding vector_cosine_ops);