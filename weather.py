import hashlib
import json
from datetime import datetime, timezone
import lakebase
from weather_api import WeatherAPI


class WeatherClient:
    def __init__(self):
        self.api = WeatherAPI()

    def normalize_alert(self, alert: dict, location: str) -> dict:
        props = alert.get("properties", {})

        return {
            "id": props.get("id") or alert.get("id")
            ,"location": location
            ,"source_type": "alert"
            ,"headline": props.get("headline") or props.get("event")
            ,"narrative_text": self._combine_text(
                props.get("description")
                ,props.get("instruction")
            )
            ,"issued_at": props.get("sent")
            ,"effective_at": props.get("effective")
            ,"payload": alert
            ,"synced_at": datetime.now(timezone.utc)
        }

    def normalize_forecast_discussion(self, discussion: dict, location: str) -> dict:
        """Normalize an NWS Area Forecast Discussion."""

        issued_at = discussion.get("issuanceTime")
        stable_key = f"{location}|AFD|{issued_at}"
        document_id = hashlib.sha256(stable_key.encode("utf-8")).hexdigest()

        return {
            "id": document_id
            ,"location": location
            ,"source_type": "forecast"
            ,"headline": discussion.get("productName") or "Area Forecast Discussion"
            ,"narrative_text": discussion.get("productText")
            ,"issued_at": issued_at
            ,"effective_at": issued_at
            ,"payload": discussion
            ,"synced_at": datetime.now(timezone.utc)
        }

    @staticmethod
    def _combine_text(*parts):
        parts = [p.strip() for p in parts if p]
        return "\n\n".join(parts)

    def fetch_location(self, lat: float, lon: float, location: str) -> list[dict]:
        """Fetch and normalize weather documents for one location.
        WeatherClient class no longer makes any HTTP calls itself — that logic moved out to weather_api.py. 
        But fetch_location still needs the actual data (grid point, alerts, forecast discussion) to normalize it. 
        So it borrows WeatherAPI's methods to go get that data
        """

        point_data = self.api.resolve_location(lat, lon)
        alerts = self.api.get_active_alerts(lat, lon)
        documents = [
            self.normalize_alert(alert, location)
            for alert in alerts
        ]

        discussion = self.api.get_forecast_discussion(point_data)
        if discussion:
            documents.append(
                self.normalize_forecast_discussion(discussion, location)
            )

        return documents

    def fetch_location_input(self, location: str) -> list[dict]:
        """Resolve a location input and fetch its weather documents."""

        from geocode import resolve_location_input
        lat, lon = resolve_location_input(location)

        return self.fetch_location(lat=lat, lon=lon, location=location)


def upsert_documents(documents: list[dict]) -> int:
    """Upsert normalized weather documents into Lakebase."""

    if not documents:
        return 0

    sql = """
        INSERT INTO weather_documents (
            id, location, source_type, headline, narrative_text,
            issued_at, effective_at, payload, synced_at
        )
        VALUES (
            %s, %s, %s, %s, %s,
            %s, %s, %s::jsonb, %s
        )
        ON CONFLICT (id) DO UPDATE SET
            location = EXCLUDED.location,
            source_type = EXCLUDED.source_type,
            headline = EXCLUDED.headline,
            narrative_text = EXCLUDED.narrative_text,
            issued_at = EXCLUDED.issued_at,
            effective_at = EXCLUDED.effective_at,
            payload = EXCLUDED.payload,
            synced_at = EXCLUDED.synced_at
    """

    rows = [
        (
            doc["id"], doc["location"], doc["source_type"], doc["headline"]
            ,doc["narrative_text"], doc["issued_at"], doc["effective_at"]
            ,json.dumps(doc["payload"]), doc["synced_at"]
        )
        for doc in documents
    ]

    with lakebase.get_connection() as conn:
        with conn.cursor() as cur:
            cur.executemany(sql, rows)
        conn.commit()

    return len(rows)