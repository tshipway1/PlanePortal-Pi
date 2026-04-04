import board
import displayio
import terminalio
from adafruit_display_text import label


BACKGROUND = 0x07131F
SKY_BAND = 0x0E2231
CARD = 0x102739
CARD_ALT = 0x0C1E2D
ACCENT = 0x2DB5A3
ACCENT_DIM = 0x1D6D67
TEXT = 0xF0F7F9
TEXT_MUTED = 0x95A9B5
WARN = 0xF3BE4E
ERROR = 0xE3655B


def _solid_block(width, height, color, x, y):
    bitmap = displayio.Bitmap(width, height, 1)
    palette = displayio.Palette(1)
    palette[0] = color
    return displayio.TileGrid(bitmap, pixel_shader=palette, x=x, y=y)


def _truncate(text, limit):
    text = text or ""
    if len(text) <= limit:
        return text
    return text[: limit - 1] + "..."


def _wrap_text(text, width, max_lines):
    text = str(text or "")
    if not text:
        return ""

    words = text.split()
    if not words:
        return ""

    lines = []
    current = words[0]
    for word in words[1:]:
        proposal = current + " " + word
        if len(proposal) <= width:
            current = proposal
            continue
        lines.append(current)
        current = word
        if len(lines) >= max_lines - 1:
            break

    if len(lines) < max_lines:
        lines.append(current)

    if len(lines) > max_lines:
        lines = lines[:max_lines]

    if len(lines) == max_lines and len(" ".join(words)) > len(" ".join(lines)):
        lines[-1] = _truncate(lines[-1], max(4, width - 1))

    return "\n".join(lines)


