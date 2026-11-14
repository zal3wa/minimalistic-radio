from minimalistic_radio.ui.reorder import drop_index

# Four rows 50 px high: A, B, C, D. Their centres before the drag.
CENTERS = [25, 75, 125, 175]


def test_not_moved_stays():
    assert drop_index(CENTERS, 1, 75) == 1


def test_lands_after_the_rows_it_passed():
    assert drop_index(CENTERS, 1, 126) == 2
    assert drop_index(CENTERS, 1, 176) == 3


def test_reaching_a_centre_is_not_passing_it():
    assert drop_index(CENTERS, 1, 125) == 1
    assert drop_index(CENTERS, 2, 75) == 2


def test_upwards():
    assert drop_index(CENTERS, 3, 74) == 1
    assert drop_index(CENTERS, 3, 24) == 0


def test_past_either_end():
    assert drop_index(CENTERS, 1, 900) == 3
    assert drop_index(CENTERS, 2, -900) == 0


def test_single_row():
    assert drop_index([25], 0, 500) == 0
