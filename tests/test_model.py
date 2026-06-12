"""Gate: model unit. Every assert is a hand-verified expected value."""

import pytest

from engine.errors import UnknownSegmentError, ValidationError
from engine.model import Network, Segment


def small_network():
    return Network(
        stations=["S1", "S2", "S3"],
        segments=[
            Segment("SEG-12", ("S1", "S2"), 10),
            Segment("SEG-23", ("S2", "S3"), 8),
        ],
    )


def test_segment_lookup_returns_hand_verified_travel_time():
    net = small_network()
    assert net.segment("SEG-12").travel_time == 10
    assert net.segment("SEG-23").travel_time == 8
    assert net.segment("SEG-12").endpoints == ("S1", "S2")
    assert net.segment("SEG-12").status == "open"


def test_unknown_segment_raises_clear_error():
    net = small_network()
    with pytest.raises(UnknownSegmentError, match="SEG-99"):
        net.segment("SEG-99")


def test_other_end():
    net = small_network()
    seg = net.segment("SEG-12")
    assert Network.other_end(seg, "S1") == "S2"
    assert Network.other_end(seg, "S2") == "S1"
    with pytest.raises(ValidationError, match="S3"):
        Network.other_end(seg, "S3")


def test_segment_with_unknown_endpoint_rejected():
    with pytest.raises(ValidationError, match="S9"):
        Network(["S1", "S2"], [Segment("SEG-X", ("S1", "S9"), 5)])


def test_nonpositive_travel_time_rejected():
    with pytest.raises(ValidationError, match="travel_time"):
        Network(["S1", "S2"], [Segment("SEG-X", ("S1", "S2"), 0)])


def test_duplicate_segment_id_rejected():
    with pytest.raises(ValidationError, match="duplicate segment id"):
        Network(
            ["S1", "S2"],
            [Segment("SEG-X", ("S1", "S2"), 5), Segment("SEG-X", ("S2", "S1"), 6)],
        )


def test_bad_status_rejected():
    with pytest.raises(ValidationError, match="status"):
        Network(["S1", "S2"], [Segment("SEG-X", ("S1", "S2"), 5, status="broken")])


def test_effective_travel_time_hand_verified():
    # 12 min at half speed -> ceil(12/0.5) = 24; 20 min at 0.8 -> ceil(25) = 25;
    # full speed unchanged; 7 min at 0.9 -> ceil(7.78) = 8 (rounds UP, never down).
    assert Segment("X", ("S1", "S2"), 12, speed_factor=0.5).effective_travel_time() == 24
    assert Segment("X", ("S1", "S2"), 20, speed_factor=0.8).effective_travel_time() == 25
    assert Segment("X", ("S1", "S2"), 10).effective_travel_time() == 10
    assert Segment("X", ("S1", "S2"), 7, speed_factor=0.9).effective_travel_time() == 8


def test_bad_speed_factor_rejected():
    for factor in (0, -0.5, 1.5):
        with pytest.raises(ValidationError, match="speed_factor"):
            Network(["S1", "S2"], [Segment("X", ("S1", "S2"), 5, speed_factor=factor)])


def test_stations_are_appendable():
    net = small_network()
    net.add_station("S4")
    assert net.stations == ["S1", "S2", "S3", "S4"]
    net.add_segment(Segment("SEG-34", ("S3", "S4"), 6))
    assert net.segment("SEG-34").travel_time == 6
    with pytest.raises(ValidationError, match="already exists"):
        net.add_station("S4")
