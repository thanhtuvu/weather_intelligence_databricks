from pathlib import Path
import sys
import json
import os
import requests

REPO_ROOT = Path(
    "/Workspace/Users/tuvu.uwyo@gmail.com/weather_intelligence_databricks"
)
sys.path.insert(0, str(REPO_ROOT))

from destination import normalize_place, UNNAMED_PLACEHOLDER
from datetime import datetime, timezone
import json
from pyspark.sql.functions import udf
from pyspark.sql.types import StructType, StructField, StringType, DoubleType
from databricks.sdk import WorkspaceClient

CATALOG = "weather_intelligence"
BRONZE_TABLE = f"{CATALOG}.bronze.destinations_raw"
SILVER_TABLE = f"{CATALOG}.silver.destinations_clean"
SCHEMA = "silver"
spark.sql(f"CREATE SCHEMA IF NOT EXISTS {CATALOG}.{SCHEMA}")

# Fill in your actual Databricks App URL and NAME (both visible on the app's page).
# Note the /api/ prefix — Databricks Apps' token authentication only reaches
# routes under /api/, which is why the Flask route was renamed to match.
APP_SYNC_URL = "https://weather-intelligence-app-7474652422931165.aws.databricksapps.com/api/silver/sync"
APP_NAME = "weather-intelligence-app"

# Matches destination_documents' shape exactly (minus synced_at)

silver_schema = StructType([
    StructField("id", StringType(), False)
    ,StructField("location", StringType(), False)
    ,StructField("name", StringType(), False)
    ,StructField("category", StringType(), True)
    ,StructField("kinds", StringType(), True)
    ,StructField("indoor_outdoor", StringType(), True)
    ,StructField("latitude", DoubleType(), True)
    ,StructField("longitude", DoubleType(), True)
    ,StructField("address", StringType(), True)
    ,StructField("narrative_text", StringType(), True)
    ,StructField("payload", StringType(), False)
])

def _clean_row(raw_feature, raw_detail, location):
    feature = json.loads(raw_feature)
    detail = json.loads(raw_detail) if raw_detail else None
    doc = normalize_place(feature, detail, location)

    return (
        doc["id"]
        ,doc["location"]
        ,doc["name"]
        ,doc["category"]
        ,doc["kinds"]
        ,doc["indoor_outdoor"]
        ,doc["latitude"]
        ,doc["longitude"]
        ,doc["address"]
        ,doc["narrative_text"]
        ,json.dumps(doc["payload"])
    )

clean_row_udf = udf(_clean_row, silver_schema)

bronze_df = spark.table(BRONZE_TABLE)

silver_df = (
    bronze_df
    .withColumn("cleaned", clean_row_udf("raw_feature", "raw_detail", "location"))
    .select("cleaned.*")
    .filter(f"name != '{UNNAMED_PLACEHOLDER}'")
)

#Write to silver schema `destinations_clean` table:
silver_df.write.mode("overwrite").saveAsTable(SILVER_TABLE)

# --- Hand off the Lakebase write + embedding step to the Flask/MCP app ---
# psycopg can't run safely inside this Spark driver process (SIGABRT — a
# native libpq conflict with the driver's own already-loaded native libs).
# The app's container is a plain Python process with none of that baggage,
# and already does this exact upsert_documents()/embed_unembedded_documents()
# work for every other route — so Silver's job is just to hand it the
# cleaned rows over HTTP instead of touching Lakebase directly.

now = datetime.now(timezone.utc)
rows = silver_df.collect()
documents = [
    {
        "id": row["id"]
        ,"location": row["location"]
        ,"name": row["name"]
        ,"category": row["category"]
        ,"kinds": row["kinds"]
        ,"indoor_outdoor": row["indoor_outdoor"]
        ,"latitude": row["latitude"]
        ,"longitude": row["longitude"]
        ,"address": row["address"]
        ,"narrative_text": row["narrative_text"]
        ,"payload": json.loads(row["payload"])
        ,"synced_at": now.isoformat()  # datetime isn't JSON-serializable — sent as ISO text, parsed back on the other end
    }
    for row in rows
]

sync_token = dbutils.secrets.get(scope="geoapify", key="silver-sync-token")

# --- Exchange this notebook's own token for an audience-scoped OAuth token
#     for the app, per Databricks' documented "call an app from a notebook"
#     flow. Without this, the request never reaches Flask at all — Databricks
#     Apps gates access at the platform level, before your route code runs,
#     regardless of any custom header you send.
_wc = WorkspaceClient()
app_client_id = _wc.apps.get(APP_NAME).oauth2_app_client_id

notebook_token = (
    dbutils.notebook.entry_point.getDbutils()
    .notebook().getContext().apiToken().get()
)

token_response = requests.post(
    url=f"{_wc.config.host}/oidc/v1/token"
    ,data={
        "grant_type": "urn:ietf:params:oauth:grant-type:token-exchange"
        ,"subject_token": notebook_token
        ,"subject_token_type": "urn:databricks:params:oauth:token-type:personal-access-token"
        ,"requested_token_type": "urn:ietf:params:oauth:token-type:access_token"
        ,"scope": "all-apis"
        ,"audience": app_client_id
    }
)
token_response.raise_for_status()
audience_token = token_response.json()["access_token"]

response = requests.post(
    APP_SYNC_URL
    ,json={"documents": documents}
    ,headers={
        "Authorization": f"Bearer {audience_token}"  # gets the request past Databricks Apps' own platform gate
        ,"X-Sync-Token": sync_token  # confirms to Flask specifically that this is the Spark job calling
    }
    ,timeout=300  # generous on purpose — the app embeds the documents server-side before responding, which can take a while for a few hundred rows
)

# Log the raw response before assuming it's JSON — an empty or HTML body
# here (instead of a JSONDecodeError further down) is the fastest way to
# tell whether this is an auth/routing problem versus an actual app error.
print(f"App responded {response.status_code}: {response.text[:500]}")

if not response.ok:
    raise RuntimeError(f"Silver sync to app failed ({response.status_code}): {response.text}")

result = response.json()
print(f"Silver Delta write: {len(rows)} rows. App sync result: {result}")