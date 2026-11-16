import http.client
import socket
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from minimalistic_radio.core import addresses, net
from minimalistic_radio.core.net import NetworkError, fetch_bytes, fetch_json, fetch_picture, redirect_allowed


class _Cut:
    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def read(self, n=-1):
        raise http.client.IncompleteRead(b"")


@pytest.mark.parametrize("fetch", [fetch_bytes, fetch_json])
def test_urlopen_http_exception_is_network_error(monkeypatch, fetch):
    def opener(url, download):
        raise http.client.BadStatusLine("x")
    monkeypatch.setattr(net, "_open", opener)
    with pytest.raises(NetworkError):
        fetch("http://a/s")


@pytest.mark.parametrize("fetch", [fetch_bytes, fetch_json])
def test_cut_off_read_is_network_error(monkeypatch, fetch):
    monkeypatch.setattr(net, "_open", lambda url, download: _Cut())
    with pytest.raises(NetworkError):
        fetch("http://a/s")


# ---- Against a server on this computer ----

class _Server:
    """http://127.0.0.1:<port>: /payload, /r/<n> (n redirects before the payload), /to?<address> (a redirect
    there) and /slow (a byte every 50 ms, without end)."""

    def __init__(self) -> None:
        self.paths: list[str] = []
        server = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def do_GET(self):
                server.paths.append(self.path)
                if self.path == "/payload":
                    self._send(b"payload")
                elif self.path.startswith("/r/"):
                    left = int(self.path[3:])
                    self._redirect(f"/r/{left - 1}" if left > 1 else "/payload")
                elif self.path.startswith("/to?"):
                    self._redirect(self.path[4:])
                elif self.path == "/slow":
                    self.send_response(200)
                    self.send_header("Content-Length", "1000000")
                    self.end_headers()
                    try:
                        while True:
                            self.wfile.write(b"x")
                            self.wfile.flush()
                            time.sleep(0.05)
                    except OSError:
                        pass

            def _send(self, body):
                self.send_response(200)
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def _redirect(self, where):
                self.send_response(302)
                self.send_header("Location", where)
                self.send_header("Content-Length", "0")
                self.end_headers()

        self.httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.httpd.daemon_threads = True
        self.port = self.httpd.server_address[1]
        threading.Thread(target=self.httpd.serve_forever, args=(0.05,), daemon=True).start()

    def url(self, path: str) -> str:
        return f"http://127.0.0.1:{self.port}{path}"


@pytest.fixture
def server():
    running = _Server()
    yield running
    running.httpd.shutdown()
    running.httpd.server_close()


@pytest.fixture
def home(monkeypatch):
    """127.0.0.1 (the test server) doesn't count as the local network; every other address as usual. Gives the
    addresses connected to."""
    rule = addresses.local_address
    monkeypatch.setattr(addresses, "local_address", lambda address: address != "127.0.0.1" and rule(address))
    connected = []
    connect = net._TimedSocket.connect
    monkeypatch.setattr(net._TimedSocket, "connect", lambda sock, where: connected.append(where[0]) or connect(sock, where))
    return connected


@pytest.fixture
def names(monkeypatch):
    """Names that resolve to the address given (name → address)."""
    table = {}
    resolve = socket.getaddrinfo

    def fake(host, port, *args, **kwargs):
        if host in table:
            return [(socket.AF_INET, socket.SOCK_STREAM, socket.IPPROTO_TCP, "", (table[host], port))]
        return resolve(host, port, *args, **kwargs)
    monkeypatch.setattr(net.socket, "getaddrinfo", fake)
    return table


def test_a_download_and_its_redirects(server):
    assert fetch_bytes(server.url("/payload")) == b"payload"
    assert fetch_bytes(server.url("/r/5")) == b"payload"


def test_more_than_five_redirects_fail(server):
    with pytest.raises(NetworkError):
        fetch_bytes(server.url("/r/6"))
    assert "/payload" not in server.paths


def test_redirects_go_only_to_http_or_https(server):
    listener = socket.create_server(("127.0.0.1", 0))   # an FTP server would be asked here
    listener.settimeout(0.5)
    try:
        with pytest.raises(NetworkError):
            fetch_bytes(server.url(f"/to?ftp://127.0.0.1:{listener.getsockname()[1]}/x"))
        with pytest.raises(socket.timeout):
            listener.accept()[0].close()
    finally:
        listener.close()
    for where in ("file:///etc/hostname", "data:,x", "javascript:x"):
        with pytest.raises(NetworkError):
            fetch_bytes(server.url("/to?" + where))


def test_the_redirect_rule():
    assert redirect_allowed("http://a.example/x") and redirect_allowed("HTTPS://a.example/x")
    for url in ("ftp://a.example/x", "file:///etc/hostname", "data:,x", "gopher://a.example/", "https:///x"):
        assert not redirect_allowed(url)


def test_only_web_addresses_are_fetched():
    for url in ("file:///etc/hostname", "ftp://127.0.0.1/x", "data:,x", "nothing"):
        with pytest.raises(NetworkError):
            fetch_bytes(url)


def test_a_download_stops_at_its_deadline(server):
    started = time.monotonic()
    with pytest.raises(NetworkError):
        fetch_bytes(server.url("/slow"), timeout=5, deadline=0.5)
    assert time.monotonic() - started < 2.5   # not the 5 s of one read, nor the 20 000 s of the whole


def test_every_download_has_a_30_second_deadline():
    assert net.DEADLINE == 30


def test_pictures_never_come_from_the_local_network(server):
    with pytest.raises(NetworkError):
        fetch_picture(server.url("/payload"), 1000)
    for url in ("http://localhost/x.png", "http://nas.local/x.png", "http://router.lan/x.png",
                "http://nas.home.arpa/x.png", "http://[::1]/x.png", "http://192.168.1.1/x.png"):
        with pytest.raises(NetworkError):
            fetch_picture(url, 1000)
    assert server.paths == []


def test_a_name_on_the_local_network_is_refused_when_connecting(server, names):
    names["logo.example"] = "127.0.0.1"
    with pytest.raises(NetworkError):
        fetch_picture(f"http://logo.example:{server.port}/payload", 1000)
    assert server.paths == []


def test_the_address_checked_is_the_one_connected_to(server, names, home):
    names["logo.example"] = "127.0.0.1"
    assert fetch_picture(f"http://logo.example:{server.port}/payload", 1000) == b"payload"
    assert home == ["127.0.0.1"]


def test_every_redirect_of_a_picture_is_checked(server, names, home):
    assert fetch_picture(server.url("/r/2"), 1000) == b"payload" and home == ["127.0.0.1"] * 3
    names["nas.example"] = "10.9.9.9"
    for where in (f"http://nas.example:{server.port}/payload", f"http://localhost:{server.port}/payload",
                  f"http://192.168.1.1:{server.port}/payload"):
        home.clear()
        with pytest.raises(NetworkError):
            fetch_picture(server.url("/to?" + where), 1000)
        assert home == ["127.0.0.1"]   # the first hop only
    assert server.paths.count("/payload") == 1


def test_a_picture_too_big_fails(server, home):
    with pytest.raises(NetworkError):
        fetch_picture(server.url("/payload"), 3)
