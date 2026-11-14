"""Stream URL rules, mirroring IsWebUrl and StreamKey in src/Services/Storage.cs."""
from urllib.parse import urlsplit

_DEFAULT_PORTS = {"http": 80, "https": 443}


def is_web_url(value: str | None) -> bool:
    if not value:
        return False
    try:
        parts = urlsplit(value)
        parts.port  # noqa: B018 - raises ValueError for a malformed port
    except ValueError:
        return False
    return (parts.scheme.lower() in _DEFAULT_PORTS and bool(parts.hostname)
            and "@" not in parts.netloc)


def stream_key(url: str | None) -> str:
    text = (url or "").strip()
    try:
        parts = urlsplit(text)
        port = parts.port
    except ValueError:
        return text
    if not parts.scheme or not parts.hostname:
        return text
    show_port = port is not None and port != _DEFAULT_PORTS.get(parts.scheme.lower())
    key = parts.hostname.lower() + (f":{port}" if show_port else "") + parts.path.rstrip("/")
    if parts.query:
        key += "?" + parts.query
    return key


def same_stream(a: str | None, b: str | None) -> bool:
    return stream_key(a) == stream_key(b)
