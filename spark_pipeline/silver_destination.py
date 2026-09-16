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

CATALOG = "weather_intelligence"
BRONZE_TABLE = f"{CATALOG}.bronze.destinations_raw"
SILVER_TABLE = f"{CATALOG}.silver.destinations_clean"
SCHEMA = "silver"
APP_SYNC_URL = "https://weather-intelligence-app-7474652422931165.aws.databricksapps.com/silver/sync"

# Matches destination_documents' shape exactly (minus synced_at)
spark.sql(f"CREATE SCHEMA IF NOT EXISTS {CATALOG}.{SCHEMA}")
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

# --- Hand off the Lakebase write + embedding step to the Flask/MCP app so Silver's job is just to hand it the
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

response = requests.post(
    APP_SYNC_URL
    ,json={"documents": documents}
    ,headers={"X-Sync-Token": sync_token}
    ,timeout=300  # generous on purpose — the app embeds the documents server-side before responding, which can take a while for a few hundred rows
)

if not response.ok:
    raise RuntimeError(f"Silver sync to app failed ({response.status_code}): {response.text}")

result = response.json()
print(f"Silver Delta write: {len(rows)} rows. App sync result: {result}")