import time

from app.adsbdb_client import ADSBDBClient
from app.config import AppConfig
from app.network import NetworkManager
from app.opensky_client import OpenSkyClient
from app.photo import PhotoManager
from app.tracker import FlightTracker
from app.ui import PlanePortalUI


class PlanePortalApp:
    def __init__(self):
        self._config = AppConfig()
        self._ui = PlanePortalUI(self._config)
        self._network = NetworkManager(self._config)
        self._tracker = FlightTracker(self._config)
        self._opensky = OpenSkyClient(self._config, self._session)
        self._adsbdb = ADSBDBClient(self._config, self._session)
        self._photo = PhotoManager(self._config, self._session)

    def _session(self):
        return self._network.session

    def run(self):
        validation_error = self._config.validate()
        if validation_error:
            self._ui.show_message("Config required", "Edit settings.toml", validation_error)
            while True:
                time.sleep(1)

        while True:
            cycle_started = time.monotonic()
            try:
                self._ui.show_refreshing("Connecting to WiFi", self._config.source_label())
                self._network.connect()

                self._ui.show_refreshing(
                    "Scanning nearby aircraft", self._config.source_label()
                )
                photo_note = self._refresh_test_photo()
                states = self._opensky.fetch_states(self._tracker.current_bounds())
                snapshot_time = time.monotonic()
                snapshot = self._tracker.ingest_states(states, snapshot_time)
                enrich_note = self._enrich(snapshot)
                snapshot = self._tracker.snapshot(time.monotonic())

                detail = "{} live, {} recent inside {} mi".format(
                    snapshot["live_count"],
                    snapshot["recent_count"],
                    int(self._config.radius_miles),
                )
                if photo_note:
                    detail = "{}  {}".format(detail, photo_note)
                if enrich_note:
                    detail = "{}  {}".format(detail, enrich_note)
                self._ui.render_snapshot(
                    snapshot,
                    self._network.ip_address,
                    self._config.source_label(),
                    stale=False,
                    detail=detail,
                )
            except Exception as error:
                snapshot = self._tracker.snapshot(time.monotonic())
                detail = "stale data: {}".format(self._short_error(error))
                if snapshot["featured"]:
                    self._ui.render_snapshot(
                        snapshot,
                        self._network.ip_address,
                        self._config.source_label(),
                        stale=True,
                        detail=detail,
                    )
                else:
                    self._ui.show_message(
                        "Update failed",
                        self._short_error(error),
                        "Check WiFi, OpenSky credentials, and location settings",
                    )
                print("Plane Portal error:", type(error).__name__, error)

            self._sleep_until_next_cycle(cycle_started)

    def _enrich(self, snapshot):
        note = None
        for record in snapshot["records"][: self._config.enrichment_limit]:
            try:
                enrichment = self._adsbdb.enrich_aircraft(
                    record["icao24"], record["callsign"]
                )
            except Exception as error:
                print("Plane Portal enrichment error:", type(error).__name__, error)
                note = "route lookup delayed"
                continue
            if enrichment:
                self._tracker.attach_enrichment(record["icao24"], enrichment)
        return note

    def _refresh_test_photo(self):
        try:
            bitmap_path, note = self._photo.ensure_test_photo()
            if bitmap_path:
                self._ui.show_test_photo(bitmap_path)
                return note
            self._ui.show_placeholder_photo()
            return note
        except Exception as error:
            self._ui.show_placeholder_photo()
            print("Plane Portal photo error:", type(error).__name__, error)
            return "photo fallback"

    def _sleep_until_next_cycle(self, cycle_started):
        elapsed = time.monotonic() - cycle_started
        remaining = self._config.refresh_seconds - elapsed
        while remaining > 0:
            time.sleep(min(1, remaining))
            remaining -= 1

    def _short_error(self, error):
        text = "{}: {}".format(type(error).__name__, error)
        if len(text) <= 52:
            return text
        return text[:51] + "..."