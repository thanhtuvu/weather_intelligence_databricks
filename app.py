from flask import Flask, request, jsonify, render_template
import os
import psycopg
from psycopg_pool import ConnectionPool
from databricks import sdk
from weather import WeatherClient, upsert_documents
import lakebase
from embeddings import embed_unembedded_documents
from search import search_weather_documents
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
@app.route("/health")
def health():
    return {
        "status": "ok",
        "pgendpoint_exists": bool(os.environ.get("PGENDPOINT")),
        "pgendpoint": os.environ.get("PGENDPOINT"),
    }

# --------------------------------------------------
# Weather sync
# --------------------------------------------------

@app.route("/weather/sync", methods=["POST"])
def sync_weather():
    #Flask Endpoint:
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

    #From weather.py:
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
    #Flask Endpoint:
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

    # From search.py
    results = search_weather_documents(
        query=query,
        get_connection=lakebase.get_connection,
        top_k=top_k,
    )

    return jsonify({
        "query": query,
        "results": results,
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