import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR))

from datetime import datetime
from fastmcp import FastMCP
from weather_api import WeatherAPI
from search import search_weather_documents, search_destination_documents
from routing import RoutingAPI
from itinerary import (
    ItineraryItemInput
    ,create_itinerary
    ,add_itinerary_items
    ,get_itinerary
    ,list_itineraries
    ,update_itinerary_status
)

from lakebase import get_connection
import os

mcp = FastMCP("Weather MCP Server")
weather_api = WeatherAPI()
routing_api = RoutingAPI(api_key=os.environ["ORS_API_KEY"])
DEFAULT_USER = "tuvu.uwyo@gmail.com"

def _weather_forecast(location: str, days: int = 3) -> list:
    """
    A Python helper function to get and transform the NWS forecast into a clean daily structure.
    """
    if days < 1 or days > 7:
        raise ValueError("days must be between 1 and 7")

    forecast = weather_api.get_forecast(location)
    periods = forecast["periods"]

    daily_forecasts = []

    for i, period in enumerate(periods):

        if not period.get("isDaytime"):
            continue

        date = period["startTime"][:10]
        high = period.get("temperature")
        unit = period.get("temperatureUnit")

        daytime_precipitation = (
            period
            .get("probabilityOfPrecipitation", {})
            .get("value")
        )

        daytime_conditions = period.get("shortForecast")

        low = None
        nighttime_precipitation = None
        nighttime_conditions = None

        if i + 1 < len(periods):
            next_period = periods[i + 1]

            if not next_period.get("isDaytime"):
                low = next_period.get("temperature")

                nighttime_precipitation = (
                    next_period
                    .get("probabilityOfPrecipitation", {})
                    .get("value")
                )

                nighttime_conditions = next_period.get("shortForecast")

        daily_forecasts.append({
            "date": date,
            "day": period.get("name"),
            "temperature_high": high,
            "temperature_low": low,
            "temperature_unit": unit,
            "daytime_precipitation_probability": daytime_precipitation,
            "nighttime_precipitation_probability": nighttime_precipitation,
            "daytime_conditions": daytime_conditions,
            "nighttime_conditions": nighttime_conditions,
        })

        if len(daily_forecasts) >= days:
            break

    return daily_forecasts


@mcp.tool()
def get_current_weather(location: str) -> dict:
    """Get the current weather conditions for a location."""
    return weather_api.get_current_weather(location)


@mcp.tool()
def get_forecast(location: str, days: int = 3) -> list:
    """Get a multi-day weather forecast with daily high/low temperatures."""
    return _weather_forecast(location, days)

@mcp.tool()
def search_weather(query: str, top_k: int = 5) -> list:
    """Search stored weather documents using semantic similarity."""
    if top_k < 1 or top_k > 20:
        raise ValueError("top_k must be between 1 and 20")

    return search_weather_documents(
        query=query,
        get_connection=get_connection,
        top_k=top_k,
    )

@mcp.tool()
def search_destinations(query: str, top_k: int = 5) -> list:
    """
    Search stored destination/attraction documents using semantic similarity.
    Use each result's attraction_id when saving an itinerary item via
    create_trip_itinerary or add_stops_to_itinerary — never invent one.
    title, item_type, and address are shown here to help you choose the
    right place; you don't need to pass them back when saving.
    """
    if top_k < 1 or top_k > 20:
        raise ValueError("top_k must be between 1 and 20")

    results = search_destination_documents(
        query=query
        ,get_connection=get_connection
        ,top_k=top_k
    )

    for result in results:
        result["attraction_id"] = result.pop("id")
        result["title"] = result.pop("name")
        result["item_type"] = result.pop("category")

    return results

@mcp.tool()
def get_travel_times(locations: list[str], mode: str = "walking") -> list:
    """
    Pairwise travel time/distance across a list of locations.
    Use this to check whether a day's planned stops are geographically
    realistic before committing to an itinerary.
    """

    if len(locations) < 2:
        raise ValueError("Provide at least 2 locations.")

    matrix = routing_api.get_travel_time_matrix(locations, mode)

    pairs = []
    for i, origin in enumerate(locations):
        for j, destination in enumerate(locations):
            if i == j:
                continue

            pairs.append({
                "from": origin
                ,"to": destination
                ,"distance_km": round(matrix["distances_meters"][i][j] / 1000, 1)
                ,"duration_min": round(matrix["durations_seconds"][i][j] / 60, 1)
            })

    return pairs

