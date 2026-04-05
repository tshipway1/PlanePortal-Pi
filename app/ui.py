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
ALT_LOW = 0xF39C5A
ALT_MID = 0x2DB5A3
ALT_HIGH = 0xB7E3F5

RADAR_WIDTH = 98
RADAR_HEIGHT = 70
RADAR_CENTER_X = 49
RADAR_CENTER_Y = 35
RADAR_RADIUS = 31

BADGE_STATUS_X = 126
BADGE_TREND_X = 160
BADGE_Y = 46
BADGE_WIDTH = 28
BADGE_HEIGHT = 12
BADGE_TEXT_Y = 55


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


def _distance_label(distance_miles):
    return "{:.1f}MI".format(distance_miles)


def _altitude_label(altitude_ft):
    if altitude_ft is None:
        return "--KFT"
    return "{}KFT".format(max(0, int(round(altitude_ft / 1000.0))))


def _speed_label(speed_kts):
    if speed_kts is None:
        return "--KT"
    return "{}KT".format(speed_kts)


def _heading_label(heading):
    return "HDG{:03d}".format(int(heading) % 360)


def _vertical_label(vertical_rate_fpm):
    if vertical_rate_fpm is None:
        return "VS --"
    return "VS {:+d}".format(int(vertical_rate_fpm))


def _trend_label(vertical_rate_fpm):
    if vertical_rate_fpm is None:
        return "LVL"
    if vertical_rate_fpm > 250:
        return "CLB"
    if vertical_rate_fpm < -250:
        return "DSC"
    return "LVL"


def _altitude_color(altitude_ft):
    if altitude_ft is None:
        return TEXT_MUTED
    if altitude_ft < 12000:
        return ALT_LOW
    if altitude_ft < 28000:
        return ALT_MID
    return ALT_HIGH


def _bearing_to_xy(bearing_degrees, distance_miles, radius_miles):
    if radius_miles <= 0:
        radius_fraction = 0
    else:
        radius_fraction = min(1.0, max(0.0, distance_miles / radius_miles))

    angle = bearing_degrees * 3.141592653589793 / 180.0
    x_offset = int(round(__import__("math").sin(angle) * RADAR_RADIUS * radius_fraction))
    y_offset = int(round(__import__("math").cos(angle) * RADAR_RADIUS * radius_fraction))
    return RADAR_CENTER_X + x_offset, RADAR_CENTER_Y - y_offset


def _heading_endpoint(x_pos, y_pos, heading_degrees, length=8):
    angle = heading_degrees * 3.141592653589793 / 180.0
    x_offset = int(round(__import__("math").sin(angle) * length))
    y_offset = int(round(__import__("math").cos(angle) * length))
    return x_pos + x_offset, y_pos - y_offset


def _draw_pixel(bitmap, x_pos, y_pos, color_index):
    if 0 <= x_pos < bitmap.width and 0 <= y_pos < bitmap.height:
        bitmap[x_pos, y_pos] = color_index


def _draw_square(bitmap, x_pos, y_pos, radius, color_index):
    for x_value in range(x_pos - radius, x_pos + radius + 1):
        for y_value in range(y_pos - radius, y_pos + radius + 1):
            _draw_pixel(bitmap, x_value, y_value, color_index)


def _draw_line(bitmap, x0, y0, x1, y1, color_index):
    delta_x = abs(x1 - x0)
    step_x = 1 if x0 < x1 else -1
    delta_y = -abs(y1 - y0)
    step_y = 1 if y0 < y1 else -1
    error = delta_x + delta_y

    while True:
        _draw_pixel(bitmap, x0, y0, color_index)
        if x0 == x1 and y0 == y1:
            return
        error_double = error * 2
        if error_double >= delta_y:
            error += delta_y
            x0 += step_x
        if error_double <= delta_x:
            error += delta_x
            y0 += step_y


def _make_palette(*colors):
    palette = displayio.Palette(len(colors))
    for index, color in enumerate(colors):
        palette[index] = color
    return palette


