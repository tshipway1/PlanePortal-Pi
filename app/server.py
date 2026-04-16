"""Flask web server for PlanePortal Pi.

Serves the dashboard and provides a JSON API endpoint that the frontend
polls for live data. A background thread runs the fetch/enrich cycle.
"""

import math
import threading
import time

from flask import Flask, jsonify, render_template

from app.adsbdb_client import ADSBDBClient
from app.config import AppConfig
from app.opensky_client import OpenSkyClient
from app.tracker import FlightTracker


class PlanePortalServer:
    def __init__(self):
        self._config = AppConfig()
        self._tracker = FlightTracker(self._config)
        self._opensky = OpenSkyClient(self._config)
        self._adsbdb = ADSBDBClient(self._config)
        self._last_snapshot = None
        self._last_detail = ""
        self._last_error = None
        self._lock = threading.Lock()

        self.app = Flask(
            __name__,
            template_folder="../templates",
            static_folder="../static",
        )
        self._register_routes()

    def _register_routes(self):
        @self.app.route("/")
        def index():
            validation_error = self._config.validate()
            return render_template(
                "dashboard.html",
                config=self._config,
                validation_error=validation_error,
            )

        @self.app.route("/api/snapshot")
        def api_snapshot():
            with self._lock:
                snapshot = self._last_snapshot
                detail = self._last_detail
                error = self._last_error

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
                radar_points.append(
                    {
                        "bearing": record["bearing"],
                        "distance_miles": record["distance_miles"],
                        "altitude_ft": record.get("altitude_ft"),
                        "is_live": record.get("is_live", False),
                        "is_featured": record is featured,
                        "heading": record["heading"],
                        "callsign": record["callsign"],
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
                }
            )

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

            with self._lock:
                self._last_snapshot = snapshot
                self._last_detail = detail
                self._last_error = None

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
