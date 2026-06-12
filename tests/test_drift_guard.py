"""Gate: guard unit — the most security-critical text check in the system."""

from engine.drift_guard import verify_text


ENTITIES = frozenset({"T2", "T1", "S6", "S1", "SEG-12", "SEG-23", "SEG-36"})
NUMBERS = frozenset({34.0, 5.0, 11.0, 29.0})


def test_faithful_text_passes():
    text = "T2 was rerouted via SEG-12 and SEG-23 to SEG-36; arrives S6 at minute 34 (+5 min)."
    assert verify_text(text, ENTITIES, NUMBERS) == []


def test_invented_number_caught():
    text = "T2 arrives S6 at minute 99."
    assert verify_text(text, ENTITIES, NUMBERS) == ["invented number: 99"]


def test_invented_train_caught():
    text = "T9 arrives S6 at minute 34."
    assert verify_text(text, ENTITIES, NUMBERS) == ["invented id: T9"]


def test_invented_segment_and_station_caught():
    text = "T2 takes SEG-99 to S8, arriving minute 34."
    assert verify_text(text, ENTITIES, NUMBERS) == [
        "invented id: S8",
        "invented id: SEG-99",
    ]


def test_ids_do_not_leak_digits_as_numbers():
    # SEG-12 contains '12', T2 contains '2', S6 contains '6' — none of those
    # digits are in NUMBERS, but as parts of allowed ids they must not trip
    # the number check.
    text = "T2 via SEG-12 to S6: minute 34."
    assert verify_text(text, ENTITIES, NUMBERS) == []


def test_decimals_checked():
    assert verify_text("speed factor 0.5", ENTITIES, frozenset({0.5})) == []
    assert verify_text("speed factor 0.7", ENTITIES, frozenset({0.5})) == [
        "invented number: 0.7"
    ]


def test_multiple_violations_all_reported():
    text = "T7 reroutes via SEG-99, arriving minute 88 (+44 min)."
    assert verify_text(text, ENTITIES, NUMBERS) == [
        "invented id: SEG-99",
        "invented id: T7",
        "invented number: 44",
        "invented number: 88",
    ]


def test_signed_and_suffixed_numbers_still_checked():
    # '+5 min' and '5-minute' style both reduce to the number 5
    assert verify_text("+5 min late", ENTITIES, NUMBERS) == []
    assert verify_text("running +6 min late", ENTITIES, NUMBERS) == [
        "invented number: 6"
    ]