class PlanePortalUI:
    def __init__(self, config):
        self._config = config
        self._display = board.DISPLAY
        self._root = displayio.Group()
        self._display.root_group = self._root
        self._radar_bitmap = None
        self._radar_tilegrid = None

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
        self._status_badge_bg = _solid_block(BADGE_WIDTH, BADGE_HEIGHT, ACCENT, BADGE_STATUS_X, BADGE_Y)
        self._trend_badge_bg = _solid_block(BADGE_WIDTH, BADGE_HEIGHT, WARN, BADGE_TREND_X, BADGE_Y)
        self._status_badge_text = label.Label(
            terminalio.FONT, text="", color=BACKGROUND, x=BADGE_STATUS_X, y=BADGE_TEXT_Y
        )
        self._trend_badge_text = label.Label(
            terminalio.FONT, text="", color=BACKGROUND, x=BADGE_TREND_X, y=BADGE_TEXT_Y
        )
        self._featured_callsign = label.Label(
            terminalio.FONT, text="", color=TEXT, scale=2, x=126, y=74
        )
        self._featured_type = label.Label(
            terminalio.FONT, text="", color=TEXT_MUTED, x=126, y=96
        )
        self._featured_route = label.Label(
            terminalio.FONT, text="", color=TEXT, x=126, y=114
        )
        self._featured_metrics = label.Label(
            terminalio.FONT, text="", color=TEXT, x=18, y=146
        )
        self._featured_metrics_secondary = label.Label(
            terminalio.FONT, text="", color=TEXT_MUTED, x=18, y=166
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
            self._status_badge_bg,
            self._trend_badge_bg,
            self._status_badge_text,
            self._trend_badge_text,
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
        self._radar_bitmap = None
        self._radar_tilegrid = None

    def _build_radar_background(self):
        bitmap = displayio.Bitmap(RADAR_WIDTH, RADAR_HEIGHT, 8)
        palette = _make_palette(
            SKY_BAND,
            ACCENT_DIM,
            ALT_MID,
            ALT_LOW,
            ALT_HIGH,
            TEXT_MUTED,
            TEXT,
            ERROR,
        )
        bitmap.fill(0)

        for radius in (10, 20, 30):
            lower = radius - 1
            upper = radius + 1
            lower_sq = lower * lower
            upper_sq = upper * upper
            for x_pos in range(RADAR_WIDTH):
                for y_pos in range(RADAR_HEIGHT):
                    dx = x_pos - RADAR_CENTER_X
                    dy = y_pos - RADAR_CENTER_Y
                    distance_sq = dx * dx + dy * dy
                    if lower_sq <= distance_sq <= upper_sq:
                        bitmap[x_pos, y_pos] = 1

        _draw_line(bitmap, RADAR_CENTER_X - RADAR_RADIUS, RADAR_CENTER_Y, RADAR_CENTER_X + RADAR_RADIUS, RADAR_CENTER_Y, 1)
        _draw_line(bitmap, RADAR_CENTER_X, RADAR_CENTER_Y - RADAR_RADIUS, RADAR_CENTER_X, RADAR_CENTER_Y + RADAR_RADIUS, 1)
        _draw_square(bitmap, RADAR_CENTER_X, RADAR_CENTER_Y, 1, 6)

        _draw_line(bitmap, RADAR_CENTER_X, 2, RADAR_CENTER_X, 6, 6)
        _draw_line(bitmap, RADAR_CENTER_X - 2, 4, RADAR_CENTER_X + 2, 4, 6)

        tilegrid = displayio.TileGrid(bitmap, pixel_shader=palette)
        self._clear_image_group()
        self._image_group.append(tilegrid)
        self._radar_bitmap = bitmap
        self._radar_tilegrid = tilegrid

    def show_radar_snapshot(self, snapshot):
        self._build_radar_background()

        records = snapshot.get("records") or []
        for record in records[1:]:
            x_pos, y_pos = _bearing_to_xy(
                record["bearing"], record["distance_miles"], self._config.radius_miles
            )
            color_index = 5 if not record.get("is_live") else self._radar_color_index(record)
            _draw_square(self._radar_bitmap, x_pos, y_pos, 1, color_index)

        featured = snapshot.get("featured")
        if featured:
            x_pos, y_pos = _bearing_to_xy(
                featured["bearing"], featured["distance_miles"], self._config.radius_miles
            )
            end_x, end_y = _heading_endpoint(x_pos, y_pos, featured["heading"])
            _draw_line(self._radar_bitmap, x_pos, y_pos, end_x, end_y, 6)
            _draw_square(self._radar_bitmap, x_pos, y_pos, 2, 7)
            _draw_square(self._radar_bitmap, x_pos, y_pos, 1, self._radar_color_index(featured))

    def _radar_color_index(self, record):
        altitude_ft = record.get("altitude_ft")
        if altitude_ft is None:
            return 5
        if altitude_ft < 12000:
            return 3
        if altitude_ft < 28000:
            return 2
        return 4

    def _set_badges(self, status_text, status_color, trend_text, trend_color):
        status_text = _truncate(status_text, 4)
        trend_text = _truncate(trend_text, 4)
        self._status_badge_bg.pixel_shader[0] = status_color
        self._trend_badge_bg.pixel_shader[0] = trend_color
        self._status_badge_text.text = status_text
        self._trend_badge_text.text = trend_text
        self._status_badge_text.x = self._badge_text_x(BADGE_STATUS_X, status_text)
        self._trend_badge_text.x = self._badge_text_x(BADGE_TREND_X, trend_text)

    def _badge_text_x(self, badge_x, text):
        text_width = len(text) * 6
        return badge_x + max(1, (BADGE_WIDTH - text_width) // 2)

    def show_message(self, title, body, footer, side_text=None, use_radar=False):
        if use_radar:
            self.show_radar_snapshot({"records": [], "featured": None})
        else:
            self._clear_image_group()
            self._build_plane_glyph()

        self._header_title.text = _truncate(title.upper(), 22)
        self._header_subtitle.text = _truncate(body, 24)
        self._featured_status.color = WARN
        self._featured_status.text = "STANDBY"
        self._set_badges("WAIT", WARN, "IDLE", CARD_ALT)
        self._featured_callsign.text = ""
        self._featured_type.text = ""
        self._featured_route.text = ""
        self._featured_metrics.text = _wrap_text(body, 22, 2)
        self._featured_metrics_secondary.text = _wrap_text(footer, 22, 2)
        self._featured_owner.text = ""
        self._image_badge.text = ""
        self._side_title.text = "STATUS"
        self._side_list.text = _wrap_text(
            side_text or "Waiting for first nearby aircraft", 13, 5
        )
        self._footer.color = TEXT_MUTED
        self._footer.text = _truncate(footer, 46)

    def show_refreshing(self, detail, source_label):
        self._header_subtitle.text = _truncate(source_label, 24)
        self._featured_status.color = WARN
        self._featured_status.text = "REFRESH"
        self._set_badges("SCAN", WARN, "LIVE", ACCENT_DIM)
        self._side_title.text = "STATUS"
        self._side_list.text = _wrap_text(detail, 13, 5)
        self._footer.color = WARN
        self._footer.text = _truncate(detail, 46)

    def render_snapshot(self, snapshot, ip_address, source_label, stale=False, detail=None):
        featured = snapshot["featured"]
        if featured is None:
            if snapshot.get("has_seen_aircraft"):
                self.show_message(
                    "Quiet Sky",
                    "No aircraft now",
                    "Watching {} miles around watch point".format(self._config.radius_miles),
                    side_text="No aircraft in recent window",
                    use_radar=True,
                )
            else:
                self.show_message(
                    "Quiet Sky",
                    "No planes logged",
                    "Watching {} miles around watch point".format(self._config.radius_miles),
                    side_text="Waiting for first nearby aircraft",
                    use_radar=False,
                )
            return

        self._header_title.text = "PLANE PORTAL"
        self._header_subtitle.text = _truncate(
            "{}  {}".format(source_label, ip_address), 24
        )
        self._side_title.text = "RECENT SKY"
        self.show_radar_snapshot(snapshot)

        self._featured_status.text = featured["status_text"]
        self._featured_status.color = WARN if stale else ACCENT
        self._set_badges(
            featured["status_text"],
            WARN if stale else ACCENT,
            _trend_label(featured["vertical_rate_fpm"]),
            self._trend_color(featured["vertical_rate_fpm"]),
        )
        self._featured_callsign.text = _truncate(featured["callsign"], 6)
        self._featured_type.text = _truncate(self._aircraft_line(featured), 14)
        self._featured_type.color = _altitude_color(featured.get("altitude_ft"))
        self._featured_route.text = _truncate(self._route_badge(featured), 16)
        self._featured_metrics.text = _truncate(self._metric_line(featured), 26)
        self._featured_metrics_secondary.text = _truncate(self._metric_line_secondary(featured), 26)
        self._featured_owner.text = _truncate(self._owner_badge(featured), 26)
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
        return None

    def _metric_line(self, record):
        return "{}  {}  {}".format(
            _distance_label(record["distance_miles"]),
            _altitude_label(record["altitude_ft"]),
            _speed_label(record["speed_kts"]),
        )

    def _metric_line_secondary(self, record):
        return "BRG{:03d}  {}  {}".format(
            record["bearing"],
            _heading_label(record["heading"]),
            _vertical_label(record["vertical_rate_fpm"]),
        )

    def _route_badge(self, record):
        route = self._route_line(record)
        if not route:
            return "NO ROUTE"
        return route.replace(" -> ", ">")

    def _owner_badge(self, record):
        owner = self._owner_line(record)
        if not owner:
            return record.get("category_name") or "Aircraft"
        return _truncate(owner, 20)

    def _trend_color(self, vertical_rate_fpm):
        if vertical_rate_fpm is None:
            return CARD_ALT
        if vertical_rate_fpm > 250:
            return ALT_HIGH
        if vertical_rate_fpm < -250:
            return ALT_LOW
        return TEXT_MUTED

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
        return None

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
            route = self._route_badge(record)
            lines.append(
                "{} {}\n{} {}\n{}".format(
                    record["status_text"][0],
                    _distance_label(record["distance_miles"]),
                    _truncate(record["callsign"], 6),
                    _altitude_label(record["altitude_ft"]),
                    _truncate(route, 12),
                )
            )
        return "\n".join(lines)