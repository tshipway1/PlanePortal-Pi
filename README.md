# Plane Portal

CircuitPython application for an Adafruit PyPortal that watches a fixed circular area around a configured center point, remembers aircraft seen in the last few minutes, and shows the most relevant nearby planes on the display.

## What it does

- Polls OpenSky for live aircraft state vectors near a configured watch point
- Applies a true circular radius filter on-device, defaulting to 3 miles
- Keeps a rolling recent-aircraft memory so a plane can remain visible after it passes through the radius
- Enriches the most relevant aircraft with ADSBDB metadata such as registration, aircraft type, airline, and route when available
- Renders a compact aviation-style dashboard for the PyPortal's 320x240 display, including a mini radar view, status badges, and a recent-traffic column

## What the screen shows

- Top bar: app title, source status, and IP / source summary
- Left radar tile: nearby aircraft plotted by bearing and relative distance from your configured watch point
- Featured aircraft card: callsign, route, type / operator, distance, altitude, speed, heading, and vertical trend
- Status badges: live/recent state and climb/descent trend
- Right column: compact recent / nearby aircraft list
- Footer: refresh summary plus non-fatal notes such as delayed enrichment

## Current implementation status

This is the first implementation pass.

- Live OpenSky polling: implemented
- Local recent-flight memory: implemented
- ADSBDB enrichment: implemented
- Radar-style live display: implemented
- Altitude color coding and compact status badges: implemented
- Experimental image support: removed in favor of a cleaner radar-first display

## Required CircuitPython libraries

Copy these libraries from the matching Adafruit CircuitPython bundle into `CIRCUITPY/lib`:

- `adafruit_connection_manager.mpy`
- `adafruit_requests.mpy`
- `adafruit_display_text/`
- `adafruit_esp32spi/`

The project uses built-in `board`, `displayio`, and `terminalio`, so no extra font or image assets are required for the initial version.

## Device setup

1. Install CircuitPython on the PyPortal.
2. Copy the required libraries into `CIRCUITPY/lib`.
3. Copy [code.py](code.py) and the [app](app) folder to the root of `CIRCUITPY`.
4. Copy [settings.toml.example](settings.toml.example) to `settings.toml` on `CIRCUITPY` and fill in your values.
5. Reset the board.

If the app fails during boot or refresh, open the serial console to read lines beginning with `Plane Portal error:`.

## Configuration

The app reads configuration from `settings.toml`.

Required:

- `CIRCUITPY_WIFI_SSID`
- `CIRCUITPY_WIFI_PASSWORD`
- `PLANEPORTAL_HOME_LATITUDE`
- `PLANEPORTAL_HOME_LONGITUDE`

These existing key names are kept for compatibility, but they represent the app's watch point or center point, not necessarily a home location.

Recommended:

- `OPENSKY_CLIENT_ID`
- `OPENSKY_CLIENT_SECRET`

Optional:

- `PLANEPORTAL_RADIUS_MILES`
- `PLANEPORTAL_REFRESH_SECONDS`
- `PLANEPORTAL_RECENT_WINDOW_MINUTES`
- `PLANEPORTAL_ENRICHMENT_LIMIT`
- `PLANEPORTAL_ADSB_CACHE_SECONDS`
- `PLANEPORTAL_DEBUG`

Notes:

- `settings.toml` does not support float literals, so latitude, longitude, and radius should be stored as quoted strings.
- Without OpenSky credentials the app still works in anonymous mode, but with lower rate limits.
- OpenSky supplies the live aircraft position and movement data.
- ADSBDB supplies best-effort aircraft metadata such as type, registration, route, and airline.

## Known limitations

- OpenSky now uses OAuth2 client credentials, so valid OpenSky API credentials are strongly recommended.
- The "recently overhead" list is maintained locally from prior refreshes. It is not historical flight data pulled from the API.
- ADSBDB metadata is best-effort only. Some aircraft have no route information or type details.
- The app intentionally does not attempt aircraft photo rendering on-device.

## File layout

- [code.py](code.py): top-level CircuitPython entrypoint
- [app/config.py](app/config.py): settings parsing and defaults
- [app/network.py](app/network.py): PyPortal WiFi session management
- [app/opensky_client.py](app/opensky_client.py): OpenSky OAuth and live aircraft fetches
- [app/adsbdb_client.py](app/adsbdb_client.py): ADSBDB enrichment and caching
- [app/tracker.py](app/tracker.py): radius filtering, distance math, and recent-flight tracking
- [app/ui.py](app/ui.py): display layout and rendering
- [app/main.py](app/main.py): application loop

## Next recommended steps

1. Test the current build directly on the PyPortal hardware.
2. Tune the live radar and recent-traffic layout against your local sky traffic.
3. Add optional touch interactions for cycling the featured aircraft.
4. Keep refining the radar-first display and resist reintroducing features that do not fit the hardware well.