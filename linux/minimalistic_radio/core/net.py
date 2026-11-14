"""Small blocking HTTP helpers (standard library only)."""
import json
import urllib.error
import urllib.request
from typing import Any

from minimalistic_radio import VERSION

USER_AGENT = f"MinimalisticRadio/{VERSION} (Linux)"


class NetworkError(Exception):
    pass


def _open(url: str, timeout: float):
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    return urllib.request.urlopen(request, timeout=timeout)


def fetch_bytes(url: str, timeout: float = 10.0, limit: int = 2_000_000) -> bytes:
    try:
        with _open(url, timeout) as response:
            data = response.read(limit + 1)
    except (urllib.error.URLError, OSError, ValueError) as error:
        raise NetworkError(str(error)) from error
    if len(data) > limit:
        raise NetworkError("response too large")
    return data


def fetch_json(url: str, timeout: float = 10.0) -> Any:
    data = fetch_bytes(url, timeout, limit=8 * 1024 * 1024)
    try:
        return json.loads(data.decode("utf-8-sig"))
    except (ValueError, UnicodeDecodeError) as error:
        raise NetworkError(f"bad JSON: {error}") from error
