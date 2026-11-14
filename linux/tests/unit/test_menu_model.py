from conftest import item
from minimalistic_radio.platform.menu_model import TRACK_ID, build_tray_menu, mpris_metadata, tooltip


def test_menu_order_and_labels(ctl_playing):
    ids = [m.id for m in build_tray_menu(ctl_playing, str, None)]
    assert ids == ["playback", "stations", "volume", "sleep", "sep:1", "now:station", "now:track", "sep:2", "settings", "quit"]
    menu = {m.id: m for m in build_tray_menu(ctl_playing, str, None)}
    assert menu["playback"].label == "Stop" and menu["volume"].label == "Volume (30%)"
    assert menu["now:station"].enabled is False and menu["now:track"].label == "Leonard Cohen - Everybody Knows"
    assert [s.checked for s in menu["stations"].children] == [True, False] and menu["stations"].children[0].toggle == "radio"


def test_volume_bounds(ctl):
    ctl.set_volume(100)
    children = item(build_tray_menu(ctl, str, None), "volume").children
    assert [m.id for m in children] == ["volume:up", "volume:down", "sep:volume",
                                        "volume:0", "volume:25", "volume:50", "volume:75", "volume:100"]
    v = {m.id: m for m in children}
    assert v["volume:up"].enabled is False and v["volume:down"].enabled and v["volume:0"].label == "Mute"


def test_play_disabled_without_stations(empty_ctl):
    assert item(build_tray_menu(empty_ctl, str, None), "playback").enabled is False


def test_sleep_label_and_checks(ctl):
    ctl.set_sleep_timer(30)
    s = item(build_tray_menu(ctl, str, None), "sleep")
    assert s.label == f"Stops at {ctl.sleep_at:%H:%M}" and item(s.children, "sleep:30").checked and not item(s.children, "sleep:off").checked


def test_update_item_only_when_ready(ctl):
    assert item(build_tray_menu(ctl, str, "Update"), "update").label == "Update"
    assert all(m.id != "update" for m in build_tray_menu(ctl, str, None))


def test_no_now_items_without_station(ctl):
    ids = [m.id for m in build_tray_menu(ctl, str, None)]
    assert ids == ["playback", "stations", "volume", "sleep", "sep:1", "sep:2", "settings", "quit"]


def test_tooltip_truncated(ctl_playing):
    ctl_playing.track = "X" * 400
    title, body = tooltip(ctl_playing)
    assert title == "Minimalistic Radio · Radio A" and len(body) <= 120 and body.endswith("…")


def test_track_item_truncated(ctl_playing):
    ctl_playing.track = "X" * 400
    label = item(build_tray_menu(ctl_playing, str, None), "now:track").label
    assert len(label) <= 120 and label.endswith("…")


def test_mpris_metadata(ctl_playing):
    m = mpris_metadata(ctl_playing)
    assert m["xesam:title"] == "Everybody Knows" and m["xesam:artist"] == ["Leonard Cohen"] and m["xesam:album"] == "Radio A"
    assert m["mpris:trackid"] == TRACK_ID and "mpris:artUrl" not in m


def test_mpris_metadata_station_only(ctl):
    ctl.select(0)
    assert mpris_metadata(ctl)["xesam:title"] == "Alpha"
