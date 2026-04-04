import time


def _url_encode(value):
    safe = "-_.~"
    output = ""
    for char in str(value):
        codepoint = ord(char)
        is_ascii_alnum = (
            48 <= codepoint <= 57
            or 65 <= codepoint <= 90
            or 97 <= codepoint <= 122
        )
        if is_ascii_alnum or char in safe:
            output += char
        else:
            output += "%{:02X}".format(codepoint)
    return output


class ADSBDBClient:
    def __init__(self, config, session_provider):
        self._config = config
        self._session_provider = session_provider
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

        url = "https://api.adsbdb.com/v0/aircraft/{}".format(_url_encode(mode_s))
        if callsign is None:
            clean_callsign = ""
        elif isinstance(callsign, str):
            clean_callsign = callsign.strip()
        else:
            clean_callsign = str(callsign).strip()
        if clean_callsign:
            url += "?callsign={}".format(_url_encode(clean_callsign))

        response = self._session_provider().get(url, headers={"Accept": "application/json"})
        try:
            if response.status_code == 429:
                self._cooldown_until = now + 60
                return None
            if response.status_code >= 400:
                return None
            payload = response.json()
        finally:
            response.close()

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