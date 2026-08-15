# Weather Prediction MCP Server + Agent

## 1. Overview

This project builds a weather-focused MCP server and a Databricks Agent Bricks agent that can answer natural-language weather questions and make simple weather recommendations.

The MCP server exposes three weather tools:

- Current weather conditions
- Multi-day weather forecasts
- Umbrella recommendations based on precipitation probability

The MCP server is deployed as a Databricks App and registered as an external MCP server in the Databricks workspace. An Agent Bricks agent uses the MCP tools to answer natural-language questions.

## 2. Architecture

```text
User
  │
  ▼
Databricks Agent Bricks
  │
  │ External MCP
  ▼
Weather MCP Server
(Databricks App)
  │
  ▼
Weather API Adapter
(weather_api.py)
  │
  ▼
National Weather Service API
```

The responsibilities are separated into two main layers:

- `server.py` contains the MCP tools and weather recommendation logic.
- `weather_api.py` acts as the adapter for the external weather APIs and handles HTTP requests, response parsing, and API errors.

## 3. Weather API

### National Weather Service (NWS)

This project uses the National Weather Service API: https://api.weather.gov/

The NWS API was selected because it is free, does not require an API key, provides official NOAA weather data, and provides current observations and forecasts.

The NWS API is US-only, so the application currently supports locations that can be resolved to NWS-supported US weather data.

### Location Resolution

The application uses the Nominatim geocoding service to convert a user-provided location into latitude and longitude coordinates. Those coordinates are then passed to the NWS API.

## 4. MCP Tools

The MCP server exposes three tools using FastMCP and `@mcp.tool`.

### `get_current_weather(location)`

Returns current temperature, conditions, humidity, wind speed, and wind direction.

Example:

> What's the current weather in Seattle?

### `get_forecast(location, days)`

Returns a structured multi-day forecast including date, high/low temperature, daytime and nighttime precipitation probability, and daytime/nighttime conditions.

The `days` parameter accepts values from 1 to 7.

Example:

> What's the 3-day forecast for New York City?

### `predict_umbrella_needed(location, date)`

Provides a simple recommendation based on precipitation probability.

The tool:

1. Retrieves the 7-day forecast.
2. Finds the requested date.
3. Checks daytime and nighttime precipitation probabilities.
4. Uses the higher available probability.
5. Compares it with the 50% umbrella threshold.
6. Returns `"Yes"` or `"No"` with the relevant probabilities and reasoning.

The recommendation is derived from forecast data rather than directly reported by the weather service.

Example:

> Will I need an umbrella in Seattle tomorrow?

## 5. MCP Server

The MCP server is built using FastMCP and uses the streamable HTTP pattern.

The application is deployed as a Databricks App.

```text
mcp_server/
├── server.py
├── weather_api.py
├── requirements.txt
└── app.yaml
```

### `server.py`

Contains the FastMCP server configuration, MCP tool definitions, forecast transformation, and umbrella recommendation logic.

### `weather_api.py`

Acts as the weather API adapter. It contains location resolution, NWS API requests, HTTP response handling, response parsing, and API error handling.

No raw `requests` calls are made inside the MCP tool functions.

## 6. Agent Bricks Agent

The deployed MCP server was registered as an external MCP server in the Databricks workspace.

The Agent Bricks agent uses the MCP server as an external tool and calls the weather tools based on the user's natural-language request.

The agent uses these guardrails:

### Weather data only

> Only provide weather-related information based on available weather tools. Do not fabricate weather conditions, forecasts, or recommendations.

### Respect tool results

> Treat tool results as the authoritative source for current and forecast weather information. If the tool cannot provide the requested information, say so rather than guessing.

### Recommendation transparency

> When making a weather recommendation, explain the relevant weather conditions briefly. Do not present a derived recommendation as if it were directly reported by the weather service.

The agent was tested through the Agent Bricks Playground and successfully used the MCP tools.

## 7. Error Handling

Error handling is implemented primarily in the weather API adapter.

A custom `WeatherAPIError` exception converts lower-level request failures into application-level errors.

The adapter handles:

- Request timeouts
- Connection failures
- HTTP errors
- Invalid API responses
- Locations that cannot be resolved
- Missing weather observation stations
- Forecasts unavailable for the requested date

For HTTP errors, the response status code is checked when available. For example, a `404` can be converted into a meaningful location/data-not-found error.

The MCP tool does not expose raw Python stack traces to the user.

For an invalid location such as:

> What's the current weather in Narnia?

the agent does not fabricate weather information. Instead, it explains that weather data could not be retrieved and asks for a valid location.

## 8. How to Run / Deploy

### 1. Deploy the MCP server

Deploy the `mcp_server` application as a Databricks App using `app.yaml` and `requirements.txt`.

### 2. Register the MCP server

In the Databricks workspace:

```text
AI Gateway
    → MCPs
    → Add MCP / Register external MCP
```

Register the deployed MCP server using its streamable HTTP endpoint.

### 3. Configure the Agent Bricks agent

Configure an Agent Bricks agent and add the registered weather MCP server as an external tool.

Available tools:

- `get_current_weather`
- `get_forecast`
- `predict_umbrella_needed`

### 4. Test through Playground

Use the Agent Bricks Playground to test natural-language weather questions and verify that the agent calls the appropriate MCP tools.

## 9. Example Questions

### Current weather

> What's the current weather in Seattle?

The agent calls `get_current_weather` and summarizes the returned weather conditions.

### Multi-day forecast

> Give me the 3-day forecast for New York City.

The agent calls `get_forecast` and summarizes the forecast information.

### Weather recommendation

> Will I need an umbrella in Seattle tomorrow?

The agent calls `predict_umbrella_needed` and explains the recommendation using precipitation probabilities.

### Invalid location

> What's the current weather in Narnia?

The weather API cannot resolve the location, so the agent explains that weather data cannot be retrieved instead of fabricating weather information.

## 10. Limitations

- **US locations only:** The National Weather Service API is designed for US weather data.
- **Forecast horizon:** The forecast tool currently supports up to 7 days.
- **External API dependency:** Weather information depends on the availability of NWS and Nominatim.
- **Simple recommendation logic:** The umbrella recommendation uses a single 50% precipitation-probability threshold.
- **No historical weather:** Historical weather lookup is not implemented.
- **No severe weather tool:** Severe weather alerts are not currently exposed as an MCP tool.
