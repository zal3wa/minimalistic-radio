"""Small blocking HTTP helpers (standard library only).

Every download has an overall deadline (DEADLINE seconds) besides the timeout of each read, so a server that sends
a byte now and then can't hold it for hours, and follows at most MAX_REDIRECTS redirects, only to http and https.
Pictures (fetch_picture) never come from the local network (core/addresses.py): the name of the first address and
of every redirect is checked, and so is each address it resolves to, when connecting, so the address checked is the
one used. Through a proxy only the name is checked: the proxy resolves it.
"""
from __future__ import annotations

import functools
import http.client
import json
import socket
import ssl
import time
import urllib.error
import urllib.request
from typing import Any
from urllib.parse import urlsplit

from minimalistic_radio import VERSION

from . import addresses
from .streams import is_web_url

USER_AGENT = f"MinimalisticRadio/{VERSION} (Linux)"
DEADLINE = 30.0       # seconds for a whole download
MAX_REDIRECTS = 5


class NetworkError(Exception):
    pass


class _Refused(OSError):
    """A picture address on the local network."""


def redirect_allowed(url: str) -> bool:
    """Redirects are followed only to http and https addresses."""
    return is_web_url(url)


class _Download:
    """One download: its deadline, and whether it is a picture (never from the local network)."""

    def __init__(self, timeout: float, deadline: float, picture: bool) -> None:
        self.timeout = timeout
        self.end = time.monotonic() + deadline
        self.picture = picture

    def wait(self) -> float:
        """How long the next step may block: the timeout, less near the deadline. TimeoutError after it."""
        left = self.end - time.monotonic()
        if left <= 0:
            raise TimeoutError("the download took too long")
        return min(self.timeout, left)

    def refuses_name(self, host: str | None) -> bool:
        return self.picture and addresses.local_name(host or "")

    def connect(self, address: tuple[str, int], _timeout: Any = None, source_address: Any = None, *,
                direct: bool) -> socket.socket:
        """socket.create_connection, with the deadline on every read. For a picture, a direct connection is made
        only when none of the addresses the name resolves to is on the local network."""
        host, port = address
        found = socket.getaddrinfo(host, port, 0, socket.SOCK_STREAM)
        if self.picture and direct and addresses.refused(host, lambda _host: [info[4][0] for info in found]):
            raise _Refused("a picture on the local network")
        error: OSError | None = None
        for family, kind, proto, _name, where in found:
            sock = _TimedSocket(family, kind, proto)
            sock.download = self
            try:
                sock.settimeout(self.wait())
                if source_address:
                    sock.bind(source_address)
                sock.connect(where)
                return sock
            except OSError as failure:
                error = failure
                sock.close()
        raise error or OSError("the name has no address")


class _TimedSocket(socket.socket):
    """Each read waits at most until the download's deadline."""
    download: _Download | None = None

    def recv(self, size: int, flags: int = 0) -> bytes:
        if self.download is not None:
            self.settimeout(self.download.wait())
        return super().recv(size, flags)

    def recv_into(self, buffer: Any, size: int = 0, flags: int = 0) -> int:
        if self.download is not None:
            self.settimeout(self.download.wait())
        return super().recv_into(buffer, size, flags)


class _TimedSSLSocket(ssl.SSLSocket):
    """The same for https (the context below makes these)."""
    download: _Download | None = None

    def recv(self, size: int = 1024, flags: int = 0) -> bytes:
        if self.download is not None:
            self.settimeout(self.download.wait())
        return super().recv(size, flags)

    def recv_into(self, buffer: Any, size: int | None = None, flags: int = 0) -> int:
        if self.download is not None:
            self.settimeout(self.download.wait())
        return super().recv_into(buffer, size, flags)


@functools.cache
def _tls() -> ssl.SSLContext:
    """What urllib would use (the system's certificates, HTTP/1.1), with timed sockets."""
    context = ssl.create_default_context()
    context.set_alpn_protocols(["http/1.1"])
    context.sslsocket_class = _TimedSSLSocket
    return context


