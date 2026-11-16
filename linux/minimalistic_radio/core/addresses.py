"""Where pictures are never fetched from: the local network (the same rule on Windows and macOS).

A picture address (a logo, a cover) can come from a share link or a stream. Fetching it from a name or an address on
the home network would let a stranger make the radio ask a router or a printer something. Streams don't follow this
rule: a station on the home network still plays.
"""
from __future__ import annotations

from ipaddress import IPv6Address, ip_address, ip_network
from typing import Callable, Iterable

LOCAL_SUFFIXES = (".localhost", ".local", ".lan", ".home", ".internal", ".home.arpa")

# Loopback, private, link-local, carrier-grade NAT, multicast, unspecified and reserved; IPv4-mapped IPv6 addresses
# are checked as the IPv4 address they carry.
_IPV4 = tuple(ip_network(n) for n in (
    "0.0.0.0/8", "10.0.0.0/8", "100.64.0.0/10", "127.0.0.0/8", "169.254.0.0/16", "172.16.0.0/12",
    "192.0.0.0/24", "192.168.0.0/16", "198.18.0.0/15", "224.0.0.0/4", "240.0.0.0/4"))
_IPV6 = tuple(ip_network(n) for n in ("::/128", "::1/128", "fc00::/7", "fe80::/10"))


def local_address(text: str) -> bool:
    """An IP address pictures are never fetched from; also any text that isn't an IP address."""
    try:
        address = ip_address(text.split("%", 1)[0])   # without an IPv6 zone (fe80::1%eth0)
    except ValueError:
        return True
    if isinstance(address, IPv6Address) and address.ipv4_mapped is not None:
        address = address.ipv4_mapped
    return any(address in network for network in (_IPV4 if address.version == 4 else _IPV6))


def local_name(host: str) -> bool:
    """A host name (or an IP address written as one) on the local network, known without asking DNS."""
    name = host.strip().strip("[]").lower().rstrip(".")
    if not name or name == "localhost" or name.endswith(LOCAL_SUFFIXES):
        return True
    try:
        ip_address(name.split("%", 1)[0])
    except ValueError:
        return False   # a name: DNS tells where it is
    return local_address(name)


def refused(host: str, resolve: Callable[[str], Iterable[str]]) -> bool:
    """Whether a picture may not be fetched from `host`: a local name, or a name with any address on the local
    network (`resolve` gives its addresses). A name that can't be resolved is refused too."""
    if local_name(host):
        return True
    try:
        found = list(resolve(host))
    except OSError:
        return True
    return not found or any(local_address(address) for address in found)
