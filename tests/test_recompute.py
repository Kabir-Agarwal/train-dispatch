"""Gate: recompute unit — basic behaviour, hand-verified."""

import pytest

from data.baseline import build_network, build_trains
from engine.anomalies import TrackClosed, TrainCancelled, TrainDelayed
from engine.collision import find_conflicts
from engine.errors import UnknownSegmentError, UnknownTrainError
from engine.recompute import recompute_schedule
from engine.scheduler import build_schedule


def recompute(anomalies):
    return recompute_schedule(build_network(), build_trains(), anomalies)


def test_no_impact_anomaly_leaves_everything_unchanged():
    # SEG-36 is used by no train: every action is 'unchanged', schedule equals
    # baseline, zero total delay.
    result = recompute([TrackClosed("SEG-36")])
    baseline_schedule, _ = build_schedule(build_network(), build_trains())
    assert all(a.action == "unchanged" for a in result.actions.values())
    assert result.schedule == baseline_schedule
    assert result.total_added_delay == 0
    assert find_conflicts(list(result.occupancy_table)) == []


def test_cancelled_train_is_excluded_others_proceed():
    result = recompute([TrainCancelled("T3")])
    assert result.actions["T3"].action == "cancelled"
    assert result.actions["T3"].arrivals is None
    assert "T3" not in result.schedule
    assert not any(o.train_id == "T3" for o in result.occupancy_table)
    for tid in ("T1", "T2", "T4", "T5"):
        assert result.actions[tid].action == "unchanged"
    assert result.total_added_delay == 0


def test_stranded_trains_reported_honestly_rest_scheduled():
    # SEG-34 + SEG-45 closed cuts S4 off entirely.
    result = recompute([TrackClosed("SEG-34"), TrackClosed("SEG-45")])
    for tid in ("T1", "T4", "T5"):
        assert result.actions[tid].action == "stranded"
        assert result.actions[tid].arrivals is None
        assert "cannot complete" in result.actions[tid].reason
    for tid in ("T2", "T3"):
        assert result.actions[tid].action == "unchanged"
    assert result.total_added_delay == 0
    assert find_conflicts(list(result.occupancy_table)) == []


def test_admin_delay_without_conflict_is_depart_delayed():
    # T1 +5 creates no conflict: action depart_delayed, S4 at 35.
    result = recompute([TrainDelayed("T1", 5)])
    a = result.actions["T1"]
    assert a.action == "depart_delayed"
    assert a.depart_at == 5
    assert a.arrivals == {"S1": 5, "S2": 15, "S3": 23, "S4": 35}
    assert a.added_delay == 5
    for tid in ("T2", "T3", "T4", "T5"):
        assert result.actions[tid].action == "unchanged"
    assert result.total_added_delay == 5


def test_bad_anomaly_input_rejected_cleanly():
    with pytest.raises(UnknownSegmentError, match="SEG-99"):
        recompute([TrackClosed("SEG-99")])
    with pytest.raises(UnknownTrainError, match="T9"):
        recompute([TrainDelayed("T9", 5)])
