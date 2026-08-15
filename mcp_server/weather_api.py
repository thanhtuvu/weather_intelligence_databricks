import requests


NWS_BASE_URL = "https://api.weather.gov"

HEADERS = {
    "User-Agent": "weather-intelligence, tuvu.uwyo@gmail.com",
    "Accept": "application/geo+json",
}


class WeatherAPIError(Exception):
    """Raised when the weather API cannot fulfill a request."""


class WeatherAPI:
    """Adapter for retrieving weather data from the NWS API."""

    def _get(self, url):
        try:
            response = requests.get(
                url,
                headers=HEADERS,
                timeout=10
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

    def get_coordinates(self, location):
        """
        Resolve a city/state or ZIP code to latitude/longitude.

        Example:
            "Chicago, IL" -> (41.8781, -87.6298)
        """

        # We'll use the Nominatim geocoding API for city/state lookup.
        url = "https://nominatim.openstreetmap.org/search"

        params = {
            "q": location,
            "format": "json",
            "limit": 1,
        }

        headers = {
            "User-Agent": "weather-intelligence"
        }

        try:
            response = requests.get(
                url,
                params=params,
                headers=headers,
                timeout=10
            )
            response.raise_for_status()
            results = response.json()

        except requests.exceptions.Timeout as e:
            raise WeatherAPIError(
                "The location service request timed out."
            ) from e

        except requests.exceptions.ConnectionError as e:
            raise WeatherAPIError(
                "Unable to connect to the location service."
            ) from e

        except requests.exceptions.HTTPError as e:
            if (
                e.response is not None
                and e.response.status_code == 404
            ):
                raise WeatherAPIError(
                    f"The location service could not find "
                    f"the requested location: {location}"
                ) from e

            raise WeatherAPIError(
                "The location service returned an HTTP error."
            ) from e

        except requests.exceptions.RequestException as e:
            raise WeatherAPIError(
                "An error occurred while resolving the location."
            ) from e

        except ValueError as e:
            raise WeatherAPIError(
                "The location service returned an invalid response."
            ) from e

        if not results:
            raise WeatherAPIError(
                f"Could not find location: {location}"
            )

        return {
            "latitude": float(results[0]["lat"]),
            "longitude": float(results[0]["lon"]),
        }

    def get_forecast(self, location):
        """
        Get the NWS forecast for a location.

        Returns:
            The parsed forecast periods.
        """

        coordinates = self.get_coordinates(location)

        lat = coordinates["latitude"]
        lon = coordinates["longitude"]

        # First request: find the NWS forecast office/grid
        points_url = f"{NWS_BASE_URL}/points/{lat},{lon}"
        points = self._get(points_url)

        forecast_url = points["properties"]["forecast"]
        forecast = self._get(forecast_url)

        return {
            "location": location,
            "periods": forecast["properties"]["periods"],
        }

    def get_current_weather(self, location):
        """
        Get current weather conditions for a location.
        """

        coordinates = self.get_coordinates(location)

        lat = coordinates["latitude"]
        lon = coordinates["longitude"]

        points_url = f"{NWS_BASE_URL}/points/{lat},{lon}"
        points = self._get(points_url)

        station_url = points["properties"]["observationStations"]
        stations = self._get(station_url)

        if not stations["features"]:
            raise WeatherAPIError(
                f"No observation station found for {location}"
            )

        station_id = stations["features"][0]["properties"][
            "stationIdentifier"
        ]

        observation_url = (
            f"{NWS_BASE_URL}/stations/{station_id}/observations/latest"
        )

        observation = self._get(observation_url)
        properties = observation["properties"]
        temperature = properties.get("temperature")

        if temperature and temperature.get("value") is not None:
            temp_c = temperature["value"]
            temp_f = (temp_c * 9 / 5) + 32
        else:
            temp_f = None

        return {
            "location": location,
            "temperature": {
                "value": round(temp_f, 1)
                if temp_f is not None
                else None,
                "unit": "F",
            },
            "conditions": properties.get("textDescription"),
            "humidity": (
                round(
                    properties["relativeHumidity"]["value"],
                    1
                )
                if properties.get("relativeHumidity", {}).get("value")
                is not None
                else None
            ),
            "wind_speed": properties.get("windSpeed"),
            "wind_direction": properties.get("windDirection"),
        }