# Weather Intelligence

A Databricks-based weather intelligence application that ingests weather data, stores it in Lakebase, generates vector embeddings, and enables semantic search over weather information.

## Architecture

```text
Weather API
    ↓
weather_documents
    ↓
Chunking
    ↓
all-MiniLM-L6-v2 embeddings
    ↓
weather_embeddings
    ↓
Vector similarity search
    ↓
Weather Intelligence UI
```

The application is deployed as a Databricks App and uses Lakebase (PostgreSQL) for storage.

## 1. Data Source

The project uses weather data from the **National Weather Service (NWS) API**.

NWS was chosen because:

- It provides authoritative U.S. weather information.
- The API is publicly accessible.
- It provides both structured forecast data and text-based weather information.
- Forecast discussions and weather narratives are well suited to semantic search.
- The data contains useful context that would be difficult to retrieve using simple keyword matching.

The application accepts locations such as:

```text
Chicago, IL
New York City, NY
Los Angeles, CA
```

and synchronizes relevant weather documents into Lakebase.

## 2. Data Model

### `weather_documents`

This table stores the source weather documents.

Key fields include:

| Column | Purpose |
|---|---|
| `id` | Unique document identifier |
| `location` | Location associated with the document |
| `source_type` | Type of weather source/document |
| `headline` | Human-readable document title |
| `narrative_text` | Main weather narrative used for embedding |
| `synced_at` | Timestamp indicating when the document was synchronized |

The source document is kept separately from its embeddings so that the original weather information remains available and can be joined back to search results.

### `weather_embeddings`

This table stores the vectorized chunks of each weather document.

Key fields include:

| Column | Purpose |
|---|---|
| `id` | Unique embedding/chunk identifier |
| `document_id` | Reference to `weather_documents.id` |
| `chunk_index` | Position of the chunk within the document |
| `chunk_text` | Original text represented by the embedding |
| `embedding` | 384-dimensional vector |
| `model_name` | Embedding model used |
| `created_at` | Embedding creation timestamp |

A unique constraint on:

```text
(document_id, chunk_index)
```

prevents the same document chunk from being embedded more than once.

## 3. Chunking Strategy

Weather narratives are split into overlapping text chunks before embedding.

Current configuration:

```text
Chunk size:       800 characters
Chunk overlap:    100 characters
```

The overlap helps preserve context when important information falls near a chunk boundary.

The chunking implementation is intentionally simple at this stage. It uses character-based windows rather than attempting to split on sentences or semantic topics.

## 4. Embedding Model

The project uses:

```text
sentence-transformers/all-MiniLM-L6-v2
```

with:

```text
Embedding dimensions: 384
Batch size:           32
```

`all-MiniLM-L6-v2` was selected because it provides a good balance between semantic quality, model size, and inference speed.

The model runs directly inside the Databricks App, avoiding the need for an external embedding API.

The model is loaded once and reused by the application to avoid repeatedly initializing the model for every request.

## 5. End-to-End Pipeline

### Step 1 — Sync weather data

The UI sends a request to:

```text
POST /weather/sync
```

The application retrieves weather information for the requested locations and upserts documents into:

```text
weather_documents
```

### Step 2 — Automatic embedding

After synchronization completes, the application automatically calls:

```python
embed_unembedded_documents(lakebase.get_connection)
```

Only documents that do not already have embeddings are processed.

The process:

1. Finds unembedded documents.
2. Splits the narrative text into chunks.
3. Generates 384-dimensional embeddings.
4. Inserts the chunks into `weather_embeddings`.
5. Uses `(document_id, chunk_index)` to avoid duplicate chunks.

This makes embedding a downstream step of the synchronization process rather than requiring a separate manual job.

### Step 3 — Semantic search

The UI sends a question to:

```text
POST /weather/search
```

For example:

```text
How hot is it in New York City?
```

The question is converted into the same 384-dimensional embedding space.

The application then performs vector similarity search using PostgreSQL/pgvector:

```sql
ORDER BY e.embedding <=> %s::vector
```

The most relevant chunks are returned together with their source location, headline, and similarity score.

## 6. Running the Pipeline

### Start the application

The Databricks App runs:

```text
python app.py
```

### Sync weather data

Use the Weather Intelligence UI:

1. Enter a location.
2. Click **Sync Weather**.
3. The application fetches and stores the weather documents.
4. New documents are automatically embedded.

### Search

Enter a natural-language question such as:

```text
How hot is it in New York City?
```

or:

```text
Is there a risk of flooding near rivers?
```

The application performs semantic vector search and displays the most relevant weather chunks.

## 7. Known Limitations

### No generative RAG response yet

The current application performs semantic retrieval but does not yet pass the retrieved context to an LLM to generate a synthesized answer.

The current flow is:

```text
Question
   ↓
Embedding
   ↓
Vector Search
   ↓
Relevant Chunks
```

A future RAG layer will extend this to:

```text
Question
   ↓
Vector Search
   ↓
Relevant Chunks
   ↓
LLM
   ↓
Natural-language answer
```

### Simple character-based chunking

The current 800-character chunking strategy does not understand sentence or topic boundaries.

A future implementation could use sentence-aware or topic-aware chunking.

### Embedding model

`all-MiniLM-L6-v2` is lightweight and fast, but larger embedding models could potentially provide better retrieval quality.

### Retrieval filtering

Search currently performs vector similarity across the available embedding data.

Future improvements could include filtering by:

- location
- source type
- document date
- forecast period

### Document deduplication

The current ingestion flow still needs stronger document-level deduplication/upsert behavior based on a stable source identifier.

### Scheduling

Weather synchronization currently depends on triggering the sync endpoint.

A production version should run synchronization on a schedule so that the knowledge base stays current automatically.

### Database connection management

The application currently uses a direct Lakebase connection for search and embedding operations. The connection pool implementation was found to cause connection acquisition timeouts in the App environment and is therefore not currently used for these operations.

## 8. Future Improvements

Planned improvements include:

1. Add an LLM-based RAG response layer.
2. Improve document deduplication/upsert logic.
3. Schedule automatic weather synchronization.
4. Add retrieval filtering by `source_type`.
5. Improve chunking strategy.
6. Add citations/source references to generated answers.
7. Improve retrieval evaluation and relevance testing.

##9. Grant access
GRANT ALL PRIVILEGES ON TABLE weather_embeddings TO "dbf9f891-2ab9-499e-8376-2867b405bb96";

ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL PRIVILEGES ON TABLES TO "dbf9f891-2ab9-499e-8376-2867b405bb96";

##10. Notes as I go:
1. Databricks recognizes an app prefixed with `mcp-` as a custom MCP server and lists it under the `Agents > MCP Servers` tab — it doesn't provision a separate MCP server object, just reflects the app's own `/mcp` endpoint. This custom MCP server can't also be deleted without deleting the app. 
