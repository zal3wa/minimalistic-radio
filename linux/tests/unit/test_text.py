import pytest

from minimalistic_radio.core.text import MAX_NAME, clean_chars, clean_name, notification_text

BIDI = "؜‎‏‪‫‬‭‮⁦⁧⁨⁩"


@pytest.mark.parametrize("mark", list(BIDI))
def test_each_bidirectional_formatting_character_is_removed(mark):
    assert clean_name(f"Radio{mark} 357") == "Radio 357"


def test_control_characters_are_removed():
    assert clean_name("Radio\x00\x07\n\t\x1b357\x7f\x85") == "Radio357"


def test_a_name_turned_around_is_shown_as_it_is():
    assert clean_name("‮FM 357 oidaR") == "FM 357 oidaR"


def test_joiners_and_variation_selectors_stay():
    family = "\U0001F468‍\U0001F469‍\U0001F467"   # one emoji made of three, joined by ZWJ
    heart = "❤️"                                   # a variation selector picks the emoji form
    assert clean_name(f"Radio {family} {heart}‬ ") == f"Radio {family} {heart}"
    assert clean_chars("a‌b‍c︎") == "a‌b‍c︎"


def test_trimmed_and_cut_to_100_characters():
    assert MAX_NAME == 100
    assert clean_name("   Jazz   ") == "Jazz"
    assert clean_name("x" * 300) == "x" * 100
    assert clean_name("x" * 99 + " y") == "x" * 99   # cut, then trimmed again


def test_nothing_left_is_an_empty_name():
    assert clean_name(None) == "" and clean_name("‮ \n ") == ""


def test_notification_texts_have_no_angle_brackets():
    assert notification_text("<b>Radio</b> & <i>Jazz</i>") == "‹b›Radio‹/b› & ‹i›Jazz‹/i›"
    assert notification_text("Simon & Garfunkel") == "Simon & Garfunkel"
