from minimalistic_radio.platform.updates import update_state


def test_update_on_the_remote_only():
    assert update_state({"running-commit": "a", "local-commit": "a", "remote-commit": "b"}) == "update"


def test_restart_when_installed_already():
    assert update_state({"running-commit": "a", "local-commit": "b", "remote-commit": "b"}) == "restart"


def test_nothing_new():
    assert update_state({"running-commit": "a", "local-commit": "a", "remote-commit": "a"}) is None
