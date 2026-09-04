import requests
from geocode import resolve_location_input

NWS_BASE_URL = "https://api.weather.gov"

HEADERS = {
    "User-Agent": "weather-intelligence, tuvu.uwyo@gmail.com"
    ,"Accept": "application/geo+json"
}


class WeatherAPIError(Exception):
    """Raised when the weather API cannot fulfill a request."""


class WeatherAPI:
    """Adapter for retrieving weather data from the NWS API."""

    def _get(self, url, params=None):
        try:
            response = requests.get(
                url
                ,params=params
                ,headers=HEADERS
                ,timeout=10
            )
            response.raise_for_status()
            return response.json()

        except requests.exceptions.Timeout as e:
            raise WeatherAPIError(
                "The weather service request timed out."
            ) from e

        except requests.exceptions.ConnectionError as e:
            raise WeatherAPIError(
                "Unable to connect to the weather service."
            ) from e

        except requests.exceptions.HTTPError as e:
            if (
                e.response is not None
                and e.response.status_code == 404
            ):
                raise WeatherAPIError(
                    "The requested weather location or data "
                    "could not be found."
                ) from e

            raise WeatherAPIError(
                "The weather service returned an HTTP error."
            ) from e

        except requests.exceptions.RequestException as e:
            raise WeatherAPIError(
                "An error occurred while contacting the weather service."
            ) from e

        except ValueError as e:
            raise WeatherAPIError(
                "The weather service returned an invalid response."
            ) from e

    def _resolve_coordinates(self, location: str) -> tuple[float, float]:
        try:
            return resolve_location_input(location)
        except ValueError as e:
            raise WeatherAPIError(f"Could not find location: {location}") from e
        except requests.exceptions.RequestException as e:
            raise WeatherAPIError(
                "An error occurred while resolving the location."
            ) from e

    def resolve_location(self, lat: float, lon: float) -> dict:
        """Resolve coordinates to an NWS grid point"""

        return self._get(f"{NWS_BASE_URL}/points/{lat},{lon}")

    def get_active_alerts(self, lat: float, lon: float) -> list[dict]:
        """Get active NWS alerts affecting the point"""

        data = self._get(
            f"{NWS_BASE_URL}/alerts/active"
            ,params={"point": f"{lat},{lon}"}
        )
        return data.get("features", [])

    def get_forecast_discussion(self, point_data: dict) -> dict:
        """Get the latest Area Forecast Discussion for the NWS office"""

        office = point_data["properties"]["cwa"]
        url = f"{NWS_BASE_URL}/products/types/AFD/locations/{office}/latest"
        return self._get(url)

    def get_forecast(self, location: str):
        """Get the NWS forecast for a location."""

        lat, lon = self._resolve_coordinates(location)
        points = self.resolve_location(lat, lon)
        forecast_url = points["properties"]["forecast"]
        forecast = self._get(forecast_url)

        return {
            "location": location
            ,"periods": forecast["properties"]["periods"]
        }

    def get_current_weather(self, location):
        """Get current weather conditions for a location."""

        lat, lon = self._resolve_coordinates(location)
        points = self.resolve_location(lat, lon)
        station_url = points["properties"]["observationStations"]
        stations = self._get(station_url)

        if not stations["features"]:
            raise WeatherAPIError(
                f"No observation station found for {location}"
            )

        station_id = stations["features"][0]["properties"]["stationIdentifier"]
        observation_url = f"{NWS_BASE_URL}/stations/{station_id}/observations/latest"
        observation = self._get(observation_url)
        properties = observation["properties"]
        temperature = properties.get("temperature")

        if temperature and temperature.get("value") is not None:
            temp_c = temperature["value"]
            temp_f = (temp_c * 9 / 5) + 32
        else:
            temp_f = None

        return {
            "location": location
            ,"temperature": {
                "value": round(temp_f, 1) if temp_f is not None else None
                ,"unit": "F"
            }
            ,"conditions": properties.get("textDescription")
            ,"humidity": (
                round(properties["relativeHumidity"]["value"], 1)
                if properties.get("relativeHumidity", {}).get("value") is not None
                else None
            )
            ,"wind_speed": properties.get("windSpeed")
            ,"wind_direction": properties.get("windDirection")
        }