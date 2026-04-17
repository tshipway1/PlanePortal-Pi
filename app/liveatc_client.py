"""LiveATC feed pattern generator.

Generates common feed mount name patterns for a given airport ICAO code.
LiveATC uses Cloudflare protection, so we cannot scrape their feed list.
Instead we provide well-known naming patterns that cover most airports.
"""


# Common feed type suffixes used by LiveATC
FEED_TYPES = [
    ("Twr", "Tower"),
    ("App", "Approach"),
    ("Gnd", "Ground"),
    ("Del", "Clearance"),
    ("Dep", "Departure"),
    ("ATIS", "ATIS"),
    ("App_Final", "Final Approach"),
    ("Ctr", "Center/ARTCC"),
]


def feed_patterns(icao):
    """Generate common LiveATC feed patterns for an ICAO code.

    Returns list of dicts: [{"mount": "KJFK_Twr", "label": "Tower"}, ...]
    """
    icao = icao.strip().upper()
    if not icao or len(icao) < 3 or len(icao) > 4:
        return []
    return [
        {"mount": f"{icao}_{suffix}", "label": label}
        for suffix, label in FEED_TYPES
    ]


def hlisten_url(mount, icao):
    """Build the LiveATC player page URL for a feed mount."""
    return f"https://www.liveatc.net/hlisten.php?mount={mount}&icao={icao}"
