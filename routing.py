import requests
from geocode import resolve_location_input

BASE_URL = "https://api.openrouteservice.org"

PROFILE_MAP = {
    "walking": "foot-walking"
    ,"driving": "driving-car"
    ,"cycling": "cycling-regular"
}

class RoutingAPIError(Exception):
    """Raised when OpenRouteService cannot fulfill a request."""

class RoutingAPI:
    """Adapter for travel-time and distance queries via OpenRouteService."""

    def __init__(self, api_key: str):
        self.api_key = api_key
        self.session = requests.Session()
        self.session.headers.update({
            "Authorization": api_key
            ,"Content-Type": "application/json"
        })

    def _resolve_profile(self, mode: str) -> str:
        if mode not in PROFILE_MAP:
            raise ValueError(f"mode must be one of {list(PROFILE_MAP)}, got {mode!r}")
        return PROFILE_MAP[mode]

    def _post(self, path: str, body: dict) -> dict:
        try:
            response = self.session.post(
                f"{BASE_URL}{path}"
                ,json=body
                ,timeout=20
            )
            response.raise_for_status()
            return response.json()

        except requests.exceptions.Timeout as e:
            raise RoutingAPIError("OpenRouteService request timed out.") from e

        except requests.exceptions.HTTPError as e:
            raise RoutingAPIError(
                f"OpenRouteService returned an HTTP error: {e}"
            ) from e

        except requests.exceptions.RequestException as e:
            raise RoutingAPIError(
                "An error occurred while contacting OpenRouteService."
            ) from e

    def get_travel_time(self, origin: str, destination: str, mode: str = "walking") -> dict:
        profile = self._resolve_profile(mode)
        origin_lat, origin_lon = resolve_location_input(origin)
        dest_lat, dest_lon = resolve_location_input(destination)

        body = {
            "coordinates": [
                [origin_lon, origin_lat]
                ,[dest_lon, dest_lat]
            ]
        }

        result = self._post(f"/v2/directions/{profile}", body)
        route = result["routes"][0]["summary"]

        distance_meters = route["distance"]
        duration_seconds = route["duration"]

        return {
            "origin": origin
            ,"destination": destination
            ,"mode": mode
            ,"distance_meters": distance_meters
            ,"duration_seconds": duration_seconds
            ,"distance_km": round(distance_meters / 1000, 2)
            ,"duration_minutes": round(duration_seconds / 60, 1)
        }

    def get_travel_time_matrix(self, locations: list[str], mode: str = "walking") -> dict:
        """Returns a matrix of travel times between all pairs of locations."""

        profile = self._resolve_profile(mode)
        coords = [resolve_location_input(loc) for loc in locations]
        coords = [[lon, lat] for lat, lon in coords]

        result = self._post(
            f"/v2/matrix/{profile}"
            ,{"locations": coords, "metrics": ["distance", "duration"]}
        )

        return {
            "locations": locations
            ,"mode": mode
            ,"durations_seconds": result["durations"]
            ,"distances_meters": result["distances"]
        }