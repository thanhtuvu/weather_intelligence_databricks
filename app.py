from flask import Flask, request, jsonify, render_template
import os
import psycopg
from psycopg_pool import ConnectionPool
from databricks import sdk
from weather import WeatherClient, upsert_documents
import lakebase
from embeddings import (
    embed_unembedded_documents,
    get_embedding_model,
)
# --------------------------------------------------
# Databricks / Lakebase connection
# --------------------------------------------------

workspace_client = sdk.WorkspaceClient()
endpoint = os.getenv("PGENDPOINT")
connection_pool = None

class OAuthConnection(psycopg.Connection):
    @classmethod
    def connect(cls, conninfo="", **kwargs):
        credential = workspace_client.postgres.generate_database_credential(
            endpoint=endpoint
        )

        kwargs["password"] = credential.token
        return super().connect(conninfo, **kwargs)

def get_connection_pool():
    global connection_pool
    if connection_pool is None:
        conn_string = (
            f"dbname={os.getenv('PGDATABASE')} "
            f"user={os.getenv('PGUSER')} "
            f"host={os.getenv('PGHOST')} "
            f"port={os.getenv('PGPORT')} "
            f"sslmode={os.getenv('PGSSLMODE', 'require')} "
            f"application_name={os.getenv('PGAPPNAME')}"
        )

        connection_pool = ConnectionPool(
            conn_string,
            connection_class=OAuthConnection,
            min_size=1,
            max_size=10,
        )
    return connection_pool

def get_connection():
    return get_connection_pool().connection()

# --------------------------------------------------
# Weather client
# --------------------------------------------------

weather_client = WeatherClient()

# --------------------------------------------------
# Flask app
# --------------------------------------------------

app = Flask(__name__)
@app.errorhandler(Exception)
def handle_exception(exc):
    return jsonify({
        "error": str(exc)
    }), 500
# --------------------------------------------------
# UI
# --------------------------------------------------

@app.route("/", methods=["GET"])
def index():
    return render_template("index.html")

# --------------------------------------------------
# Health
# --------------------------------------------------

@app.route("/health", methods=["GET"])
def health():
    return jsonify({
        "status": "ok"
    })

# --------------------------------------------------
# Weather sync
# --------------------------------------------------

@app.route("/weather/sync", methods=["POST"])
def sync_weather():

    data = request.get_json(silent=True) or {}
    locations = data.get("locations")
    limit = data.get("limit", 50)

    if not isinstance(locations, list) or not locations:
        return jsonify({
            "error": "locations must be a non-empty list"
        }), 400

    try:
        limit = int(limit)
    except (TypeError, ValueError):
        return jsonify({
            "error": "limit must be an integer"
        }), 400

    limit = max(1, min(limit, 50))
    total_synced = 0
    errors = []

    for location in locations:
        try:
            documents = weather_client.fetch_location_input(
                location
            )
            documents = documents[:limit]
            synced = upsert_documents(documents)
            total_synced += synced

        except Exception as exc:
            errors.append({
                "location": location,
                "error": str(exc),
            })

    embedded = 0

    try:
        embedded = embed_unembedded_documents(
            lakebase.get_connection
        )

    except Exception as exc:
        errors.append({
            "embedding": str(exc),
        })

    return jsonify({
        "synced": total_synced,
        "embedded": embedded,
        "locations_requested": len(locations),
        "errors": errors,
    })

# --------------------------------------------------
# Weather semantic search
# --------------------------------------------------

@app.route("/weather/search", methods=["POST"])
def search_weather():
    data = request.get_json(silent=True) or {}
    query = data.get("query")
    top_k = data.get("top_k", 5)

    if not isinstance(query, str) or not query.strip():
        return jsonify({
            "error": "query must be a non-empty string"
        }), 400

    try:
        top_k = int(top_k)
    except (TypeError, ValueError):
        return jsonify({
            "error": "top_k must be an integer"
        }), 400

    top_k = max(1, min(top_k, 20))
    query_embedding = get_embedding_model().encode(
        query.strip()
    )

    vector = "[" + ",".join(
        str(float(value)) for value in query_embedding
    ) + "]"

# Search connection is using the App's Lakebase connection
    with lakebase.get_connection() as conn:
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

            results = cur.fetchall()

    return jsonify({
        "query": query,
        "results": [
            {
                "location": row["location"],
                "headline": row["headline"],
                "chunk_text": row["chunk_text"],
                "similarity": float(row["similarity"]),
            }
            for row in results
        ],
    })


# --------------------------------------------------
# Run
# --------------------------------------------------

if __name__ == "__main__":
    host = os.getenv("FLASK_RUN_HOST", "0.0.0.0")
    port = int(os.getenv("FLASK_RUN_PORT", "8000"))

    app.run(
        host=host,
        port=port,
        debug=False,
    )