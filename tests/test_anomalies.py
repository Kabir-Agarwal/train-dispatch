"""Gate: anomalies unit. Types, validation, application — hand-verified values."""

import pytest

from data.baseline import build_network, build_trains
from engine.anomalies import (
    ReducedSpeed,
    TrackBlocked,
    TrackClosed,
    TrainCancelled,
    TrainDelayed,
    apply_anomalies,
    delay_minutes,
    validate_anomalies,
)
from engine.errors import UnknownSegmentError, UnknownTrainError, ValidationError


def test_valid_anomalies_pass():
    validate_anomalies(
        build_network(),
        build_trains(),
        [
            TrackClosed("SEG-34"),
            TrackBlocked("SEG-12"),
            ReducedSpeed("SEG-56", 0.5),
            TrainCancelled("T3"),
            TrainDelayed("T1", 5),
        ],
    )  # must not raise


def test_unknown_segment_rejected():
    with pytest.raises(UnknownSegmentError, match="SEG-99"):
        validate_anomalies(build_network(), build_trains(), [TrackClosed("SEG-99")])


def test_unknown_train_rejected():
    with pytest.raises(UnknownTrainError, match="T9"):
        validate_anomalies(build_network(), build_trains(), [TrainCancelled("T9")])


def test_bad_factor_rejected():
    for factor in (0, 1, 1.5, -0.3):
        with pytest.raises(ValidationError, match="factor"):
            validate_anomalies(
                build_network(), build_trains(), [ReducedSpeed("SEG-56", factor)]
            )


def test_bad_delay_minutes_rejected():
    for minutes in (0, -5):
        with pytest.raises(ValidationError, match="minutes"):
            validate_anomalies(
                build_network(), build_trains(), [TrainDelayed("T1", minutes)]
            )


def test_empty_anomaly_list_rejected():
    with pytest.raises(ValidationError, match="no anomalies"):
        validate_anomalies(build_network(), build_trains(), [])


def test_apply_track_closed_marks_segment_closed():
    net = build_network()
    eff = apply_anomalies(net, [TrackClosed("SEG-34")])
    assert eff.segment("SEG-34").status == "closed"
    assert eff.segment("SEG-12").status == "open"  # others untouched
    assert net.segment("SEG-34").status == "open"  # original unchanged


def test_apply_track_blocked_same_routing_effect():
    eff = apply_anomalies(build_network(), [TrackBlocked("SEG-34")])
    assert eff.segment("SEG-34").status == "closed"


def test_apply_reduced_speed_changes_effective_time():
    # SEG-56 is 9 min; at half speed ceil(9/0.5) = 18 min.
    eff = apply_anomalies(build_network(), [ReducedSpeed("SEG-56", 0.5)])
    seg = eff.segment("SEG-56")
    assert seg.status == "reduced-speed"
    assert seg.effective_travel_time() == 18
    assert build_network().segment("SEG-56").effective_travel_time() == 9


def test_closed_beats_reduced_on_same_segment():
    eff = apply_anomalies(
        build_network(), [ReducedSpeed("SEG-34", 0.5), TrackClosed("SEG-34")]
    )
    assert eff.segment("SEG-34").status == "closed"


def test_multiple_delays_for_one_train_add_up():
    assert delay_minutes([TrainDelayed("T1", 5), TrainDelayed("T1", 7)]) == {"T1": 12}
