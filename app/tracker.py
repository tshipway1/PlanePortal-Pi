"""Flight tracking, radius filtering, and distance math for PlanePortal Pi.

Maintains a rolling registry of recently seen aircraft and produces snapshots
for the UI to render.
"""

import math
import time

STATE_ICAO24 = 0
STATE_CALLSIGN = 1
STATE_COUNTRY = 2
STATE_LONGITUDE = 5
STATE_LATITUDE = 6
STATE_BARO_ALTITUDE = 7
STATE_ON_GROUND = 8
STATE_VELOCITY = 9
STATE_HEADING = 10
STATE_VERTICAL_RATE = 11
STATE_GEO_ALTITUDE = 13
STATE_LAST_CONTACT = 4
STATE_CATEGORY = 17

EARTH_RADIUS_MILES = 3958.8

CATEGORY_NAMES = {
    2: "Light aircraft",
    3: "Small aircraft",
    4: "Large aircraft",
    5: "High vortex",
    6: "Heavy aircraft",
    7: "Performance",
    8: "Rotorcraft",
    9: "Glider",
    12: "Ultralight",
    14: "UAV",
}


def haversine_miles(lat1, lon1, lat2, lon2):
    lat1_r = math.radians(lat1)
    lon1_r = math.radians(lon1)
    lat2_r = math.radians(lat2)
    lon2_r = math.radians(lon2)

    dlat = lat2_r - lat1_r
    dlon = lon2_r - lon1_r

    a = (
        math.sin(dlat / 2) ** 2
        + math.cos(lat1_r) * math.cos(lat2_r) * math.sin(dlon / 2) ** 2
    )
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return EARTH_RADIUS_MILES * c


def bearing_degrees(lat1, lon1, lat2, lon2):
    lat1_r = math.radians(lat1)
    lat2_r = math.radians(lat2)
    dlon = math.radians(lon2 - lon1)

    x = math.sin(dlon) * math.cos(lat2_r)
    y = math.cos(lat1_r) * math.sin(lat2_r) - math.sin(lat1_r) * math.cos(
        lat2_r
    ) * math.cos(dlon)

    return (math.degrees(math.atan2(x, y)) + 360) % 360


def bounding_box(latitude, longitude, radius_miles, margin=1.15):
    padded = radius_miles * margin
    lat_delta = padded / 69.0
    cos_lat = math.cos(math.radians(latitude))
    if abs(cos_lat) < 0.01:
        lon_delta = 180
    else:
        lon_delta = padded / (69.172 * cos_lat)

    return {
        "lamin": latitude - lat_delta,
        "lomin": longitude - lon_delta,
        "lamax": latitude + lat_delta,
        "lomax": longitude + lon_delta,
    }


def _clean_callsign(value):
    if value is None:
        return "Unknown"
    value = str(value).strip()
    return value if value else "Unknown"


def _meters_to_feet(value):
    if value is None:
        return None
    return int(value * 3.28084)


def _meters_per_second_to_knots(value):
    if value is None:
        return None
    return int(value * 1.94384)


def _meters_per_second_to_fpm(value):
    if value is None:
        return None
    return int(value * 196.85)


class FlightTracker:
    def __init__(self, config):
        self._config = config
        self._registry = {}
        self._has_seen_aircraft = False

    def current_bounds(self):
        return bounding_box(
            self._config.home_latitude,
            self._config.home_longitude,
            self._config.radius_miles,
        )

    def ingest_states(self, states, now=None):
        if now is None:
            now = time.monotonic()
        for state in states:
            record = self._normalize_state(state, now)
            if record is None:
                continue

            previous = self._registry.get(record["icao24"])
            if previous and previous.get("enrichment"):
                record["enrichment"] = previous["enrichment"]

            self._registry[record["icao24"]] = record
            self._has_seen_aircraft = True

        self._prune(now)
        return self.snapshot(now)

    def attach_enrichment(self, icao24, enrichment):
        record = self._registry.get(icao24)
        if record:
            record["enrichment"] = enrichment

    def snapshot(self, now=None):
        if now is None:
            now = time.monotonic()
        live_threshold = max(45, self._config.refresh_seconds + 15)
        records = []
        live_count = 0
        for record in self._registry.values():
            age = int(now - record["last_seen_monotonic"])
            record["age_seconds"] = age
            record["is_live"] = age <= live_threshold
            record["status_text"] = "LIVE" if record["is_live"] else "RECENT"
            if record["is_live"]:
                live_count += 1
            records.append(record)

        records.sort(key=self._sort_key)

        return {
            "records": records,
            "featured": records[0] if records else None,
            "others": records[1:4],
            "live_count": live_count,
            "recent_count": max(0, len(records) - live_count),
            "has_seen_aircraft": self._has_seen_aircraft,
        }

    def _prune(self, now):
        stale = [
            k
            for k, v in self._registry.items()
            if now - v["last_seen_monotonic"] > self._config.recent_window_seconds
        ]
        for k in stale:
            del self._registry[k]

    def _sort_key(self, record):
        return (
            0 if record.get("is_live") else 1,
            record["distance_tenths"],
            record.get("age_seconds", 0),
            record["callsign"],
        )

    def _normalize_state(self, state, now):
        if not state or len(state) <= STATE_CATEGORY:
            return None

        latitude = state[STATE_LATITUDE]
        longitude = state[STATE_LONGITUDE]
        if latitude is None or longitude is None:
            return None
        if state[STATE_ON_GROUND]:
            return None

        distance = haversine_miles(
            self._config.home_latitude,
            self._config.home_longitude,
            latitude,
            longitude,
        )
        if distance > self._config.radius_miles:
            return None

        alt_m = state[STATE_GEO_ALTITUDE]
        if alt_m is None:
            alt_m = state[STATE_BARO_ALTITUDE]

        return {
            "icao24": state[STATE_ICAO24],
            "callsign": _clean_callsign(state[STATE_CALLSIGN]),
            "origin_country": state[STATE_COUNTRY] or "Unknown",
            "latitude": latitude,
            "longitude": longitude,
            "distance_miles": distance,
            "distance_tenths": int(distance * 10),
            "bearing": int(
                bearing_degrees(
                    self._config.home_latitude,
                    self._config.home_longitude,
                    latitude,
                    longitude,
                )
            ),
            "altitude_ft": _meters_to_feet(alt_m),
            "speed_kts": _meters_per_second_to_knots(state[STATE_VELOCITY]),
            "heading": int(state[STATE_HEADING] or 0),
            "vertical_rate_fpm": _meters_per_second_to_fpm(state[STATE_VERTICAL_RATE]),
            "category_name": CATEGORY_NAMES.get(state[STATE_CATEGORY], "Aircraft"),
            "last_contact": state[STATE_LAST_CONTACT],
            "last_seen_monotonic": now,
            "enrichment": None,
        }
