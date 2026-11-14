import http.client

import pytest

from minimalistic_radio.core import net
from minimalistic_radio.core.net import NetworkError, fetch_bytes, fetch_json


class _Cut:
    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def read(self, n=-1):
        raise http.client.IncompleteRead(b"")


@pytest.mark.parametrize("fetch", [fetch_bytes, fetch_json])
def test_urlopen_http_exception_is_network_error(monkeypatch, fetch):
    def opener(url, timeout):
        raise http.client.BadStatusLine("x")
    monkeypatch.setattr(net, "_open", opener)
    with pytest.raises(NetworkError):
        fetch("http://a/s")


@pytest.mark.parametrize("fetch", [fetch_bytes, fetch_json])
def test_cut_off_read_is_network_error(monkeypatch, fetch):
    monkeypatch.setattr(net, "_open", lambda url, timeout: _Cut())
    with pytest.raises(NetworkError):
        fetch("http://a/s")
