"""Weather client for PlanePortal Pi.

Fetches current conditions from Open-Meteo (free, no API key).
Returns aviation-relevant data: temperature, wind, visibility, cloud cover.
"""

import time
import requests

METEO_URL = "https://api.open-meteo.com/v1/forecast"
NOMINATIM_URL = "https://nominatim.openstreetmap.org/reverse"


class WeatherClient:
    def __init__(self, config):
        self._config = config
        self._session = requests.Session()
        self._cache = None
        self._cache_time = 0
        self._cache_ttl = 600  # refresh weather every 10 minutes
        self._location_name = None
        self._location_coords = None  # (lat, lon) that was geocoded

    def _resolve_location(self, lat, lon):
        """Reverse geocode coordinates to a human-readable place name."""
        coords = (round(lat, 4), round(lon, 4))
        if self._location_name and self._location_coords == coords:
            return self._location_name
        try:
            resp = self._session.get(
                NOMINATIM_URL,
                params={
                    "lat": lat, "lon": lon,
                    "format": "json", "zoom": 10,
                },
                headers={"User-Agent": "PlanePortal-Pi/1.0"},
                timeout=10,
            )
            if resp.status_code < 400:
                addr = resp.json().get("address", {})
                city = (addr.get("city") or addr.get("town")
                        or addr.get("village") or addr.get("county") or "")
                state = addr.get("state", "")
                if city and state:
                    self._location_name = f"{city}, {state}"
                elif city:
                    self._location_name = city
                else:
                    self._location_name = None
                self._location_coords = coords
        except Exception:
            pass
        return self._location_name

    def fetch(self):
        now = time.monotonic()
        if self._cache and now - self._cache_time < self._cache_ttl:
            return self._cache

        try:
            resp = self._session.get(
                METEO_URL,
                params={
                    "latitude": self._config.home_latitude,
                    "longitude": self._config.home_longitude,
                    "current": ",".join([
                        "temperature_2m",
                        "relative_humidity_2m",
                        "apparent_temperature",
                        "wind_speed_10m",
                        "wind_direction_10m",
                        "wind_gusts_10m",
                        "cloud_cover",
                        "visibility",
                        "weather_code",
                    ]),
                    "temperature_unit": "fahrenheit",
                    "wind_speed_unit": "kn",
                    "timezone": "auto",
                },
                timeout=10,
            )
            if resp.status_code >= 400:
                return self._cache

            payload = resp.json()
            data = payload.get("current", {})
            lat = self._config.home_latitude
            lon = self._config.home_longitude
            place = self._resolve_location(lat, lon)
            fallback = f"{abs(lat):.2f}{'N' if lat >= 0 else 'S'}, {abs(lon):.2f}{'W' if lon < 0 else 'E'}"
            self._cache = {
                "location": place or fallback,
                "temp_f": data.get("temperature_2m"),
                "feels_like_f": data.get("apparent_temperature"),
                "humidity_pct": data.get("relative_humidity_2m"),
                "wind_kts": data.get("wind_speed_10m"),
                "wind_dir": data.get("wind_direction_10m"),
                "wind_gusts_kts": data.get("wind_gusts_10m"),
                "cloud_cover_pct": data.get("cloud_cover"),
                "visibility_m": data.get("visibility"),
                "weather_code": data.get("weather_code"),
                "condition": _weather_condition(data.get("weather_code")),
            }
            self._cache_time = now
            return self._cache
        except Exception:
            return self._cache


def _weather_condition(code):
    """Map WMO weather code to short description."""
    if code is None:
        return "Unknown"
    conditions = {
        0: "Clear", 1: "Mostly Clear", 2: "Partly Cloudy", 3: "Overcast",
        45: "Fog", 48: "Rime Fog",
        51: "Light Drizzle", 53: "Drizzle", 55: "Heavy Drizzle",
        56: "Freezing Drizzle", 57: "Freezing Drizzle",
        61: "Light Rain", 63: "Rain", 65: "Heavy Rain",
        66: "Freezing Rain", 67: "Freezing Rain",
        71: "Light Snow", 73: "Snow", 75: "Heavy Snow",
        77: "Snow Grains",
        80: "Light Showers", 81: "Showers", 82: "Heavy Showers",
        85: "Snow Showers", 86: "Heavy Snow Showers",
        95: "Thunderstorm", 96: "Thunderstorm + Hail", 99: "Thunderstorm + Hail",
    }
    return conditions.get(code, "Unknown")
