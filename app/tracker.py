import math


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
    lat1_radians = math.radians(lat1)
    lon1_radians = math.radians(lon1)
    lat2_radians = math.radians(lat2)
    lon2_radians = math.radians(lon2)

    latitude_delta = lat2_radians - lat1_radians
    longitude_delta = lon2_radians - lon1_radians

    a_value = (
        math.sin(latitude_delta / 2) ** 2
        + math.cos(lat1_radians)
        * math.cos(lat2_radians)
        * math.sin(longitude_delta / 2) ** 2
    )
    c_value = 2 * math.atan2(math.sqrt(a_value), math.sqrt(1 - a_value))
    return EARTH_RADIUS_MILES * c_value


def bearing_degrees(lat1, lon1, lat2, lon2):
    lat1_radians = math.radians(lat1)
    lat2_radians = math.radians(lat2)
    longitude_delta = math.radians(lon2 - lon1)

    x_axis = math.sin(longitude_delta) * math.cos(lat2_radians)
    y_axis = math.cos(lat1_radians) * math.sin(lat2_radians) - math.sin(
        lat1_radians
    ) * math.cos(lat2_radians) * math.cos(longitude_delta)

    return (math.degrees(math.atan2(x_axis, y_axis)) + 360) % 360


def bounding_box(latitude, longitude, radius_miles, margin=1.15):
    padded_radius = radius_miles * margin
    latitude_delta = padded_radius / 69.0
    cos_latitude = math.cos(math.radians(latitude))
    if abs(cos_latitude) < 0.01:
        longitude_delta = 180
    else:
        longitude_delta = padded_radius / (69.172 * cos_latitude)

    return {
        "lamin": latitude - latitude_delta,
        "lomin": longitude - longitude_delta,
        "lamax": latitude + latitude_delta,
        "lomax": longitude + longitude_delta,
    }


def _clean_callsign(value):
    if value is None:
        return "Unknown"

    if isinstance(value, str):
        value = value.strip()
    else:
        value = str(value).strip()

    if not value:
        return "Unknown"
    return value


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

    def current_bounds(self):
        return bounding_box(
            self._config.home_latitude,
            self._config.home_longitude,
            self._config.radius_miles,
        )

    def ingest_states(self, states, now):
        for state in states:
            record = self._normalize_state(state, now)
            if record is None:
                continue

            previous = self._registry.get(record["icao24"])
            if previous and previous.get("enrichment"):
                record["enrichment"] = previous["enrichment"]

            self._registry[record["icao24"]] = record

        self._prune(now)
        return self.snapshot(now)

    def attach_enrichment(self, icao24, enrichment):
        record = self._registry.get(icao24)
        if not record:
            return
        record["enrichment"] = enrichment

    def snapshot(self, now):
        live_threshold = max(45, self._config.refresh_seconds + 15)
        records = []
        live_count = 0
        for record in self._registry.values():
            age_seconds = int(now - record["last_seen_monotonic"])
            record["age_seconds"] = age_seconds
            record["is_live"] = age_seconds <= live_threshold
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
        }

    def _prune(self, now):
        stale_keys = []
        for icao24, record in self._registry.items():
            if now - record["last_seen_monotonic"] > self._config.recent_window_seconds:
                stale_keys.append(icao24)
        for icao24 in stale_keys:
            del self._registry[icao24]

    def _sort_key(self, record):
        return (
            0 if record["is_live"] else 1,
            record["distance_tenths"],
            record["age_seconds"],
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

        distance_miles = haversine_miles(
            self._config.home_latitude,
            self._config.home_longitude,
            latitude,
            longitude,
        )
        if distance_miles > self._config.radius_miles:
            return None

        altitude_meters = state[STATE_GEO_ALTITUDE]
        if altitude_meters is None:
            altitude_meters = state[STATE_BARO_ALTITUDE]

        icao24 = state[STATE_ICAO24]
        return {
            "icao24": icao24,
            "callsign": _clean_callsign(state[STATE_CALLSIGN]),
            "origin_country": state[STATE_COUNTRY] or "Unknown",
            "latitude": latitude,
            "longitude": longitude,
            "distance_miles": distance_miles,
            "distance_tenths": int(distance_miles * 10),
            "bearing": int(
                bearing_degrees(
                    self._config.home_latitude,
                    self._config.home_longitude,
                    latitude,
                    longitude,
                )
            ),
            "altitude_ft": _meters_to_feet(altitude_meters),
            "speed_kts": _meters_per_second_to_knots(state[STATE_VELOCITY]),
            "heading": int(state[STATE_HEADING] or 0),
            "vertical_rate_fpm": _meters_per_second_to_fpm(state[STATE_VERTICAL_RATE]),
            "category_name": CATEGORY_NAMES.get(state[STATE_CATEGORY], "Aircraft"),
            "last_contact": state[STATE_LAST_CONTACT],
            "last_seen_monotonic": now,
            "enrichment": None,
        }