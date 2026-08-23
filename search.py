from embeddings import get_embedding_model

def search_weather_documents(query, get_connection, top_k=5):
    """
    Search weather document chunks using semantic similarity.
    """

    query_embedding = get_embedding_model().encode(query.strip())

    vector = "[" + ",".join(
        str(float(value)) for value in query_embedding
    ) + "]"

    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT
                    d.location,
                    d.headline,
                    e.chunk_text,
                    1 - (e.embedding <=> %s::vector) AS similarity
                FROM weather_embeddings e
                JOIN weather_documents d
                    ON d.id = e.document_id
                ORDER BY e.embedding <=> %s::vector
                LIMIT %s;
                """,
                (vector, vector, top_k),
            )

            rows = cur.fetchall()

    return [
        {
            "location": row["location"],
            "headline": row["headline"],
            "chunk_text": row["chunk_text"],
            "similarity": float(row["similarity"]),
        }
        for row in rows
    ]