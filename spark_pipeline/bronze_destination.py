from pathlib import Path
import sys
import os
import json
from datetime import datetime, timezone
from destination import DEFAULT_INGEST_CATEGORIES
from destination_api import DestinationAPI, DestinationAPIError

REPO_ROOT = Path(
    "/Workspace/Users/tuvu.uwyo@gmail.com/weather_intelligence_databricks"
)
sys.path.insert(0, str(REPO_ROOT))

CATALOG = "weather_intelligence"
SCHEMA = "bronze"
TABLE = "destinations_raw"

# --- 1. Set up the catalog, schema, and Bronze table (safe to re-run) ---
spark.sql(f"CREATE CATALOG IF NOT EXISTS {CATALOG}")
spark.sql(f"CREATE SCHEMA IF NOT EXISTS {CATALOG}.{SCHEMA}")
spark.sql(f"""
    CREATE TABLE IF NOT EXISTS {CATALOG}.{SCHEMA}.{TABLE} (
        place_id STRING,
        location STRING NOT NULL,
        raw_feature STRING NOT NULL,
        fetched_at TIMESTAMP NOT NULL,
        source STRING NOT NULL
    ) USING DELTA
""")


