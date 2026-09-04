CREATE EXTENSION IF NOT EXISTS pgcrypto;

CREATE TABLE IF NOT EXISTS itineraries (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid()
    ,user_id TEXT NOT NULL
    ,destination TEXT NOT NULL
    ,start_date DATE NOT NULL
    ,end_date DATE NOT NULL
    ,preferences JSONB NOT NULL DEFAULT '{}'::jsonb
    ,status TEXT NOT NULL DEFAULT 'draft'
    ,created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
    ,updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);