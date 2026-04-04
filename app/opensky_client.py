import time


TOKEN_URL = (
    "https://auth.opensky-network.org/auth/realms/opensky-network/protocol/"
    "openid-connect/token"
)
STATES_URL = "https://opensky-network.org/api/states/all"


def _url_encode(value):
    value = str(value)
    safe = "-_.~"
    output = ""
    for char in value:
        codepoint = ord(char)
        is_ascii_alnum = (
            48 <= codepoint <= 57
            or 65 <= codepoint <= 90
            or 97 <= codepoint <= 122
        )
        if is_ascii_alnum or char in safe:
            output += char
        else:
            output += "%{:02X}".format(codepoint)
    return output


class OpenSkyClient:
    def __init__(self, config, session_provider):
        self._config = config
        self._session_provider = session_provider
        self._access_token = None
        self._token_expires_at = 0

    def _headers(self):
        headers = {"Accept": "application/json"}
        if self._config.has_opensky_auth:
            headers["Authorization"] = "Bearer {}".format(self._get_token())
        return headers

    def _get_token(self, force_refresh=False):
        if not self._config.has_opensky_auth:
            return None

        now = time.monotonic()
        if not force_refresh and self._access_token and now < self._token_expires_at:
            return self._access_token

        body = (
            "grant_type=client_credentials&client_id={}&client_secret={}"
        ).format(
            _url_encode(self._config.opensky_client_id),
            _url_encode(self._config.opensky_client_secret),
        )
        response = self._session_provider().post(
            TOKEN_URL,
            data=body,
            headers={
                "Content-Type": "application/x-www-form-urlencoded",
                "Accept": "application/json",
            },
        )
        try:
            if response.status_code >= 400:
                raise RuntimeError("OpenSky token request failed: {}".format(response.status_code))
            payload = response.json()
        finally:
            response.close()

        if not isinstance(payload, dict):
            raise RuntimeError(
                "OpenSky token payload was {}, not object".format(type(payload).__name__)
            )

        access_token = payload.get("access_token")
        expires_in = int(payload.get("expires_in", 1800))
        if not access_token:
            raise RuntimeError("OpenSky token response did not include an access token")

        self._access_token = access_token
        self._token_expires_at = time.monotonic() + max(60, expires_in - 30)
        return self._access_token

    def fetch_states(self, bounds):
        url = (
            "{}?lamin={:.5f}&lomin={:.5f}&lamax={:.5f}&lomax={:.5f}&extended=1"
        ).format(
            STATES_URL,
            bounds["lamin"],
            bounds["lomin"],
            bounds["lamax"],
            bounds["lomax"],
        )

        response = self._session_provider().get(url, headers=self._headers())
        try:
            if response.status_code == 401 and self._config.has_opensky_auth:
                self._get_token(force_refresh=True)
                response.close()
                response = self._session_provider().get(url, headers=self._headers())

            if response.status_code >= 400:
                raise RuntimeError("OpenSky state request failed: {}".format(response.status_code))

            payload = response.json()
        finally:
            response.close()

        if not isinstance(payload, dict):
            raise RuntimeError(
                "OpenSky states payload was {}, not object".format(type(payload).__name__)
            )

        return payload.get("states") or []