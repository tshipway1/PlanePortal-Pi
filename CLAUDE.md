# CLAUDE.md — Guidance for Claude Code

This file documents the PlanePortal-Pi project for future Claude Code sessions.

## What this is

A real-time aircraft tracking dashboard that runs on a **Raspberry Pi** with a **7" touchscreen (800×480)** in full-screen Chromium kiosk mode. Displays nearby aircraft on a radar, featured plane details, weather, and live ATC audio.

## Tech stack

- **Backend**: Python 3 + Flask 3 (single-file app in `app/server.py`)
- **Frontend**: Vanilla HTML5/CSS3/JavaScript in one Jinja template (`templates/dashboard.html`) — no build step, no frameworks, no npm
- **Radar**: HTML5 Canvas with inline SVG aircraft icons
- **Data sources**:
  - [OpenSky Network](https://opensky-network.org/) — live aircraft states (requires OAuth client credentials)
  - [ADSBDB](https://adsbdb.com/) — aircraft metadata (registration, type, airline, route)
  - [Open-Meteo](https://open-meteo.com/) — weather
  - [Broadcastify](https://www.broadcastify.com/) — live ATC audio feeds (scraped for stream URL, proxied)

## File layout

```
app/
  server.py              # Flask routes, background fetch thread, radar icon selection
  config.py              # Loads .env, validates settings
  tracker.py             # Aircraft state ingestion, filtering, snapshot
  opensky_client.py      # OpenSky API client with OAuth
  adsbdb_client.py       # ADSBDB enrichment client
  weather_client.py      # Open-Meteo client
  broadcastify_client.py # Scrapes Broadcastify feed pages for stream URLs
  liveatc_client.py      # DEAD CODE — kept only for reference. See "ATC audio" below.
templates/
  dashboard.html         # Single-page UI, ~1440 lines, inline CSS + JS
static/
  icons/*.svg            # 16 aircraft-type silhouettes (colored dynamically)
run.py                   # Entry point: loads .env, creates Flask app, binds 0.0.0.0:5000
setup-pi.sh              # Sets up venv, systemd service, Chromium kiosk autostart
.env                     # Runtime config (lat/lon, refresh, OpenSky creds, etc.)
```

## Running it

- **Dev**: `venv/bin/python run.py`
- **Production**: `sudo systemctl restart planeportal` (systemd service definition in `/etc/systemd/system/planeportal.service`, runs `venv/bin/python run.py`)
- **Kiosk browser**: auto-started by `~/.config/autostart/planeportal-kiosk.desktop`. Flags: `--noerrdialogs --disable-infobars --kiosk --incognito --password-store=basic http://localhost:5000`

## Runtime architecture

1. **Background thread** in `PlanePortalServer` runs every `PLANEPORTAL_REFRESH_SECONDS` (default 120s):
   - Fetch OpenSky states for current bounds
   - Ingest into `FlightTracker`, filter to within radius
   - Enrich top `ENRICHMENT_LIMIT` aircraft via ADSBDB
   - Fetch weather
   - Store in-memory snapshot (lock-protected)
2. **Frontend polls `/api/snapshot`** every 5s, redraws radar, featured card, recent list, weather
3. **Settings are edited in-UI** via an overlay with on-screen keyboard → POSTs to `/api/settings` → writes `.env` → SIGTERMs self → systemd restarts
4. **Auto page reload** when server version changes (detected via `server_version` field in snapshot)

## API endpoints

- `GET /` — dashboard HTML
- `GET /api/snapshot` — main polled endpoint, returns all live data
- `GET /api/settings` / `POST /api/settings` — read/write .env
- `GET /api/atc/feed?id=N` — fetch Broadcastify feed name + online status
- `GET /api/atc/stream?id=N` — streams the live MP3 audio (proxied)

## Kiosk-mode quirks (important!)

These have bitten us; don't repeat them:

- **`--incognito` means no persistent cookies.** Anything requiring a Cloudflare challenge will re-challenge on every launch. Don't build features that rely on cookies persisting across sessions.
- **`--kiosk` is strict fullscreen.** No tab bar, no window controls, no way for the user to close a popup window. `window.open()` popups are a UX dead-end.
- **Native `<select>` dropdowns behave badly on the touchscreen** — the native popup is tiny and hard to hit. Use **button grids or custom keyboards** instead.
- **Touch events aren't always click events.** The whole dashboard uses an `onTap()` helper (see `templates/dashboard.html` around the ATC section) that listens to `touchend` with scroll-vs-tap detection, and falls back to `click` for mouse. Reuse this pattern for any new interactive elements.
- **Settings overlay has its own on-screen keyboard** (`osk`). The ATC overlay has a separate numeric keyboard. They're independent — don't try to unify them without care.

## ATC audio notes

- **We tried LiveATC first — it does not work.** All LiveATC URLs are behind Cloudflare JS challenges, their stream servers reject non-browser clients, and their ToS explicitly prohibits third-party stream use. The `app/liveatc_client.py` file exists only as a reference; delete it anytime.
- **Broadcastify works great.** Feed pages (`/listen/feed/{id}`) are not Cloudflare-protected. They contain a `ListenPlayer.init()` call with a `relayUrl` that's a direct MP3 Icecast stream. The URL has session tokens (`nc=...&xan=...`) and must be fetched fresh for each play.
- **Server proxies the MP3 stream.** `/api/atc/stream?id=N` re-scrapes the feed page for a fresh URL, then streams chunks to the browser `<audio>` element. This avoids CORS and hides the session-token URL from the client.
- **Feed IDs are entered manually.** User finds a feed at broadcastify.com/listen (e.g., `22167` = Frederick County Airport KFDK) and types it on the on-screen numeric keyboard. Stored in localStorage.
- **Feed scraping regex** lives in `broadcastify_client.py` — if Broadcastify changes their player markup, update the `relayUrl:` regex.

## Audio subsystem

- Pi runs **PipeWire** (not PulseAudio). Use `wpctl` for audio control:
  - `wpctl status` — list sinks/streams
  - `wpctl set-volume <id> 1.0` — set volume
  - Needs `XDG_RUNTIME_DIR=/run/user/$(id -u)` when running as non-login bash.
- Bluetooth speakers: pair with `bluetoothctl`, then wait a moment for PipeWire to expose them as a sink via the `libspa-0.2-bluetooth` plugin (already installed). The first time a BT device connects, PipeWire auto-selects it as default sink.

## Config (`.env`)

Required:
- `PLANEPORTAL_HOME_LATITUDE`, `PLANEPORTAL_HOME_LONGITUDE` — center of radar
- `OPENSKY_CLIENT_ID`, `OPENSKY_CLIENT_SECRET` — for OpenSky OAuth

Optional (with defaults):
- `PLANEPORTAL_RADIUS_MILES=30`, `PLANEPORTAL_REFRESH_SECONDS=120`, `PLANEPORTAL_RECENT_WINDOW_MINUTES=30`, `PLANEPORTAL_ENRICHMENT_LIMIT=4`, `PLANEPORTAL_ADSB_CACHE_SECONDS=1800`, `PLANEPORTAL_DEBUG=0`, `PORT=5000`

## Coding conventions

- **No external JS/CSS frameworks.** Keep the payload tiny for the Pi.
- **Edit existing files rather than adding new ones.** The whole dashboard is in one HTML file on purpose.
- **No comments in code unless the "why" is non-obvious.** Identifiers carry the meaning.
- **Touch-first UI.** Button targets ≥ 28px. Use the `onTap()` helper. Avoid hover-only affordances.
- **Monospace aesthetic.** Courier New / Liberation Mono. Aviation/control-room vibe.
- **Colors come from CSS custom properties** at top of `<style>` — don't hardcode hex values in individual rules.

## Common tasks

- **Adding a new data source**: create `app/<name>_client.py`, instantiate in `PlanePortalServer.__init__`, wire into `_fetch_cycle` or add a new route.
- **Changing the radar**: canvas drawing code is in `drawRadar()` in `dashboard.html`. Icons are picked server-side in `_pick_icon()` in `server.py`.
- **Changing settings UI**: fields list is near the top of `dashboard.html` (`fieldMap` + `fieldLabels`). Server-side validation is in `SETTINGS_KEYS` dict in `_register_settings_routes`.

## What NOT to do

- Don't add a build step (webpack, vite, etc.). Keep it vanilla.
- Don't add any LiveATC integration. Dead end.
- Don't use `window.open()` for any feature — kiosk mode can't manage the window.
- Don't add `<select>` dropdowns to the main UI.
- Don't hit the OpenSky or ADSBDB APIs more frequently than the current cadence — they have rate limits and we already tune `refresh_seconds` carefully.
