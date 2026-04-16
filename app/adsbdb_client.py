"""ADSBDB aircraft metadata client for PlanePortal Pi.

Enriches aircraft with registration, type, route, and airline information.
"""

import time
from urllib.parse import quote

import requests


class ADSBDBClient:
    def __init__(self, config):
        self._config = config
        self._session = requests.Session()
        self._cache = {}
        self._cooldown_until = 0

    def _cached(self, mode_s, now):
        cached = self._cache.get(mode_s)
        if not cached:
            return None
        if now >= cached["expires_at"]:
            return None
        return cached["value"]

    def enrich_aircraft(self, mode_s, callsign=None):
        if not mode_s:
            return None

        mode_s = str(mode_s).upper()
        now = time.monotonic()
        cached = self._cached(mode_s, now)
        if cached is not None:
            return cached
        if now < self._cooldown_until:
            return None

        url = f"https://api.adsbdb.com/v0/aircraft/{quote(mode_s)}"
        clean_callsign = str(callsign or "").strip()
        if clean_callsign:
            url += f"?callsign={quote(clean_callsign)}"

        try:
            response = self._session.get(
                url, headers={"Accept": "application/json"}, timeout=10
            )
        except requests.RequestException:
            return None

        if response.status_code == 429:
            self._cooldown_until = now + 60
            return None
        if response.status_code >= 400:
            return None

        try:
            payload = response.json()
        except ValueError:
            return None

        if not isinstance(payload, dict):
            return None

        value = payload.get("response")
        if not isinstance(value, dict):
            value = None

        self._cache[mode_s] = {
            "value": value,
            "expires_at": now + self._config.adsb_cache_seconds,
        }
        return value
