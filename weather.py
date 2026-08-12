import hashlib
from datetime import datetime, timezone
import requests
import json
import lakebase

BASE_URL = "https://api.weather.gov"

# Replace with your own identifier/contact.
USER_AGENT = "weather-intelligence, tuvu.uwyo@gmail.com"
HEADERS = {
    "User-Agent": USER_AGENT,
    "Accept": "application/geo+json",
}

class WeatherClient:
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update(HEADERS)

    def _get(self, url, params=None):
        response = self.session.get(
            url,
            params=params,
            timeout=30,
        )
        response.raise_for_status()
        return response.json()

    def resolve_location_name(self, location: str) -> tuple[float, float]:
        """
        Resolve a city/state location to latitude/longitude.
        Example:
            "Chicago, IL" -> (41.8781, -87.6298)
        """

        # We'll use the Nominatim geocoding API for city/state lookup.
        response = self.session.get(
            "https://nominatim.openstreetmap.org/search",
            params={
                "q": location,
                "format": "json",
                "limit": 1,
            },
            timeout=30,
        )

        response.raise_for_status()
        results = response.json()
        if not results:
            raise ValueError(f"Could not resolve location: {location}")
        return (
            float(results[0]["lat"]),
            float(results[0]["lon"]),
        )

    def resolve_location_input(self, location: str) -> tuple[float, float]:
        """
        Accept either:
        - "Chicago, IL"
        - "41.8781,-87.6298"
        """

        location = location.strip()

        # Try lat/lon first
        if "," in location:
            first, second = location.split(",", 1)
            try:
                lat = float(first.strip())
                lon = float(second.strip())
                if -90 <= lat <= 90 and -180 <= lon <= 180:
                    return lat, lon
            except ValueError:
                pass

        # Otherwise treat it as city/state
        return self.resolve_location_name(location)
    
    def resolve_location(self, lat: float, lon: float) -> dict:
        """Resolve coordinates to an NWS grid point."""
        return self._get(f"{BASE_URL}/points/{lat},{lon}")

    def get_active_alerts(self, lat: float, lon: float) -> list[dict]:
        """Get active NWS alerts affecting the point."""
        data = self._get(
            f"{BASE_URL}/alerts/active",
            params={"point": f"{lat},{lon}"},
        )
        return data.get("features", [])

    def get_forecast_discussion(self, point_data: dict) -> dict:
        """Get the latest Area Forecast Discussion for the NWS office."""
        office = point_data["properties"]["cwa"]
        url = f"{BASE_URL}/products/types/AFD/locations/{office}/latest"
        return self._get(url)

    def normalize_alert(
        self,
        alert: dict,
        location: str,
    ) -> dict:
        props = alert.get("properties", {})

        return {
            "id": props.get("id") or alert.get("id"),
            "location": location,
            "source_type": "alert",
            "headline": props.get("headline") or props.get("event"),
            "narrative_text": self._combine_text(
                props.get("description"),
                props.get("instruction"),
            ),
            "issued_at": props.get("sent"),
            "effective_at": props.get("effective"),
            "payload": alert,
            "synced_at": datetime.now(timezone.utc),
        }

    def normalize_forecast_discussion(
        self,
        discussion: dict,
        location: str,
    ) -> dict:
        """Normalize an NWS Area Forecast Discussion."""

        issued_at = discussion.get("issuanceTime")

        stable_key = (
            f"{location}|"
            f"AFD|"
            f"{issued_at}"
        )

        document_id = hashlib.sha256(
            stable_key.encode("utf-8")
        ).hexdigest()

        return {
            "id": document_id,
            "location": location,
            "source_type": "forecast",
            "headline": discussion.get("productName") or "Area Forecast Discussion",
            "narrative_text": discussion.get("productText"),
            "issued_at": issued_at,
            "effective_at": issued_at,
            "payload": discussion,
            "synced_at": datetime.now(timezone.utc),
        }

    @staticmethod
    def _combine_text(*parts):
        parts = [p.strip() for p in parts if p]
        return "\n\n".join(parts)

    def fetch_location(
        self,
        lat: float,
        lon: float,
        location: str,
    ) -> list[dict]:
        """Fetch and normalize weather documents for one location."""

        point_data = self.resolve_location(lat, lon)

        # Active alerts
        alerts = self.get_active_alerts(lat, lon)
        documents = [
            self.normalize_alert(alert, location)
            for alert in alerts
        ]

        # Area Forecast Discussion
        discussion = self.get_forecast_discussion(point_data)
        if discussion:
            documents.append(
                self.normalize_forecast_discussion(
                    discussion,
                    location,
                )
            )

        return documents
    
    def fetch_location_input(
        self,
        location: str,
    ) -> list[dict]:
        """Resolve a location input and fetch its weather documents."""

        lat, lon = self.resolve_location_input(location)

        return self.fetch_location(
            lat=lat,
            lon=lon,
            location=location,
        )
        
def upsert_documents(documents: list[dict]) -> int:
    """Upsert normalized weather documents into Lakebase."""

    if not documents:
        return 0

    sql = """
        INSERT INTO weather_documents (
            id,
            location,
            source_type,
            headline,
            narrative_text,
            issued_at,
            effective_at,
            payload,
            synced_at
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
            doc["id"],
            doc["location"],
            doc["source_type"],
            doc["headline"],
            doc["narrative_text"],
            doc["issued_at"],
            doc["effective_at"],
            json.dumps(doc["payload"]),
            doc["synced_at"],
        )
        for doc in documents
    ]

    with lakebase.get_connection() as conn:
        with conn.cursor() as cur:
            cur.executemany(sql, rows)
        conn.commit()

    return len(rows)