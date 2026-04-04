import time

from app.adsbdb_client import ADSBDBClient
from app.config import AppConfig
from app.network import NetworkManager
from app.opensky_client import OpenSkyClient
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
                states = self._opensky.fetch_states(self._tracker.current_bounds())
                snapshot_time = time.monotonic()
                snapshot = self._tracker.ingest_states(states, snapshot_time)
                self._enrich(snapshot)
                snapshot = self._tracker.snapshot(time.monotonic())

                detail = "{} live, {} recent inside {} mi".format(
                    snapshot["live_count"],
                    snapshot["recent_count"],
                    int(self._config.radius_miles),
                )
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
                if self._config.debug:
                    print("Plane Portal error:", error)

            self._sleep_until_next_cycle(cycle_started)

    def _enrich(self, snapshot):
        for record in snapshot["records"][: self._config.enrichment_limit]:
            enrichment = self._adsbdb.enrich_aircraft(record["icao24"], record["callsign"])
            if enrichment:
                self._tracker.attach_enrichment(record["icao24"], enrichment)

    def _sleep_until_next_cycle(self, cycle_started):
        elapsed = time.monotonic() - cycle_started
        remaining = self._config.refresh_seconds - elapsed
        while remaining > 0:
            time.sleep(min(1, remaining))
            remaining -= 1

    def _short_error(self, error):
        text = str(error)
        if len(text) <= 36:
            return text
        return text[:35] + "..."