from embeddings import get_embedding_model


def search_documents(
    query
    ,get_connection
    ,documents_table
    ,embeddings_table
    ,label_column="headline"
    ,top_k=5
):
    """
    Generic semantic search over any documents/embeddings table pair that
    follows the weather/destination convention: documents.id -> embeddings.document_id,
    documents.location, chunks derived from documents.narrative_text.
    """

    query_embedding = get_embedding_model().encode(query.strip())
    vector = "[" + ",".join(str(float(value)) for value in query_embedding) + "]"

    sql = f"""
        SELECT
            d.location,
            d.{label_column},
            e.chunk_text,
            1 - (e.embedding <=> %s::vector) AS similarity
        FROM {embeddings_table} e
        JOIN {documents_table} d
            ON d.id = e.document_id
        ORDER BY e.embedding <=> %s::vector
        LIMIT %s;
    """

    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, (vector, vector, top_k))
            rows = cur.fetchall()

    return [
        {
            "location": row["location"]
            ,label_column: row[label_column]
            ,"chunk_text": row["chunk_text"]
            ,"similarity": float(row["similarity"])
        }
        for row in rows
    ]


def search_weather_documents(query, get_connection, top_k=5):
    """Preserves the exact call signature and return shape app.py/server.py already use."""

    return search_documents(
        query
        ,get_connection
        ,documents_table="weather_documents"
        ,embeddings_table="weather_embeddings"
        ,label_column="headline"
        ,top_k=top_k
    )


def search_destination_documents(query, get_connection, top_k=5):
    return search_documents(
        query
        ,get_connection
        ,documents_table="destination_documents"
        ,embeddings_table="destination_embeddings"
        ,label_column="name"
        ,top_k=top_k
    )