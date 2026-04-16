"""OpenSky Network API client for PlanePortal Pi.

Handles OAuth2 client credentials and live state vector fetching.
"""

import time
import requests


TOKEN_URL = (
    "https://auth.opensky-network.org/auth/realms/opensky-network/protocol/"
    "openid-connect/token"
)
STATES_URL = "https://opensky-network.org/api/states/all"


class OpenSkyClient:
    def __init__(self, config):
        self._config = config
        self._session = requests.Session()
        self._access_token = None
        self._token_expires_at = 0

    def _headers(self):
        headers = {"Accept": "application/json"}
        if self._config.has_opensky_auth:
            token = self._get_token()
            if token:
                headers["Authorization"] = f"Bearer {token}"
        return headers

    def _get_token(self, force_refresh=False):
        if not self._config.has_opensky_auth:
            return None

        now = time.monotonic()
        if not force_refresh and self._access_token and now < self._token_expires_at:
            return self._access_token

        response = self._session.post(
            TOKEN_URL,
            data={
                "grant_type": "client_credentials",
                "client_id": self._config.opensky_client_id,
                "client_secret": self._config.opensky_client_secret,
            },
            headers={
                "Content-Type": "application/x-www-form-urlencoded",
                "Accept": "application/json",
            },
            timeout=15,
        )
        if response.status_code >= 400:
            raise RuntimeError(
                f"OpenSky token request failed: {response.status_code}"
            )

        payload = response.json()
        access_token = payload.get("access_token")
        expires_in = int(payload.get("expires_in", 1800))
        if not access_token:
            raise RuntimeError("OpenSky token response missing access_token")

        self._access_token = access_token
        self._token_expires_at = time.monotonic() + max(60, expires_in - 30)
        return self._access_token

    def fetch_states(self, bounds):
        params = {
            "lamin": f"{bounds['lamin']:.5f}",
            "lomin": f"{bounds['lomin']:.5f}",
            "lamax": f"{bounds['lamax']:.5f}",
            "lomax": f"{bounds['lomax']:.5f}",
            "extended": "1",
        }

        response = self._session.get(
            STATES_URL, params=params, headers=self._headers(), timeout=20
        )

        if response.status_code == 401 and self._config.has_opensky_auth:
            self._get_token(force_refresh=True)
            response = self._session.get(
                STATES_URL, params=params, headers=self._headers(), timeout=20
            )

        if response.status_code >= 400:
            raise RuntimeError(
                f"OpenSky state request failed: {response.status_code}"
            )

        payload = response.json()
        if not isinstance(payload, dict):
            raise RuntimeError(
                f"OpenSky states payload was {type(payload).__name__}, not dict"
            )

        return payload.get("states") or []
