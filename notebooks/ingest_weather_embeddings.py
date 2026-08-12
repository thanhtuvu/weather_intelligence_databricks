from pathlib import Path
import sys

from embeddings import (
    embed_unembedded_documents,
    EMBEDDING_MODEL_NAME,
    EMBEDDING_DIM,
    CHUNK_SIZE,
    CHUNK_OVERLAP,
    BATCH_SIZE,
)

import lakebase

REPO_ROOT = Path(
    "/Workspace/Users/tuvu.uwyo@gmail.com/weather_intelligence_databricks"
)

sys.path.insert(0, str(REPO_ROOT))

print(f"Embedding model: {EMBEDDING_MODEL_NAME}")
print(f"Embedding dimension: {EMBEDDING_DIM}")
print(f"Chunk size: {CHUNK_SIZE}")
print(f"Chunk overlap: {CHUNK_OVERLAP}")
print(f"Batch size: {BATCH_SIZE}")

inserted_count = embed_unembedded_documents(
    lakebase.get_connection
)

print(
    f"Inserted {inserted_count} new weather embeddings."
)