class PlanePortalUI:
    def __init__(self, config):
        self._config = config
        self._display = board.DISPLAY
        self._root = displayio.Group()
        self._display.root_group = self._root
        self._photo_bitmap = None
        self._photo_tilegrid = None

        self._build_scene()
        self.show_message(
            "Plane Portal",
            "Booting display",
            "Edit settings.toml, then reset the board",
        )

    def _build_scene(self):
        self._root.append(_solid_block(320, 240, BACKGROUND, 0, 0))
        self._root.append(_solid_block(320, 80, SKY_BAND, 0, 0))
        self._root.append(_solid_block(320, 28, CARD_ALT, 0, 0))
        self._root.append(_solid_block(192, 154, CARD, 10, 38))
        self._root.append(_solid_block(98, 154, CARD_ALT, 212, 38))
        self._root.append(_solid_block(300, 32, CARD_ALT, 10, 198))
        self._root.append(_solid_block(98, 70, SKY_BAND, 18, 52))
        self._root.append(_solid_block(98, 2, ACCENT, 18, 120))
        self._root.append(_solid_block(300, 2, ACCENT_DIM, 10, 194))

        self._image_group = displayio.Group(x=18, y=52)
        self._root.append(self._image_group)
        self._build_plane_glyph()

        self._header_title = label.Label(
            terminalio.FONT, text="PLANE PORTAL", color=TEXT, x=12, y=17
        )
        self._header_subtitle = label.Label(
            terminalio.FONT, text="overhead now + recent", color=TEXT_MUTED, x=158, y=17
        )
        self._featured_status = label.Label(
            terminalio.FONT, text="LIVE", color=ACCENT, x=18, y=48
        )
        self._featured_callsign = label.Label(
            terminalio.FONT, text="", color=TEXT, scale=2, x=126, y=64
        )
        self._featured_type = label.Label(
            terminalio.FONT, text="", color=TEXT_MUTED, x=126, y=86
        )
        self._featured_route = label.Label(
            terminalio.FONT, text="", color=TEXT, x=126, y=106
        )
        self._featured_metrics = label.Label(
            terminalio.FONT, text="", color=TEXT, x=18, y=144
        )
        self._featured_metrics_secondary = label.Label(
            terminalio.FONT, text="", color=TEXT_MUTED, x=18, y=164
        )
        self._featured_owner = label.Label(
            terminalio.FONT, text="", color=TEXT_MUTED, x=18, y=184
        )
        self._image_badge = label.Label(
            terminalio.FONT, text="", color=TEXT_MUTED, x=18, y=132
        )
        self._side_title = label.Label(
            terminalio.FONT, text="RECENT SKY", color=TEXT, x=222, y=56
        )
        self._side_list = label.Label(
            terminalio.FONT, text="", color=TEXT_MUTED, x=222, y=76, line_spacing=1.1
        )
        self._footer = label.Label(
            terminalio.FONT, text="", color=TEXT_MUTED, x=18, y=216
        )

        for item in (
            self._header_title,
            self._header_subtitle,
            self._featured_status,
            self._featured_callsign,
            self._featured_type,
            self._featured_route,
            self._featured_metrics,
            self._featured_metrics_secondary,
            self._featured_owner,
            self._image_badge,
            self._side_title,
            self._side_list,
            self._footer,
        ):
            self._root.append(item)

    def _build_plane_glyph(self):
        self._image_group.append(_solid_block(98, 70, SKY_BAND, 0, 0))
        self._image_group.append(_solid_block(34, 4, WARN, 32, 34))
        self._image_group.append(_solid_block(8, 28, WARN, 45, 21))
        self._image_group.append(_solid_block(20, 4, WARN, 39, 17))
        self._image_group.append(_solid_block(20, 4, WARN, 39, 49))
        self._image_group.append(_solid_block(10, 4, WARN, 44, 57))

    def _clear_image_group(self):
        while len(self._image_group):
            self._image_group.pop()
        self._photo_bitmap = None
        self._photo_tilegrid = None

    def show_placeholder_photo(self):
        self._clear_image_group()
        self._build_plane_glyph()

    def show_test_photo(self, bitmap_path):
        bitmap = displayio.OnDiskBitmap(bitmap_path)
        if bitmap.width > 98 or bitmap.height > 70:
            raise RuntimeError("Photo BMP must fit inside 98x70 pixels")

        self._clear_image_group()
        tilegrid = displayio.TileGrid(bitmap, pixel_shader=bitmap.pixel_shader)
        tilegrid.x = (98 - bitmap.width) // 2
        tilegrid.y = (70 - bitmap.height) // 2
        self._image_group.append(tilegrid)
        self._photo_bitmap = bitmap
        self._photo_tilegrid = tilegrid

    def show_message(self, title, body, footer):
        self._header_title.text = _truncate(title.upper(), 22)
        self._header_subtitle.text = _truncate(body, 24)
        self._featured_status.color = WARN
        self._featured_status.text = "STANDBY"
        self._featured_callsign.text = ""
        self._featured_type.text = ""
        self._featured_route.text = ""
        self._featured_metrics.text = _wrap_text(body, 22, 2)
        self._featured_metrics_secondary.text = _wrap_text(footer, 22, 2)
        self._featured_owner.text = ""
        self._image_badge.text = ""
        self._side_title.text = "STATUS"
        self._side_list.text = _wrap_text("Waiting for first nearby aircraft", 13, 5)
        self._footer.color = TEXT_MUTED
        self._footer.text = _truncate(footer, 46)

    def show_refreshing(self, detail, source_label):
        self._header_subtitle.text = _truncate(source_label, 24)
        self._featured_status.color = WARN
        self._featured_status.text = "REFRESH"
        self._side_title.text = "STATUS"
        self._side_list.text = _wrap_text(detail, 13, 5)
        self._footer.color = WARN
        self._footer.text = _truncate(detail, 46)

    def render_snapshot(self, snapshot, ip_address, source_label, stale=False, detail=None):
        featured = snapshot["featured"]
        if featured is None:
            self.show_message(
                "Quiet Sky",
                "No planes logged",
                "Watching {} miles around home".format(self._config.radius_miles),
            )
            return

        self._header_title.text = "PLANE PORTAL"
        self._header_subtitle.text = _truncate(
            "{}  {}".format(source_label, ip_address), 24
        )
        self._side_title.text = "RECENT SKY"

        self._featured_status.text = featured["status_text"]
        self._featured_status.color = WARN if stale else ACCENT
        self._featured_callsign.text = _truncate(featured["callsign"], 12)
        self._featured_type.text = _truncate(self._aircraft_line(featured), 24)
        self._featured_route.text = _truncate(self._route_line(featured), 24)
        self._featured_metrics.text = _truncate(self._metric_line(featured), 26)
        self._featured_metrics_secondary.text = _truncate(
            self._metric_line_secondary(featured), 26
        )
        self._featured_owner.text = _truncate(self._owner_line(featured), 26)
        self._image_badge.text = _truncate(self._image_badge_text(featured), 12)
        self._side_list.text = self._side_list_text(snapshot["others"])

        footer_text = detail or "{} live, {} recent inside {} mi".format(
            snapshot["live_count"],
            snapshot["recent_count"],
            int(self._config.radius_miles),
        )
        self._footer.color = WARN if stale else TEXT_MUTED
        self._footer.text = _truncate(footer_text, 46)

    def _aircraft_line(self, record):
        enrichment = record.get("enrichment") or {}
        aircraft = enrichment.get("aircraft") or {}
        registration = aircraft.get("registration")
        aircraft_type = aircraft.get("type") or aircraft.get("icao_type")
        if registration and aircraft_type:
            return "{}  {}".format(registration, aircraft_type)
        if registration:
            return registration
        if aircraft_type:
            return aircraft_type
        return record["category_name"]

    def _route_line(self, record):
        enrichment = record.get("enrichment") or {}
        flightroute = enrichment.get("flightroute") or {}
        origin = flightroute.get("origin") or {}
        destination = flightroute.get("destination") or {}
        origin_code = origin.get("iata_code") or origin.get("icao_code")
        destination_code = destination.get("iata_code") or destination.get("icao_code")
        if origin_code and destination_code:
            return "{} -> {}".format(origin_code, destination_code)
        return record["origin_country"]

    def _metric_line(self, record):
        altitude = record["altitude_ft"]
        speed = record["speed_kts"]
        return "{:.1f} mi   {} ft   {} kt".format(
            record["distance_miles"],
            altitude if altitude is not None else "--",
            speed if speed is not None else "--",
        )

    def _metric_line_secondary(self, record):
        climb = record["vertical_rate_fpm"]
        return "BRG {}  HDG {}  VS {}".format(
            record["bearing"],
            record["heading"],
            climb if climb is not None else "--",
        )

    def _owner_line(self, record):
        enrichment = record.get("enrichment") or {}
        aircraft = enrichment.get("aircraft") or {}
        flightroute = enrichment.get("flightroute") or {}
        airline = flightroute.get("airline") or {}
        if airline.get("name"):
            return airline.get("name")
        if aircraft.get("registered_owner"):
            return aircraft.get("registered_owner")
        if aircraft.get("manufacturer"):
            return aircraft.get("manufacturer")
        return record["category_name"]

    def _image_badge_text(self, record):
        enrichment = record.get("enrichment") or {}
        aircraft = enrichment.get("aircraft") or {}
        if aircraft.get("registration"):
            return aircraft.get("registration")
        return record["icao24"].upper()

    def _side_list_text(self, records):
        if not records:
            return "No other nearby\naircraft in the\nrecent window"

        lines = []
        for record in records:
            route = self._route_line(record)
            lines.append(
                "{} {:>4.1f}mi\n{}\n{}".format(
                    record["status_text"],
                    record["distance_miles"],
                    _truncate(record["callsign"], 12),
                    _truncate(route, 14),
                )
            )
        return "\n".join(lines)