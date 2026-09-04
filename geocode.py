import requests

NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
USER_AGENT = "weather-intelligence, tuvu.uwyo@gmail.com"


def resolve_location_name(location: str) -> tuple[float, float]:
    """Resolve a city/place name to (latitude, longitude) via Nominatim."""

    response = requests.get(
        NOMINATIM_URL
        ,params={
            "q": location
            ,"format": "json"
            ,"limit": 1
        }
        ,headers={"User-Agent": USER_AGENT}
        ,timeout=10
    )
    response.raise_for_status()
    results = response.json()

    if not results:
        raise ValueError(f"Could not resolve location: {location}")

    return (
        float(results[0]["lat"])
        ,float(results[0]["lon"])
    )


def resolve_location_input(location: str) -> tuple[float, float]:
    """Accept either "Seattle, WA" or "47.6062,-122.3321"."""

    location = location.strip()

    if "," in location:
        first, second = location.split(",", 1)
        try:
            lat = float(first.strip())
            lon = float(second.strip())
            if -90 <= lat <= 90 and -180 <= lon <= 180:
                return lat, lon
        except ValueError:
            pass

    return resolve_location_name(location)