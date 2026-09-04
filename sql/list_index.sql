SELECT
    tablename
    ,indexname
    ,indexdef
FROM pg_indexes
WHERE schemaname = 'public'
-- and tablename = 'destination_embeddings'
ORDER BY tablename