"""Gate: reachability unit. Hand-verified on the baseline network.

Baseline segments: SEG-12 S1-S2, SEG-23 S2-S3, SEG-34 S3-S4, SEG-45 S4-S5,
SEG-56 S5-S6, SEG-15 S1-S5, SEG-26 S2-S6.
S4 touches ONLY SEG-34 and SEG-45.
"""

from data.baseline import build_network
from engine.anomalies import TrackClosed, apply_anomalies
from engine.impact import destination_reachable


def test_baseline_fully_connected():
    net = build_network()
    assert destination_reachable(net, "S1", "S4") is True
    assert destination_reachable(net, "S6", "S3") is True


def test_alternative_route_survives_one_closure():
    # SEG-34 closed: S1 -> S4 still works via S1-S5 (SEG-15) + S5-S4 (SEG-45).
    eff = apply_anomalies(build_network(), [TrackClosed("SEG-34")])
    assert destination_reachable(eff, "S1", "S4") is True


def test_s4_cut_off_when_both_its_segments_close():
    eff = apply_anomalies(
        build_network(), [TrackClosed("SEG-34"), TrackClosed("SEG-45")]
    )
    assert destination_reachable(eff, "S1", "S4") is False
    assert destination_reachable(eff, "S4", "S1") is False  # both directions
    # the rest of the network is still connected
    assert destination_reachable(eff, "S1", "S6") is True


def test_same_station_trivially_reachable():
    assert destination_reachable(build_network(), "S2", "S2") is True
