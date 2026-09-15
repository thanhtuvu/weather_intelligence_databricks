from pathlib import Path
import sys
import os
import json
from datetime import datetime, timezone

REPO_ROOT = Path(
    "/Workspace/Users/tuvu.uwyo@gmail.com/weather_intelligence_databricks"
)
sys.path.insert(0, str(REPO_ROOT))

from destination import DEFAULT_INGEST_CATEGORIES
from destination_api import DestinationAPI, DestinationAPIError

CATALOG = "weather_intelligence"
SCHEMA = "bronze"
TABLE = "destinations_raw"
TRACKED_TABLE = "tracked_locations"

# --- 1. Set up catalog, schema, Bronze table, and tracked_locations table (safe to re-run) ---
spark.sql(f"CREATE CATALOG IF NOT EXISTS {CATALOG}")
spark.sql(f"CREATE SCHEMA IF NOT EXISTS {CATALOG}.{SCHEMA}")

spark.sql(f"""
    CREATE TABLE IF NOT EXISTS {CATALOG}.{SCHEMA}.{TABLE} (
        place_id STRING
        ,location STRING NOT NULL
        ,raw_feature STRING NOT NULL
        ,raw_detail STRING
        ,fetched_at TIMESTAMP NOT NULL
        ,source STRING NOT NULL
    ) USING DELTA
""")

spark.sql(f"""
    CREATE TABLE IF NOT EXISTS {CATALOG}.{SCHEMA}.{TRACKED_TABLE} (
        location STRING NOT NULL
        ,added_at TIMESTAMP NOT NULL
        ,active BOOLEAN NOT NULL
    ) USING DELTA
""")

# --- 2. Read the active tracked locations
tracked = (
    spark.table(f"{CATALOG}.{SCHEMA}.{TRACKED_TABLE}")
    .where("active = true")
    .select("location")
    .collect()
)
locations = [row["location"] for row in tracked]

if not locations:
    print("No active locations in tracked_locations — nothing to do.")

else:
    print(f"Refreshing {len(locations)} tracked location(s): {locations}")

    # --- 3. Fetch raw features per location and MERGE into Bronze (matched by place_id) ---
    #     MERGE instead of append: a scheduled job re-runs the same tracked cities
    #     repeatedly, so append would pile up duplicate rows every run. MERGE
    #     refreshes existing rows and only inserts truly new ones.
    client = DestinationAPI(api_key=dbutils.secrets.get(scope="weather_intelligence", key="geoapify_api_key"))
    now = datetime.now(timezone.utc)

    all_rows = []
    for location in locations:
        try:
            features = client.get_places_radius(location, categories=DEFAULT_INGEST_CATEGORIES)
        except DestinationAPIError as e:
            print(f"Skipped {location}: {e}")
            continue

        print(f"Fetched {len(features)} raw features for {location}")
        all_rows.extend([
            {
                "place_id": feature.get("properties", {}).get("place_id")
                ,"location": location
                ,"raw_feature": json.dumps(feature)
                ,"fetched_at": now
                ,"source": "geoapify"
            }
            for feature in features
        ])

    if all_rows:
        updates_df = spark.createDataFrame(all_rows)
        updates_df.createOrReplaceTempView("bronze_updates")

        spark.sql(f"""
            MERGE INTO {CATALOG}.{SCHEMA}.{TABLE} AS target
            USING bronze_updates AS source
                ON target.place_id = source.place_id 
                AND target.location = source.location
            WHEN MATCHED THEN 
                UPDATE SET
                    target.raw_feature = source.raw_feature
                    ,target.fetched_at = source.fetched_at
                    ,target.source = source.source
            WHEN NOT MATCHED THEN 
                INSERT (place_id, location, raw_feature, fetched_at, source)
                VALUES (source.place_id, source.location, source.raw_feature, source.fetched_at, source.source)
        """)

        print(f"Merged {len(all_rows)} rows into {CATALOG}.{SCHEMA}.{TABLE}")

    # --- 4. Backfill raw_detail for any row still missing it, across all tracked locations ---
    location_list_sql = ",".join(f"'{loc}'" for loc in locations)
    rows_needing_detail = (
        spark.table(f"{CATALOG}.{SCHEMA}.{TABLE}")
        .where(f"location IN ({location_list_sql}) AND raw_detail IS NULL")
        .select("place_id")
        .collect()
    )
    place_ids = [row["place_id"] for row in rows_needing_detail if row["place_id"] is not None]

    if place_ids:
        print(f"Fetching details for {len(place_ids)} places — one API call per place, expect it to take a bit")

        detail_rows = []
        for place_id in place_ids:
            try:
                detail = client.get_place_details(place_id)
                detail_rows.append({
                    "place_id": place_id
                    ,"raw_detail": json.dumps(detail)
                })
            except DestinationAPIError as e:
                print(f"Skipped {place_id}: {e}")

        if detail_rows:
            detail_df = spark.createDataFrame(detail_rows)
            detail_df.createOrReplaceTempView("detail_updates")

            spark.sql(f"""
                MERGE INTO {CATALOG}.{SCHEMA}.{TABLE} AS target
                USING detail_updates AS source
                ON target.place_id = source.place_id
                WHEN MATCHED THEN UPDATE SET target.raw_detail = source.raw_detail
            """)

            print(f"Merged {len(detail_rows)} raw_detail rows")
    else:
        print("No rows missing raw_detail.")

    print("Bronze refresh complete.")