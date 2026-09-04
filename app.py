from flask import Flask, request, jsonify, render_template
import os
import psycopg
from psycopg_pool import ConnectionPool
from databricks import sdk

from weather import WeatherClient, upsert_documents as upsert_weather_documents
from destination import fetch_destinations, upsert_documents as upsert_destination_documents

import lakebase
from embeddings import embed_unembedded_documents
from search import search_weather_documents, search_destination_documents

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

# ======================================================
# WEATHER
# ======================================================

# -----------------------------
# Weather sync/upsert/embedd
# -----------------------------
@app.route("/weather/sync", methods=["POST"])
def sync_weather():
    #Flask Endpoint:
    data = request.get_json(silent=True) or {}
    locations = data.get("locations")
    limit = data.get("limit", 50)

    if not isinstance(locations, list) or not locations:
        return jsonify({"error": "locations must be a non-empty list"}), 400

    limit = max(1, min(limit, 50))
    total_synced = 0
    errors = []

    for location in locations:
        try:
            documents = weather_client.fetch_location_input(location)
            documents = documents[:limit]
            total_synced += upsert_weather_documents(documents)
        except Exception as exc:
            errors.append({
                "location": location,
                "error": str(exc)
            })

    embedded = 0

    try:
        embedded = embed_unembedded_documents(lakebase.get_connection)
    except Exception as exc:
        errors.append({"embedding": str(exc)})

    return jsonify({
        "synced": total_synced,
        "embedded": embedded,
        "locations_requested": len(locations),
        "errors": errors,
    })

# --------------------------------
# Weather semantic search
# --------------------------------
@app.route("/weather/search", methods=["POST"])
def search_weather():
    #Flask Endpoint:
    data = request.get_json(silent=True) or {}
    query = data.get("query")
    top_k = data.get("top_k", 5)

    if not isinstance(query, str) or not query.strip():
        return jsonify({"error": "query must be a non-empty string"}), 400

    top_k = max(1, min(top_k, 20))
    results = search_weather_documents(
        query=query,
        get_connection=lakebase.get_connection,
        top_k=top_k
    )

    return jsonify({
        "query": query,
        "results": results
    })

# ======================================================
# DESTINATIONS
# ======================================================

# ---------------------------------
# Destination sync/upsert/embedd
# ---------------------------------

@app.route("/destinations/sync", methods=["POST"])
def sync_destinations():
    data = request.get_json(silent=True) or {}
    locations = data.get("locations")
    limit = data.get("limit", 50)

    if not isinstance(locations, list) or not locations:
        return jsonify({"error": "locations must be a non-empty list"}), 400

    limit = max(1, min(int(limit), 50))
    total_synced = 0
    errors = []

    for location in locations:
        try:
            documents = fetch_destinations(
                location
                ,api_key=os.environ["GEOAPIFY_API_KEY"]
                ,limit=limit
            )
            total_synced += upsert_destination_documents(documents)
        except Exception as exc:
            errors.append({"location": location, "error": str(exc)})

    embedded = 0
    try:
        embedded = embed_unembedded_documents(
            lakebase.get_connection
            ,documents_table="destination_documents"
            ,embeddings_table="destination_embeddings"
        )
    except Exception as exc:
        errors.append({"embedding": str(exc)})

    return jsonify({
        "synced": total_synced
        ,"embedded": embedded
        ,"locations_requested": len(locations)
        ,"errors": errors
    })

# --------------------------------
# Destination semantic search
# --------------------------------

@app.route("/destinations/search", methods=["POST"])
def search_destinations():
    data = request.get_json(silent=True) or {}
    query = data.get("query")
    top_k = max(1, min(int(data.get("top_k", 5)), 20))

    if not isinstance(query, str) or not query.strip():
        return jsonify({"error": "query must be a non-empty string"}), 400

    # NOT BUILT YET — see note below
    results = search_destination_documents(
        query=query
        ,get_connection=lakebase.get_connection
        ,top_k=top_k
    )

    return jsonify({"query": query, "results": results})

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