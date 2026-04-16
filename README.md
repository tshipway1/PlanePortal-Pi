# Plane Portal Pi

Real-time aircraft tracking dashboard for Raspberry Pi with a 7" display.

Ported from the original [PlanePortal](https://github.com/kevinl95/PlanePortal) CircuitPython project for Adafruit PyPortal. This version runs on a Raspberry Pi as a Flask web app displayed in fullscreen Chromium kiosk mode — designed for an 800x480 screen.

## What it does

- Polls OpenSky Network for live aircraft state vectors near a configured watch point
- Applies a true circular radius filter, defaulting to 3 miles
- Keeps a rolling recent-aircraft memory so planes remain visible after passing through the radius
- Enriches aircraft with ADSBDB metadata: registration, aircraft type, airline, and route
- Renders an aviation-style dashboard with a live radar view, featured aircraft card, metrics, and a recent-traffic sidebar
- Auto-refreshes via AJAX — no page reloads needed

## What the screen shows

- **Header**: app title, live/stale status indicator, data source
- **Radar panel** (left): aircraft plotted by bearing and distance, color-coded by altitude
- **Featured aircraft card** (center): callsign, type, route, operator, distance, altitude, speed, heading, vertical rate, and climb/descent trend
- **Recent sidebar** (right): other nearby aircraft with key details
- **Footer**: live/recent counts and status notes

### Altitude color coding

| Color | Altitude |
|-------|----------|
| Orange | Below 12,000 ft |
| Teal | 12,000 - 28,000 ft |
| Light blue | Above 28,000 ft |

## Hardware needed

- Raspberry Pi (3B+, 4, 5, or Zero 2W all work)
- 7" display — the official Raspberry Pi touchscreen (800x480) or any HDMI 7" display
- WiFi or Ethernet connection
- SD card with Raspberry Pi OS (Desktop edition)

No GPIO wiring, no special hardware. Just power, display, and network.

## Quick start

### 1. Clone and set up

```bash
git clone https://github.com/tshipway1/PlanePortal-Pi.git
cd PlanePortal-Pi
chmod +x setup-pi.sh
./setup-pi.sh
```

The setup script installs Python dependencies in a virtual environment, creates a systemd service, and configures kiosk-mode autostart.

### 2. Configure

```bash
cp .env.example .env
nano .env
```

Required settings:

- `PLANEPORTAL_HOME_LATITUDE` — your watch-point latitude (decimal degrees)
- `PLANEPORTAL_HOME_LONGITUDE` — your watch-point longitude (decimal degrees)

Recommended:

- `OPENSKY_CLIENT_ID` — OpenSky Network API client ID
- `OPENSKY_CLIENT_SECRET` — OpenSky Network API client secret

Register for free at [opensky-network.org](https://opensky-network.org/) for higher rate limits.

Optional settings (with defaults):

| Setting | Default | Description |
|---------|---------|-------------|
| `PLANEPORTAL_RADIUS_MILES` | 3 | Search radius in miles |
| `PLANEPORTAL_REFRESH_SECONDS` | 120 | Seconds between API polls |
| `PLANEPORTAL_RECENT_WINDOW_MINUTES` | 10 | How long to remember aircraft |
| `PLANEPORTAL_ENRICHMENT_LIMIT` | 4 | Max aircraft to enrich per cycle |
| `PLANEPORTAL_ADSB_CACHE_SECONDS` | 1800 | Metadata cache TTL |
| `PORT` | 5000 | Web server port |

### 3. Start

```bash
# Start the service
sudo systemctl start planeportal

# Check status
sudo systemctl status planeportal

# View logs
journalctl -u planeportal -f
```

Open `http://localhost:5000` in a browser, or reboot the Pi for automatic kiosk-mode display.

### Manual run (without systemd)

```bash
source venv/bin/activate
python run.py
```

## How it works

The app runs a Flask web server with a background thread that periodically polls the OpenSky Network API. The frontend is a single HTML page that polls a `/api/snapshot` JSON endpoint every 5 seconds and renders everything client-side with vanilla JavaScript and Canvas.

### Architecture

```
run.py                  <- Entry point: loads .env, starts Flask
app/
  server.py             <- Flask app, background fetch loop, JSON API
  config.py             <- Reads settings from environment variables
  opensky_client.py     <- OpenSky OAuth2 + state vector fetching
  adsbdb_client.py      <- Aircraft metadata enrichment + caching
  tracker.py            <- Radius filtering, distance math, flight registry
templates/
  dashboard.html        <- Full dashboard UI (HTML + CSS + JS)
```

### Data sources

- **OpenSky Network** — live aircraft positions, altitude, speed, heading, vertical rate
- **ADSBDB** — aircraft registration, type, route, airline, operator (best-effort)

## Differences from original PlanePortal

| | Original (PyPortal) | Pi Version |
|---|---|---|
| Platform | CircuitPython on Adafruit PyPortal | Python 3 on Raspberry Pi OS |
| Display | 320x240 built-in LCD | 800x480 (7" Pi screen) |
| UI | CircuitPython displayio | Flask + HTML/CSS/Canvas |
| Networking | ESP32 SPI WiFi | Native WiFi/Ethernet |
| Rendering | Bitmap pixel drawing | Canvas radar + DOM layout |
| Access | Device-only | Any browser on the network |

## Troubleshooting

**No aircraft showing up?**
- Verify your latitude/longitude in `.env` are correct
- Try increasing `PLANEPORTAL_RADIUS_MILES` to 5 or 10
- Check that OpenSky API is reachable: `curl https://opensky-network.org/api/states/all?lamin=47&lomin=-123&lamax=48&lomax=-122`

**Rate limited?**
- Register for OpenSky API credentials (free) and add them to `.env`
- Increase `PLANEPORTAL_REFRESH_SECONDS` to 180 or higher

**Screen not filling the display?**
- Chromium kiosk mode should handle this automatically
- If using HDMI, check `/boot/config.txt` display settings match your panel resolution

## Credits

Based on [PlanePortal](https://github.com/kevinl95/PlanePortal) by Kevin Loughlin.
