from minimalistic_radio.platform.background import autostart_desktop_entry


def test_autostart_desktop_entry():
    text = autostart_desktop_entry("minimalistic-radio --autostart")
    assert "Exec=minimalistic-radio --autostart" in text
    assert "X-GNOME-Autostart-enabled=true" in text
    assert "NoDisplay=true" in text
