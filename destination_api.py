import requests
from geocode import resolve_location_input

BASE_URL = "https://api.geoapify.com/v2"


class DestinationAPIError(Exception):
    """Raised when Geoapify cannot fulfill a request."""


class DestinationAPI:
    """Adapter for retrieving points-of-interest data from Geoapify Places API."""

    def __init__(self, api_key: str):
        self.api_key = api_key
        self.session = requests.Session()

    def _get(self, path: str, params: dict) -> dict:
        params = {**params, "apiKey": self.api_key}

        try:
            response = self.session.get(
                f"{BASE_URL}{path}"
                ,params=params
                ,timeout=15
            )
            response.raise_for_status()
            return response.json()

        except requests.exceptions.Timeout as e:
            raise DestinationAPIError("Geoapify request timed out.") from e

        except requests.exceptions.HTTPError as e:
            raise DestinationAPIError(f"Geoapify returned an HTTP error: {e}") from e

        except requests.exceptions.RequestException as e:
            raise DestinationAPIError("An error occurred while contacting Geoapify.") from e

    def get_places_radius(
        self
        ,location: str
        ,radius_m: int = 5000
        ,categories: str = "tourism,entertainment,leisure.park,natural,catering"
        ,limit: int = 50
    ) -> list[dict]:
        """
        Find points of interest near a location.
        `categories` is comma-separated, e.g. "entertainment.museum,leisure.park".
        Full taxonomy: apidocs.geoapify.com/docs/places
        """

        lat, lon = resolve_location_input(location)

        params = {
            "categories": categories
            ,"filter": f"circle:{lon},{lat},{radius_m}"
            ,"limit": limit
        }

        result = self._get("/places", params)
        return result.get("features", [])

    def get_place_details(self, place_id: str) -> dict:
        """Full details (description, contacts, wiki refs) for one place."""

        result = self._get("/place-details", {"id": place_id})
        features = result.get("features", [])
        return features[0] if features else {}