CREATE TABLE IF NOT EXISTS destination_documents (
    id TEXT PRIMARY KEY
    ,location TEXT NOT NULL
    ,name TEXT NOT NULL
    ,category TEXT
    ,kinds TEXT
    ,indoor_outdoor TEXT
    ,latitude DOUBLE PRECISION
    ,longitude DOUBLE PRECISION
    ,rating TEXT
    ,address TEXT
    ,narrative_text TEXT
    ,source TEXT NOT NULL DEFAULT 'opentripmap'
    ,payload JSONB NOT NULL
    ,synced_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
