import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR))

from datetime import datetime
from fastmcp import FastMCP
from weather_api import WeatherAPI
from search import search_weather_documents, search_destination_documents
from lakebase import get_connection

mcp = FastMCP("Weather MCP Server")
weather_api = WeatherAPI()

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

        # Only use daytime periods as the start of each day
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

        # The following period is the corresponding night
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
    """Search stored destination/attraction documents using semantic similarity."""

    if top_k < 1 or top_k > 20:
        raise ValueError("top_k must be between 1 and 20")

    return search_destination_documents(
        query=query
        ,get_connection=get_connection
        ,top_k=top_k
    )
    
@mcp.tool()
def predict_umbrella_needed(location: str, date: str) -> dict:
    """
    An umbrella is recommended if either daytime or nighttime precipitation probability is greater than specified threshold.
    Date format: YYYY-MM-DD.
    """
    threshold = 50
    # Validate date format
    try:
        datetime.strptime(date, "%Y-%m-%d")
    except ValueError:
        raise ValueError("date must be in YYYY-MM-DD format")

    # Get the structured daily forecast
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

        # If neither period has precipitation information, we cannot make a recommendation.
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

        # Check whichever precipitation probabilities are available.
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