class _Connection(http.client.HTTPConnection):
    def __init__(self, host: str, *, download: _Download, direct: bool, **kwargs: Any) -> None:
        super().__init__(host, **kwargs)
        self._create_connection = functools.partial(download.connect, direct=direct)


class _SecureConnection(http.client.HTTPSConnection):
    def __init__(self, host: str, *, download: _Download, direct: bool, **kwargs: Any) -> None:
        super().__init__(host, **kwargs)
        self._download = download
        self._create_connection = functools.partial(download.connect, direct=direct)

    def connect(self) -> None:
        super().connect()
        self.sock.download = self._download   # the TLS socket that replaced the plain one


def _direct(request: urllib.request.Request) -> bool:
    """Not through a proxy (https through a proxy is a tunnel to it)."""
    return not (request.has_proxy() or getattr(request, "_tunnel_host", None))


class _HTTPHandler(urllib.request.HTTPHandler):
    def __init__(self, download: _Download) -> None:
        super().__init__()
        self._download = download

    def http_open(self, req: urllib.request.Request) -> http.client.HTTPResponse:
        return self.do_open(functools.partial(_Connection, download=self._download, direct=_direct(req)), req)


class _HTTPSHandler(urllib.request.HTTPSHandler):
    def __init__(self, download: _Download) -> None:
        super().__init__(context=_tls())
        self._download = download

    def https_open(self, req: urllib.request.Request) -> http.client.HTTPResponse:
        return self.do_open(functools.partial(_SecureConnection, download=self._download, direct=_direct(req)),
                            req, context=self._context)


class _Redirects(urllib.request.HTTPRedirectHandler):
    max_redirections = MAX_REDIRECTS

    def __init__(self, download: _Download) -> None:
        self._download = download

    def redirect_request(self, req, fp, code, msg, headers, newurl):  # noqa: ANN001 - urllib's signature
        if not redirect_allowed(newurl) or self._download.refuses_name(urlsplit(newurl).hostname):
            raise urllib.error.HTTPError(newurl, code, "a redirect to an address that isn't followed", headers, fp)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def _open(url: str, download: _Download) -> Any:
    """The response, through an opener that knows only http and https."""
    opener = urllib.request.OpenerDirector()
    for handler in (urllib.request.ProxyHandler(), urllib.request.UnknownHandler(), _HTTPHandler(download),
                    _HTTPSHandler(download), urllib.request.HTTPDefaultErrorHandler(), _Redirects(download),
                    urllib.request.HTTPErrorProcessor()):
        opener.add_handler(handler)
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    return opener.open(request, timeout=download.wait())


def _fetch(url: str, timeout: float, limit: int, deadline: float, picture: bool) -> bytes:
    download = _Download(timeout, deadline, picture)
    if not is_web_url(url) or download.refuses_name(urlsplit(url).hostname):
        raise NetworkError("an address that isn't fetched")
    try:
        with _open(url, download) as response:
            data = response.read(limit + 1)
    except (urllib.error.URLError, http.client.HTTPException, OSError, ValueError) as error:
        raise NetworkError(str(error)) from error
    if len(data) > limit:
        raise NetworkError("response too large")
    return data


def fetch_bytes(url: str, timeout: float = 10.0, limit: int = 2_000_000, deadline: float = DEADLINE) -> bytes:
    """The body at an http or https address, at most `limit` bytes."""
    return _fetch(url, timeout, limit, deadline, picture=False)


def fetch_picture(url: str, limit: int, timeout: float = 10.0, deadline: float = DEADLINE) -> bytes:
    """A picture's bytes (a logo, a cover): like fetch_bytes, but never from the local network."""
    return _fetch(url, timeout, limit, deadline, picture=True)


def fetch_json(url: str, timeout: float = 10.0) -> Any:
    data = fetch_bytes(url, timeout, limit=8 * 1024 * 1024)
    try:
        return json.loads(data.decode("utf-8-sig"))
    except (ValueError, UnicodeDecodeError) as error:
        raise NetworkError(f"bad JSON: {error}") from error
