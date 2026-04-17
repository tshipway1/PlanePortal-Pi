"""Broadcastify feed client.

Fetches feed info and stream URLs from Broadcastify feed pages.
Stream URLs contain session tokens and should be fetched fresh each play.
"""

import re

import requests

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux aarch64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
}


def get_feed_info(feed_id):
    """Fetch feed name and stream URL for a Broadcastify feed ID.

    Returns dict: {"feedId": int, "name": str, "streamUrl": str, "online": bool}
    or None on error.
    """
    feed_id = int(feed_id)
    url = f"https://www.broadcastify.com/listen/feed/{feed_id}"
    try:
        resp = requests.get(url, timeout=12, headers=_HEADERS)
        resp.raise_for_status()
    except Exception:
        return None

    # Extract feed name from title
    title_match = re.search(r"<title>(.*?)</title>", resp.text)
    name = title_match.group(1).strip() if title_match else f"Feed {feed_id}"
    # Remove "Broadcastify -" prefix if present
    if " - " in name:
        name = name.split(" - ", 1)[0].strip()

    # Extract relayUrl from ListenPlayer.init() call
    relay_match = re.search(
        r'relayUrl:\s*"([^"]+)"', resp.text
    )
    stream_url = None
    if relay_match:
        stream_url = relay_match.group(1).replace("\\/", "/")

    # Check online status
    online_match = re.search(r"isOnline:\s*(true|false)", resp.text)
    online = online_match.group(1) == "true" if online_match else False

    return {
        "feedId": feed_id,
        "name": name,
        "streamUrl": stream_url,
        "online": online,
    }


def search_feeds_by_state(state_id):
    """Fetch aviation/ATC feeds for a US state.

    state_id: FIPS state code (e.g. 24 for Maryland)
    Returns list of dicts: [{"feedId": int, "name": str}, ...]
    """
    url = f"https://www.broadcastify.com/listen/stid/{state_id}"
    try:
        resp = requests.get(url, timeout=12, headers=_HEADERS)
        resp.raise_for_status()
    except Exception:
        return []

    feed_links = re.findall(
        r'/listen/feed/(\d+)["\'][^>]*>([^<]+)', resp.text
    )

    # Filter for aviation/ATC-related feeds
    atc_keywords = (
        "airport", "atc", "tower", "approach", "tracon",
        "artcc", "center", "departure", "ground control",
        "clearance", "atis", "unicom", "ctaf",
    )
    results = []
    for fid, name in feed_links:
        name_lower = name.lower()
        if any(k in name_lower for k in atc_keywords):
            results.append({"feedId": int(fid), "name": name.strip()})
    return results
