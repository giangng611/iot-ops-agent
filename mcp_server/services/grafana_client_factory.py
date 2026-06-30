import os
import threading

from grafana_client import GrafanaApi, TokenAuth

_lock = threading.Lock()
_client = None


def _build_credential():
    api_key = os.getenv("GRAFANA_API_KEY")

    if api_key:
        return TokenAuth(api_key)

    username = os.getenv("GRAFANA_USERNAME")
    password = os.getenv("GRAFANA_PASSWORD")

    if username and password:
        return (username, password)

    return None


def get_pooled_grafana_client():
    global _client

    with _lock:
        if _client is None:
            url = os.getenv("GRAFANA_URL")

            if not url:
                raise RuntimeError("GRAFANA_URL is not configured.")

            timeout_seconds = float(os.getenv("GRAFANA_TIMEOUT_SECONDS", "10"))
            _client = GrafanaApi.from_url(
                url=url,
                credential=_build_credential(),
                timeout=timeout_seconds,
            )

        return _client
