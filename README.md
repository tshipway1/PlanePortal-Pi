# Plane Portal

CircuitPython application for an Adafruit PyPortal that watches a fixed circular area around your home location, remembers aircraft seen in the last few minutes, and shows the most relevant nearby planes on the display.

## What it does

- Polls OpenSky for live aircraft state vectors near a configured location
- Applies a true circular radius filter on-device, defaulting to 3 miles
- Keeps a rolling recent-aircraft memory so a plane can remain visible after it passes through the radius
- Enriches the most relevant aircraft with ADSBDB metadata such as registration, aircraft type, airline, and route when available
- Renders a text-first dashboard designed for the PyPortal's 320x240 display

## Current implementation status

This is the first implementation pass.

- Live OpenSky polling: implemented
- Local recent-flight memory: implemented
- ADSBDB enrichment: implemented
- Photo slot: placeholder silhouette with optional fixed-image prototype
- Remote per-aircraft photo rendering: still deferred because device-only image handling is the least reliable part of the stack on PyPortal

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

## Configuration

The app reads configuration from `settings.toml`.

Required:

- `CIRCUITPY_WIFI_SSID`
- `CIRCUITPY_WIFI_PASSWORD`
- `PLANEPORTAL_HOME_LATITUDE`
- `PLANEPORTAL_HOME_LONGITUDE`

Recommended:

- `OPENSKY_CLIENT_ID`
- `OPENSKY_CLIENT_SECRET`

Notes:

- `settings.toml` does not support float literals, so latitude, longitude, and radius should be stored as quoted strings.
- Without OpenSky credentials the app still works in anonymous mode, but with lower rate limits.
- The controlled photo test currently expects a remote BMP image URL.
- The current build still does not attempt JPG decoding or live per-aircraft photo rendering.

## Controlled photo test

You can now test the picture pipeline with a fixed remote BMP.

1. Set `PLANEPORTAL_ENABLE_PHOTOS = "1"` in `settings.toml`.
2. Set `PLANEPORTAL_TEST_IMAGE_URL` to a publicly reachable BMP image URL.
3. Keep the image at `98x70` pixels or smaller for the current test layout.
4. Reset the board.

Behavior:

- If the bitmap downloads and fits the reserved image area, it will replace the silhouette.
- If the request fails, times out, or returns a non-BMP image, the app silently falls back to the silhouette and keeps running.

This is only a plumbing test for image download and display. It is not yet wired to live aircraft metadata.

## Known limitations

- OpenSky now uses OAuth2 client credentials, so valid OpenSky API credentials are strongly recommended.
- The "recently overhead" list is maintained locally from prior refreshes. It is not historical flight data pulled from the API.
- ADSBDB metadata is best-effort only. Some aircraft have no route or photo information.
- The photo area currently shows a local silhouette instead of a downloaded plane image.

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
2. Tune the UI text density against your local sky traffic.
3. Add optional touch interactions for cycling the featured aircraft.
4. Revisit best-effort photo loading only after the core polling loop is stable on-device.