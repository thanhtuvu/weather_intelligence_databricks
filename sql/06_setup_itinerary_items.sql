CREATE TABLE IF NOT EXISTS itinerary_items (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid()
    ,itinerary_id UUID NOT NULL REFERENCES itineraries(id) ON DELETE CASCADE
    ,day_number INTEGER NOT NULL
    ,sequence_order INTEGER NOT NULL
    ,item_type TEXT NOT NULL
    ,attraction_id TEXT REFERENCES destination_documents(id)
    ,title TEXT NOT NULL
    ,start_time TIMESTAMPTZ
    ,end_time TIMESTAMPTZ
    ,latitude DOUBLE PRECISION
    ,longitude DOUBLE PRECISION
    ,weather_context JSONB
    ,notes TEXT
    ,created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_itinerary_items_itinerary
    ON itinerary_items (itinerary_id, day_number, sequence_order);