"""Flask web server for PlanePortal Pi.

Serves the dashboard and provides a JSON API endpoint that the frontend
polls for live data. A background thread runs the fetch/enrich cycle.
"""

import math
import os
import signal
import threading
import time

from glob import glob

import requests as http_requests

from flask import Flask, Response, jsonify, render_template, request

from app.adsbdb_client import ADSBDBClient
from app import broadcastify_client
from app.config import AppConfig
from app.opensky_client import OpenSkyClient
from app.tracker import FlightTracker
from app.weather_client import WeatherClient


class PlanePortalServer:
    def __init__(self):
        self._config = AppConfig()
        self._tracker = FlightTracker(self._config)
        self._opensky = OpenSkyClient(self._config)
        self._adsbdb = ADSBDBClient(self._config)
        self._weather = WeatherClient(self._config)
        self._last_snapshot = None
        self._last_detail = ""
        self._last_error = None
        self._last_weather = None
        self._lock = threading.Lock()

        self.app = Flask(
            __name__,
            template_folder="../templates",
            static_folder="../static",
        )
        self._register_routes()
        self._register_settings_routes()
        self._register_broadcastify_routes()
        self._start_time = str(int(time.time()))
        self._svg_icons = self._load_svg_icons()

        @self.app.after_request
        def no_cache(response):
            response.headers["Cache-Control"] = "no-store"
            return response

    def _load_svg_icons(self):
        icons = {}
        icons_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "static", "icons")
        for path in glob(os.path.join(icons_dir, "*.svg")):
            name = os.path.splitext(os.path.basename(path))[0]
            with open(path) as f:
                icons[name] = f.read().replace("\n", "")
        return icons

    def _register_routes(self):
        @self.app.route("/")
        def index():
            validation_error = self._config.validate()
            return render_template(
                "dashboard.html",
                config=self._config,
                server_version=self._start_time,
                svg_icons=self._svg_icons,
                validation_error=validation_error,
            )

        @self.app.route("/api/snapshot")
        def api_snapshot():
            with self._lock:
                snapshot = self._last_snapshot
                detail = self._last_detail
                error = self._last_error
                weather = self._last_weather

            if snapshot is None:
                return jsonify(
                    {
                        "status": "waiting",
                        "detail": error or "Waiting for first scan...",
                        "featured": None,
                        "others": [],
                        "radar_points": [],
                        "live_count": 0,
                        "recent_count": 0,
                        "has_seen_aircraft": False,
                    }
                )

            featured = snapshot["featured"]
            featured_data = self._serialize_record(featured) if featured else None
            others_data = [self._serialize_record(r) for r in snapshot["others"]]

            radar_points = []
            for record in snapshot["records"]:
                serialized = self._serialize_record(record)
                radar_points.append(
                    {
                        "bearing": record["bearing"],
                        "distance_miles": record["distance_miles"],
                        "altitude_ft": record.get("altitude_ft"),
                        "is_live": record.get("is_live", False),
                        "is_featured": record is featured,
                        "heading": record["heading"],
                        "callsign": record["callsign"],
                        "icao24": record["icao24"],
                        "category": record["category_name"],
                        "icon": self._pick_icon(record),
                        "notable_tag": serialized["notable_tag"] if serialized else None,
                        "notable_color": serialized["notable_color"] if serialized else None,
                    }
                )

            return jsonify(
                {
                    "status": "ok",
                    "detail": detail,
                    "stale": bool(error),
                    "featured": featured_data,
                    "others": others_data,
                    "radar_points": radar_points,
                    "live_count": snapshot["live_count"],
                    "recent_count": snapshot["recent_count"],
                    "has_seen_aircraft": snapshot["has_seen_aircraft"],
                    "radius_miles": self._config.radius_miles,
                    "source_label": self._config.source_label(),
                    "server_version": self._start_time,
                    "weather": weather,
                }
            )

    def _env_path(self):
        return os.path.join(os.path.dirname(os.path.dirname(__file__)), ".env")

    def _read_env(self):
        """Read .env file and return dict of key=value pairs."""
        env = {}
        path = self._env_path()
        if not os.path.exists(path):
            return env
        with open(path, "r") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                if "=" in line:
                    key, _, value = line.partition("=")
                    env[key.strip()] = value.strip()
        return env

    def _write_env(self, updates):
        """Update .env file, preserving comments and structure."""
        path = self._env_path()
        lines = []
        if os.path.exists(path):
            with open(path, "r") as f:
                lines = f.readlines()

        written_keys = set()
        new_lines = []
        for line in lines:
            stripped = line.strip()
            if stripped and not stripped.startswith("#") and "=" in stripped:
                key = stripped.partition("=")[0].strip()
                if key in updates:
                    new_lines.append(f"{key}={updates[key]}\n")
                    written_keys.add(key)
                else:
                    new_lines.append(line)
            else:
                new_lines.append(line)

        for key, value in updates.items():
            if key not in written_keys:
                new_lines.append(f"{key}={value}\n")

        with open(path, "w") as f:
            f.writelines(new_lines)

    def _register_settings_routes(self):
        SETTINGS_KEYS = {
            "PLANEPORTAL_HOME_LATITUDE": "float",
            "PLANEPORTAL_HOME_LONGITUDE": "float",
            "PLANEPORTAL_RADIUS_MILES": "float",
            "PLANEPORTAL_REFRESH_SECONDS": "int",
            "PLANEPORTAL_RECENT_WINDOW_MINUTES": "int",
            "OPENSKY_CLIENT_ID": "str",
            "OPENSKY_CLIENT_SECRET": "str",
        }

        @self.app.route("/api/settings", methods=["GET"])
        def get_settings():
            env = self._read_env()
            settings = {}
            for key in SETTINGS_KEYS:
                settings[key] = env.get(key, "")
            return jsonify(settings)

        @self.app.route("/api/settings", methods=["POST"])
        def post_settings():
            data = request.get_json()
            if not data:
                return jsonify({"error": "No data provided"}), 400

            updates = {}
            for key, kind in SETTINGS_KEYS.items():
                if key not in data:
                    continue
                value = str(data[key]).strip()
                if kind == "float":
                    try:
                        float(value)
                    except ValueError:
                        return jsonify({"error": f"Invalid number for {key}"}), 400
                elif kind == "int":
                    try:
                        int(value)
                    except ValueError:
                        return jsonify({"error": f"Invalid integer for {key}"}), 400
                updates[key] = value

            if not updates:
                return jsonify({"error": "No valid settings provided"}), 400

            self._write_env(updates)

            # Schedule a self-restart so the response gets sent first.
            # systemd Restart=always will bring us back up.
            def _restart():
                time.sleep(1.5)
                os.kill(os.getpid(), signal.SIGTERM)
            threading.Thread(target=_restart, daemon=True).start()

            return jsonify({"status": "saved", "restarting": True})

    def _register_broadcastify_routes(self):
        @self.app.route("/api/atc/feed")
        def atc_feed_info():
            feed_id = request.args.get("id", "").strip()
            if not feed_id or not feed_id.isdigit():
                return jsonify({"error": "Invalid feed ID"}), 400
            info = broadcastify_client.get_feed_info(int(feed_id))
            if not info:
                return jsonify({"error": "Feed not found"}), 404
            # Don't expose the stream URL to the client — they use the proxy
            return jsonify({
                "feedId": info["feedId"],
                "name": info["name"],
                "online": info["online"],
            })

        @self.app.route("/api/atc/stream")
        def atc_stream():
            feed_id = request.args.get("id", "").strip()
            if not feed_id or not feed_id.isdigit():
                return "Invalid feed ID", 400
            info = broadcastify_client.get_feed_info(int(feed_id))
            if not info or not info["streamUrl"]:
                return "Feed unavailable", 502
            try:
                r = http_requests.get(
                    info["streamUrl"],
                    stream=True,
                    timeout=15,
                    headers={
                        "User-Agent": "Mozilla/5.0 (X11; Linux aarch64) "
                        "AppleWebKit/537.36"
                    },
                )
                r.raise_for_status()
            except Exception:
                return "Stream connection failed", 502

            def generate():
                try:
                    for chunk in r.iter_content(chunk_size=4096):
                        yield chunk
                finally:
                    r.close()

            return Response(
                generate(),
                content_type=r.headers.get("Content-Type", "audio/mpeg"),
            )

    # ── Icon type patterns ────────────────────────────────────
    # Widebody / heavy
    _WIDEBODY = (
        "A330", "A340", "A350", "A380",
        "B747", "747", "B767", "767", "B777", "777", "B787", "787",
        "MD11", "MD-11", "DC10", "DC-10", "IL96", "A300", "A310",
        "L101", "L-1011",
    )
    # Narrowbody jet
    _NARROWBODY = (
        "A319", "A320", "A321", "A220",
        "B737", "737", "B757", "757", "MD80", "MD-80", "MD90", "MD-90",
        "DC9", "DC-9", "717", "B717", "TU204", "TU154",
    )
    # Regional jet
    _REGIONAL_JET = (
        "CRJ", "ERJ", "EMB-", "E170", "E175", "E190", "E195",
        "F100", "F70", "BAE146", "RJ85", "ARJ",
    )
    # Turboprop / regional prop
    _TURBOPROP = (
        "ATR", "DH8", "DHC-8", "Q400", "SAAB", "SF340", "J31", "J41",
        "DO328", "AN24", "AN26", "C-130", "C130", "L-100", "P-3",
        "BE20", "B190", "EMB-120",
    )
    # Light prop / GA single engine
    _LIGHT_PROP = (
        "C172", "C182", "C206", "C152", "C150", "C210", "C177",
        "PA28", "PA32", "PA24", "PA18", "PA22",
        "SR20", "SR22", "DA40", "DA42", "DA62",
        "TB20", "TB21", "DR40", "RV-", "VENT", "LANCAIR",
        "M20", "BE35", "BE33",
    )
    # Twin prop / GA multi engine
    _TWIN_PROP = (
        "BE58", "BE55", "BE36", "PA34", "PA44", "PA31",
        "C310", "C340", "C402", "C414", "C421", "C441",
        "DA62",
    )
    # Business jet
    _BIZJET = (
        "LJ", "LEAR", "C525", "C550", "C560", "C680", "C700",
        "CL30", "CL35", "CL60", "GL5T", "GL7T", "GLEX",
        "GLF", "G280", "G550", "G650", "GV", "GIV", "GIII",
        "FA7X", "FA8X", "FA50", "FA90", "F900", "F2TH",
        "H25", "HA4T", "ASTR", "GALX",
        "PC12", "PC24", "TBM",
        "E50P", "E55P", "EA50", "PRM1", "HDJT",
    )
    # Military
    _MILITARY_TYPES = (
        "C-17", "C-5", "C-40", "KC-135", "KC-10", "KC-46",
        "F-16", "F-15", "F-18", "F-22", "F-35",
        "B-52", "B-1B", "B-2", "E-3", "E-6", "P-8",
        "V-22", "CV-22", "MQ-9", "RQ-4",
        "A-10", "T-38", "T-6",
    )
    # Helicopter types
    _HELO_TYPES = (
        "R22", "R44", "R66", "EC", "H125", "H130", "H135",
        "H145", "H155", "H160", "H175", "H215", "H225",
        "AS35", "AS50", "AS65", "A109", "A119", "A139", "A169",
        "S76", "S92", "S70", "UH-60", "AH-64", "CH-47",
        "MH-60", "B06", "B07", "B47", "B222", "B230", "B412",
        "MD5", "MD6", "B505", "SW4",
    )

    def _pick_icon(self, record):
        """Pick a radar icon type based on category + enrichment data."""
        cat = record.get("category_name", "")
        if cat == "Rotorcraft":
            return "helicopter"
        if cat == "Glider":
            return "cessna"
        if cat == "UAV":
            return "hi_perf"

        # Try enrichment aircraft type
        enrichment = record.get("enrichment") or {}
        aircraft = enrichment.get("aircraft") or {}
        atype = (aircraft.get("type") or aircraft.get("icao_type") or "").upper()

        if not atype:
            # Guess from callsign: N-numbers starting with N are often GA
            cs = record.get("callsign", "")
            if cs.startswith("N") and any(c.isdigit() for c in cs[1:4]):
                return "cessna"
            if cat == "Light aircraft":
                return "cessna"
            return "airliner"  # default — most traffic is commercial

        for t in self._HELO_TYPES:
            if t in atype:
                return "helicopter"
        for t in self._MILITARY_TYPES:
            if t in atype:
                return "hi_perf"
        for t in self._WIDEBODY:
            if t in atype:
                return "heavy_2e"
        for t in self._NARROWBODY:
            if t in atype:
                return "airliner"
        for t in self._REGIONAL_JET:
            if t in atype:
                return "jet_swept"
        for t in self._BIZJET:
            if t in atype:
                return "jet_nonswept"
        for t in self._TURBOPROP:
            if t in atype:
                return "twin_large"
        for t in self._TWIN_PROP:
            if t in atype:
                return "twin_small"
        for t in self._LIGHT_PROP:
            if t in atype:
                return "cessna"
        if cat == "Light aircraft":
            return "cessna"
        if cat == "Heavy aircraft":
            return "heavy_4e"
        return "airliner"

    # Callsign prefixes that indicate military or government aircraft
    _MILITARY_PREFIXES = (
        "RCH", "EVAC", "GOLD", "DUKE", "KING", "REACH", "JAKE",
        "TOPCAT", "SPAR", "SAM", "EXEC", "NAVY", "ARMY", "LANCE",
        "FORTE", "VIPER", "HAWK", "BOLT", "DEMON", "RAGE",
        "PAT", "ORDER", "BISON", "SKULL", "ROGUE",
    )
    _MILITARY_CALLSIGN_PATTERNS = (
        "RCH", "CNV", "AIO", "RRR", "HKY",  # USAF tankers/transports
        "MC", "PLF",  # USCG, Pilatus military
    )

    def _detect_notable(self, record, callsign, category_name, owner,
                        aircraft_type):
        """Return a notable tag and color, or (None, None)."""
        cs = callsign.upper()
        cat = category_name
        own = owner.upper() if owner else ""
        atype = (aircraft_type or "").upper()

        # Military detection
        for prefix in self._MILITARY_PREFIXES:
            if cs.startswith(prefix):
                return "MILITARY", "#E3655B"
        for pat in self._MILITARY_CALLSIGN_PATTERNS:
            if cs.startswith(pat):
                return "MILITARY", "#E3655B"
        mil_owners = (
            "AIR FORCE", "NAVY", "MARINE", "ARMY", "COAST GUARD",
            "USAF", "UNITED STATES", "DEPARTMENT OF", "NATO",
        )
        for mo in mil_owners:
            if mo in own:
                return "MILITARY", "#E3655B"
        mil_types = ("C-17", "C-130", "KC-135", "KC-10", "KC-46",
                     "F-16", "F-15", "F-18", "F-22", "F-35",
                     "B-52", "B-1B", "B-2", "E-3", "E-6", "P-8",
                     "C-5", "C-40", "V-22", "MQ-9", "RQ-4",
                     "UH-60", "AH-64", "CH-47", "MH-60", "CV-22")
        for mt in mil_types:
            if mt in atype:
                return "MILITARY", "#E3655B"

        # Helicopter
        if cat == "Rotorcraft":
            return "HELO", "#F3BE4E"

        # Heavy / widebody
        if cat == "Heavy aircraft":
            return "HEAVY", "#B7E3F5"

        # UAV / drone
        if cat == "UAV":
            return "UAV", "#E3655B"

        # Government / law enforcement
        gov_keywords = ("POLICE", "SHERIFF", "STATE PATROL", "CBP",
                        "FBI", "DHS", "SECRET SERVICE", "CUSTOMS")
        for gk in gov_keywords:
            if gk in own:
                return "GOV", "#F3BE4E"

        return None, None

    def _serialize_record(self, record):
        if record is None:
            return None
        enrichment = record.get("enrichment") or {}
        aircraft = enrichment.get("aircraft") or {}
        flightroute = enrichment.get("flightroute") or {}
        origin = flightroute.get("origin") or {}
        destination = flightroute.get("destination") or {}
        airline = flightroute.get("airline") or {}

        registration = aircraft.get("registration")
        aircraft_type = aircraft.get("type") or aircraft.get("icao_type")
        origin_code = origin.get("iata_code") or origin.get("icao_code")
        dest_code = destination.get("iata_code") or destination.get("icao_code")

        route = None
        if origin_code and dest_code:
            route = f"{origin_code} → {dest_code}"

        type_line = ""
        if registration and aircraft_type:
            type_line = f"{registration}  {aircraft_type}"
        elif registration:
            type_line = registration
        elif aircraft_type:
            type_line = aircraft_type
        else:
            type_line = record["category_name"]

        owner = (
            airline.get("name")
            or aircraft.get("registered_owner")
            or aircraft.get("manufacturer")
            or ""
        )

        vr = record.get("vertical_rate_fpm")
        if vr is None:
            trend = "LVL"
        elif vr > 250:
            trend = "CLB"
        elif vr < -250:
            trend = "DSC"
        else:
            trend = "LVL"

        notable_tag, notable_color = self._detect_notable(
            record, record["callsign"], record["category_name"],
            owner, aircraft_type,
        )

        return {
            "icao24": record["icao24"],
            "callsign": record["callsign"],
            "distance_miles": round(record["distance_miles"], 1),
            "bearing": record["bearing"],
            "altitude_ft": record.get("altitude_ft"),
            "speed_kts": record.get("speed_kts"),
            "heading": record["heading"],
            "vertical_rate_fpm": record.get("vertical_rate_fpm"),
            "status_text": record.get("status_text", ""),
            "is_live": record.get("is_live", False),
            "type_line": type_line,
            "route": route,
            "owner": owner,
            "trend": trend,
            "category_name": record["category_name"],
            "registration": registration or record["icao24"].upper(),
            "notable_tag": notable_tag,
            "notable_color": notable_color,
        }

    def _fetch_cycle(self):
        """Run one fetch-enrich-snapshot cycle."""
        try:
            states = self._opensky.fetch_states(self._tracker.current_bounds())
            now = time.monotonic()
            snapshot = self._tracker.ingest_states(states, now)

            enrich_note = None
            for record in snapshot["records"][: self._config.enrichment_limit]:
                try:
                    enrichment = self._adsbdb.enrich_aircraft(
                        record["icao24"], record["callsign"]
                    )
                    if enrichment:
                        self._tracker.attach_enrichment(record["icao24"], enrichment)
                except Exception as e:
                    if self._config.debug:
                        print(f"Enrichment error: {e}")
                    enrich_note = "metadata delayed"

            snapshot = self._tracker.snapshot(time.monotonic())

            detail = (
                f"{snapshot['live_count']} live, "
                f"{snapshot['recent_count']} recent "
                f"inside {int(self._config.radius_miles)} mi"
            )
            if enrich_note:
                detail += f"  {enrich_note}"

            weather = self._weather.fetch()

            with self._lock:
                self._last_snapshot = snapshot
                self._last_detail = detail
                self._last_error = None
                self._last_weather = weather

        except Exception as e:
            snapshot = self._tracker.snapshot(time.monotonic())
            error_text = f"{type(e).__name__}: {e}"
            if len(error_text) > 52:
                error_text = error_text[:51] + "..."
            with self._lock:
                if snapshot["featured"]:
                    self._last_snapshot = snapshot
                    self._last_detail = f"stale data: {error_text}"
                self._last_error = error_text
            print(f"PlanePortal error: {e}")

    def _background_loop(self):
        """Background thread that periodically fetches data."""
        while True:
            self._fetch_cycle()
            time.sleep(self._config.refresh_seconds)

    def start_background(self):
        thread = threading.Thread(target=self._background_loop, daemon=True)
        thread.start()


def create_app():
    server = PlanePortalServer()
    server.start_background()
    return server.app
