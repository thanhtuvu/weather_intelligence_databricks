from pathlib import Path
import sys
import json
import os
# from pprint import pprint
# os.environ["PGHOST"] = "ep-polished-silence-d8t2cf3b.database.us-east-2.cloud.databricks.com"
# os.environ["LAKEBASE_ENDPOINT"] = "projects/weather-intelligence/branches/production/endpoints/primary"
# os.environ["PGUSER"] ="tuvu.uwyo@gmail.com"

REPO_ROOT = Path(
    "/Workspace/Users/tuvu.uwyo@gmail.com/weather_intelligence_databricks"
)
sys.path.insert(0, str(REPO_ROOT))

from destination import normalize_place, upsert_documents, UNNAMED_PLACEHOLDER
from datetime import datetime, timezone
import json
from pyspark.sql.functions import udf
from pyspark.sql.types import StructType, StructField, StringType, DoubleType

CATALOG = "weather_intelligence"
BRONZE_TABLE = f"{CATALOG}.bronze.destinations_raw"
SILVER_TABLE = f"{CATALOG}.silver.destinations_clean"
SCHEMA = "silver"
spark.sql(f"CREATE SCHEMA IF NOT EXISTS {CATALOG}.{SCHEMA}")

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

#Write to silver schema:
silver_df.write.mode("overwrite").saveAsTable(SILVER_TABLE)

#Write to Lakebase table:
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
        ,"synced_at": now
    }
    for row in rows
]

upsert_documents(documents)

#Write to Embedding table:
from embeddings import embed_unembedded_documents
import lakebase

embedded = embed_unembedded_documents(
    lakebase.get_connection
    ,documents_table="destination_documents"
    ,embeddings_table="destination_embeddings"
)
