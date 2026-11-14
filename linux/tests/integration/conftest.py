"""Integration tests: real GStreamer on a GLib main loop. Run by the `integration` CI job.

Every test module in this folder is skipped where PyGObject or GStreamer is missing (e.g. on Windows).
"""
import pytest

from icy_server import IcyServer

try:
    import gi

    gi.require_version("Gst", "1.0")
    from gi.repository import Gst  # noqa: F401
    MISSING = None
except (ImportError, ValueError) as error:
    MISSING = f"PyGObject with GStreamer is missing: {error}"


class _SkippedModule(pytest.Module):
    """Stands in for a test module that would fail to import: reports it skipped instead."""

    def collect(self):
        pytest.skip(MISSING, allow_module_level=True)


def pytest_pycollect_makemodule(module_path, parent):
    if MISSING:
        return _SkippedModule.from_parent(parent, path=module_path)
    return None


@pytest.fixture(scope="session")
def icy(tmp_path_factory):
    server = IcyServer(tmp_path_factory.mktemp("icy"))
    yield server
    server.close()
