import os
import uuid
from datetime import datetime, timezone
from sentence_transformers import SentenceTransformer

WEATHER_DOCUMENTS_TABLE = "weather_documents"
EMBEDDINGS_TABLE = "weather_embeddings"
CHUNK_SIZE = 800
CHUNK_OVERLAP = 100
BATCH_SIZE = 32
EMBEDDING_MODEL_NAME = "sentence-transformers/all-MiniLM-L6-v2"
EMBEDDING_DIM = 384

os.environ["HF_HOME"] = "/tmp/.cache/huggingface"
os.environ["TRANSFORMERS_CACHE"] = "/tmp/.cache/huggingface"
os.environ["HF_HUB_CACHE"] = "/tmp/.cache/huggingface"
_embedding_model = None

def get_embedding_model():
    #load once and resuse
    global _embedding_model
    if _embedding_model is None:
        _embedding_model = SentenceTransformer(
            EMBEDDING_MODEL_NAME,
            cache_folder="/tmp/.cache/huggingface",
        )

    return _embedding_model


def chunk_text(
    text: str,
    chunk_size: int = CHUNK_SIZE,
    chunk_overlap: int = CHUNK_OVERLAP,
) -> list[str]:

    text = text.strip()
    if not text:
        return []

    if chunk_overlap >= chunk_size:
        raise ValueError(
            "chunk_overlap must be smaller than chunk_size"
        )

    step = chunk_size - chunk_overlap
    chunks = []

    for start in range(0, len(text), step):
        chunk = text[start:start + chunk_size].strip()
        if chunk:
            chunks.append(chunk)

        if start + chunk_size >= len(text):
            break
    return chunks


def embed_unembedded_documents(
    get_connection
    ,documents_table=WEATHER_DOCUMENTS_TABLE
    ,embeddings_table=EMBEDDINGS_TABLE
):
    # For incremental load of the embeddings
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                SELECT
                    d.id,
                    d.narrative_text
                FROM {documents_table} d
                WHERE d.narrative_text IS NOT NULL
                  AND TRIM(d.narrative_text) <> ''
                  AND NOT EXISTS (
                      SELECT 1
                      FROM {embeddings_table} e
                      WHERE e.document_id = d.id
                  )
                ORDER BY d.synced_at DESC
                """
            )
            documents = cur.fetchall()

    if not documents:
        return 0

    chunk_rows = []

    for document in documents:
        document_id = document["id"]
        narrative_text = document["narrative_text"]
        chunks = chunk_text(narrative_text)

        for chunk_index, chunk in enumerate(chunks):
            chunk_rows.append({
                "document_id": document_id
                ,"chunk_index": chunk_index
                ,"chunk_text": chunk
            })

    if not chunk_rows:
        return 0

    embedding_model = get_embedding_model()
    all_embeddings = []

    for i in range(0, len(chunk_rows), BATCH_SIZE):
        batch = chunk_rows[i:i + BATCH_SIZE]
        texts = [row["chunk_text"] for row in batch]
        vectors = embedding_model.encode(texts, show_progress_bar=False)
        all_embeddings.extend(vectors.tolist())

    created_at = datetime.now(timezone.utc)
    insert_rows = []

    for row, embedding in zip(chunk_rows, all_embeddings):
        vector_value = "[" + ",".join(str(float(value)) for value in embedding) + "]"

        insert_rows.append((
            str(uuid.uuid4())
            ,row["document_id"]
            ,row["chunk_index"]
            ,row["chunk_text"]
            ,vector_value
            ,EMBEDDING_MODEL_NAME
            ,created_at
        ))

    insert_query = f"""
        INSERT INTO {embeddings_table} (
            id, document_id, chunk_index, chunk_text, embedding, model_name, created_at
        )
        VALUES (%s,%s,%s,%s,%s::vector,%s,%s)
        ON CONFLICT (document_id, chunk_index) DO NOTHING
    """

    inserted_count = 0

    with get_connection() as conn:
        with conn.cursor() as cur:
            for i in range(0, len(insert_rows), 100):
                batch = insert_rows[i:i + 100]
                cur.executemany(insert_query, batch)
                inserted_count += cur.rowcount
        conn.commit()

    return inserted_count