@mcp.tool()
def predict_umbrella_needed(location: str, date: str) -> dict:
    """
    An umbrella is recommended if either daytime or nighttime precipitation probability is greater than specified threshold.
    Date format: YYYY-MM-DD.
    """
    threshold = 50
    try:
        datetime.strptime(date, "%Y-%m-%d")
    except ValueError:
        raise ValueError("date must be in YYYY-MM-DD format")

    forecasts = _weather_forecast(location, days=7)

    for forecast in forecasts:

        if forecast["date"] != date:
            continue

        daytime_precipitation = (
            forecast["daytime_precipitation_probability"]
        )

        nighttime_precipitation = (
            forecast["nighttime_precipitation_probability"]
        )

        if (
            daytime_precipitation is None
            and nighttime_precipitation is None
        ):
            return {
                "location": location,
                "date": date,
                "umbrella_needed": "Unable to determine",
                "daytime_precipitation_probability": None,
                "nighttime_precipitation_probability": None,
                "reason": (
                    "Precipitation probability was not available for this date."
                )
            }

        precipitation_values = [value for value in [daytime_precipitation,nighttime_precipitation] if value is not None]

        max_precipitation = max(precipitation_values)
        umbrella_needed = "Yes" if max_precipitation > threshold else "No"

        if umbrella_needed == "Yes":
            reason = (f"Precipitation probability reaches {max_precipitation}%, which is above the {threshold}% umbrella threshold." )
                
        else:
            reason = (f"The highest precipitation probability is {max_precipitation}%, which is at or below the {threshold}% umbrella threshold.")   

        return {
            "location": location,
            "date": date,
            "umbrella_needed": umbrella_needed,
            "daytime_precipitation_probability": daytime_precipitation,
            "nighttime_precipitation_probability": nighttime_precipitation,
            "reason": reason
        }

    raise ValueError(
        f"No forecast found for {location} on {date}"
    )

@mcp.tool()
def create_trip_itinerary(
    destination: str
    ,start_date: str
    ,end_date: str
    ,items: list[ItineraryItemInput]
    ,preferences: dict
) -> dict:
    """
    Save a complete trip itinerary — header plus all its stops — in one call.
    preferences is required: if the user hasn't stated their interests yet,
    ask before calling this tool. Each item needs attraction_id (from
    search_destinations — never invent one), day_number, and sequence_order.

    Before saving, check get_forecast or predict_umbrella_needed for each
    day's date. If rain or another weather concern is likely — especially
    for outdoor item_types like park, nature, viewpoint, or landmark — write
    a short warning into that item's notes field, e.g. "60% chance of rain —
    consider an indoor alternative." Leave notes empty otherwise. notes is
    for weather warnings only — do not use it to describe the place itself.

    time_in_day and weather_context are optional. Either the whole plan
    saves, or none of it does.
    """

    return create_itinerary(
        user_id=DEFAULT_USER
        ,destination=destination
        ,start_date=start_date
        ,end_date=end_date
        ,items=items
        ,preferences=preferences
    )

@mcp.tool()
def add_stops_to_itinerary(itinerary_id: str, items: list[ItineraryItemInput]) -> int:
    """Add one or more stops to an already-saved itinerary — not for creating a new one."""
    return add_itinerary_items(itinerary_id, items)

@mcp.tool()
def get_trip_itinerary(itinerary_id: str) -> dict:
    """Fetch a saved itinerary and all its stops, in order."""

    itinerary = get_itinerary(itinerary_id)
    if itinerary is None:
        raise ValueError(f"No itinerary found with id {itinerary_id}")
    return itinerary


@mcp.tool()
def list_trip_itineraries() -> list:
    """List all saved itineraries."""

    return list_itineraries(DEFAULT_USER)


@mcp.tool()
def set_itinerary_status(itinerary_id: str, status: str) -> bool:
    """Update an itinerary's status. status must be one of: draft, confirmed, completed, cancelled."""

    return update_itinerary_status(itinerary_id, status)

if __name__ == "__main__":
    import uvicorn
    from starlette.applications import Starlette
    from starlette.routing import Mount

    mcp_app = mcp.http_app(path="/mcp")

    app = Starlette(
        routes=[
            Mount("/", app=mcp_app)
            ,Mount("/mcp", app=mcp_app)
        ]
        ,lifespan=mcp_app.lifespan
    )

    uvicorn.run(
        app
        ,host="0.0.0.0"
        ,port=8000
    )