import pytest

from minimalistic_radio.core.addresses import local_address, local_name, refused


@pytest.mark.parametrize("address", [
    "127.0.0.1", "127.255.0.9",                    # loopback
    "10.0.0.1", "10.255.255.255",                  # private
    "172.16.0.1", "172.31.255.255",
    "192.168.0.1", "192.168.1.1",
    "169.254.0.1", "169.254.169.254",              # link-local
    "100.64.0.1", "100.127.255.255",               # carrier-grade NAT
    "0.0.0.0", "0.1.2.3",                          # unspecified, "this network"
    "192.0.0.1", "198.18.0.1", "198.19.255.255",   # reserved, benchmarking
    "224.0.0.251", "239.255.255.250",              # multicast
    "240.0.0.1", "255.255.255.255",                # reserved, broadcast
    "::", "::1",
    "fe80::1", "fe80::1%eth0", "febf::1",          # link-local, with and without a zone
    "fc00::1", "fd12:3456::1",                     # unique local
    "::ffff:192.168.1.1", "::ffff:127.0.0.1", "::ffff:10.0.0.1", "::ffff:100.64.0.1",   # IPv4-mapped
    "not an address", "",
])
def test_local_and_reserved_addresses(address):
    assert local_address(address)


@pytest.mark.parametrize("address", [
    "8.8.8.8", "1.1.1.1", "93.184.216.34", "223.255.255.255",
    "9.255.255.255", "11.0.0.0", "172.15.255.255", "172.32.0.0", "192.167.255.255", "192.169.0.0",
    "100.63.255.255", "100.128.0.0", "169.253.255.255", "198.17.255.255", "198.20.0.0", "192.0.1.0",
    "2a00:1450:4001:82a::200e", "2001:4860:4860::8888", "::ffff:8.8.8.8",
])
def test_public_addresses(address):
    assert not local_address(address)


@pytest.mark.parametrize("host", [
    "localhost", "LOCALHOST", "localhost.", "printer.localhost",
    "nas.local", "router.lan", "box.home", "service.internal", "nas.home.arpa", "NAS.Home.Arpa.",
    "127.0.0.1", "10.0.0.8", "192.168.1.1", "::1", "[::1]", "fe80::1", "::ffff:192.168.1.1", "",
])
def test_local_names(host):
    assert local_name(host)


@pytest.mark.parametrize("host", [
    "i.iheart.com", "is1-ssl.mzstatic.com", "localhost.example.com", "local.example", "lan.example.org",
    "home.example", "internal.example", "8.8.8.8", "2001:4860:4860::8888",
])
def test_public_names(host):
    assert not local_name(host)


def test_a_name_that_resolves_to_the_local_network_is_refused():
    assert refused("logo.example", lambda host: ["10.0.0.5"])
    assert refused("logo.example", lambda host: ["93.184.216.34", "192.168.1.20"])   # any address it has
    assert refused("logo.example", lambda host: ["::ffff:127.0.0.1"])
    assert refused("logo.example", lambda host: ["fe80::1%2"])


def test_a_name_on_the_internet_passes():
    assert not refused("logo.example", lambda host: ["93.184.216.34", "2606:2800:220:1:248:1893:25c8:1946"])
    assert not refused("8.8.8.8", lambda host: ["8.8.8.8"])


def test_a_local_name_is_refused_without_resolving_it():
    asked = []
    assert refused("nas.local", lambda host: asked.append(host) or ["93.184.216.34"])
    assert refused("127.0.0.1", lambda host: asked.append(host) or ["93.184.216.34"])
    assert asked == []


def test_a_name_that_doesnt_resolve_is_refused():
    def broken(host):
        raise OSError("no such name")
    assert refused("logo.example", broken)
    assert refused("logo.example", lambda host: [])
