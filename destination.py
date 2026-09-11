import hashlib
import json
from datetime import datetime, timezone

from destination_api import DestinationAPI

CATEGORY_MAP = {
    "entertainment.museum": ("museum", "indoor")
    ,"entertainment": ("entertainment", "indoor")
    ,"leisure.park": ("park", "outdoor")
    ,"natural": ("nature", "outdoor")
    ,"tourism.sights": ("landmark", "outdoor")
    ,"tourism.attraction.viewpoint": ("viewpoint", "outdoor")
    ,"catering": ("food_drink", "indoor")
    ,"commercial.shopping_mall": ("shopping", "indoor")
}

UNNAMED_PLACEHOLDER = "Unnamed"


def categorize(categories: list[str]) -> tuple[str, str]:
    matches = [
        CATEGORY_MAP[c]
        for c in sorted(categories, key=lambda c: c.count("."), reverse=True)
        if c in CATEGORY_MAP
    ]
    if not matches:
        return "other", "unknown"
    
    category, indoor_outdoor = matches[0]  # most specific tag still names the category

    if len({io for _, io in matches}) > 1:
        indoor_outdoor = "mixed"           # tags disagree — say so, don't guess
    return category, indoor_outdoor


def normalize_place(feature: dict, detail: dict | None, location: str) -> dict:
    props = feature.get("properties", {})
    categories = props.get("categories", [])
    category, indoor_outdoor = categorize(categories)

    detail_props = (detail or {}).get("properties", {})
    narrative_text = (
        detail_props.get("description")
        or detail_props.get("wiki_and_media", {}).get("description")
        or props.get("formatted", "")
    )

    document_id = props.get("place_id") or hashlib.sha256(
        f"{location}|{props.get('lat')}|{props.get('lon')}".encode("utf-8")
    ).hexdigest()

    return {
        "id": document_id
        ,"location": location
        ,"name": props.get("name") or UNNAMED_PLACEHOLDER
        ,"category": category
        ,"kinds": ",".join(categories)
        ,"indoor_outdoor": indoor_outdoor
        ,"latitude": props.get("lat")
        ,"longitude": props.get("lon")
        ,"address": props.get("address_line2") or props.get("formatted", "")
        ,"narrative_text": narrative_text
        ,"payload": {"feature": feature, "detail": detail}
        ,"synced_at": datetime.now(timezone.utc)
    }

DEFAULT_INGEST_CATEGORIES = (
    "tourism,entertainment,leisure.park,natural,catering,"
    "commercial.shopping_mall,tourism.sights"
)

def fetch_destinations(
    location: str
    ,api_key: str
    ,radius_m: int = 5000
    ,categories: str = DEFAULT_INGEST_CATEGORIES  # broad by default — this is ingestion, not user preference
    ,limit: int = 50
    ,fetch_details: bool = True
) -> list[dict]:

    client = DestinationAPI(api_key)
    features = client.get_places_radius(location, radius_m=radius_m, categories=categories, limit=limit)

    documents = []
    for feature in features:
        place_id = feature.get("properties", {}).get("place_id")
        detail = client.get_place_details(place_id) if (fetch_details and place_id) else None
        doc = normalize_place(feature, detail, location)

        if doc["name"] == UNNAMED_PLACEHOLDER:
            continue

        documents.append(doc)
        
    return documents


def upsert_documents(documents: list[dict]) -> int:
    """Upsert normalized destination documents into Lakebase."""

    import lakebase

    if not documents:
        return 0

    sql = """
        INSERT INTO destination_documents (
            id, location, name, category, kinds, indoor_outdoor,
            latitude, longitude, address, narrative_text,
            payload, synced_at
        )
        VALUES (
            %s, %s, %s, %s, %s, %s,
            %s, %s, %s, %s, %s,
            %s::jsonb, %s
        )
        ON CONFLICT (id) DO UPDATE SET
            name = EXCLUDED.name,
            category = EXCLUDED.category,
            kinds = EXCLUDED.kinds,
            indoor_outdoor = EXCLUDED.indoor_outdoor,
            address = EXCLUDED.address,
            narrative_text = EXCLUDED.narrative_text,
            payload = EXCLUDED.payload,
            synced_at = EXCLUDED.synced_at
    """

    rows = [
        (
            doc["id"], doc["location"], doc["name"], doc["category"]
            ,doc["kinds"], doc["indoor_outdoor"], doc["latitude"], doc["longitude"]
            ,doc["address"], doc["narrative_text"]
            ,json.dumps(doc["payload"]), doc["synced_at"]
        )
        for doc in documents
    ]

    with lakebase.get_connection() as conn:
        with conn.cursor() as cur:
            cur.executemany(sql, rows)
        conn.commit()

    return len(rows)