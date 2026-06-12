"""Gate: impact unit. Detection only — every value hand-verified.

Baseline occupancies (from data/baseline.py docstring):
  T1: SEG-12[0,10] SEG-23[10,18] SEG-34[18,30]
  T2: SEG-15[5,20] SEG-56[20,29]
  T3: SEG-26[12,32]
  T4: SEG-45[23,30] SEG-56[30,39]
  T5: SEG-34[40,52] SEG-23[52,60] SEG-12[60,70]
"""

from data.baseline import build_network, build_trains
from engine.anomalies import (
    ReducedSpeed,
    TrackBlocked,
    TrackClosed,
    TrainCancelled,
    TrainDelayed,
)
from engine.collision import Conflict
from engine.impact import assess_impact


def assess(anomalies):
    return assess_impact(build_network(), build_trains(), anomalies)


def statuses(report):
    return {tid: i.status for tid, i in report.impacts.items()}


def test_small_delay_shifts_times_only_no_conflict():
    # T1 +5: SEG-12[5,15] SEG-23[15,23] SEG-34[23,35]; T5 enters SEG-34 at 40 -> clean.
    report = assess([TrainDelayed("T1", 5)])
    assert statuses(report) == {
        "T1": "times_shifted", "T2": "unaffected", "T3": "unaffected",
        "T4": "unaffected", "T5": "unaffected",
    }
    assert report.impacts["T1"].new_arrivals == {"S1": 5, "S2": 15, "S3": 23, "S4": 35}
    assert "delayed 5 min" in report.impacts["T1"].reason
    assert "minute 35" in report.impacts["T1"].reason
    assert report.conflicts == ()
    assert report.no_impact is False


def test_larger_delay_creates_conflict_detected_not_resolved():
    # T1 +12: SEG-34[30,42] overlaps T5's SEG-34[40,52] during [40,42].
    report = assess([TrainDelayed("T1", 12)])
    assert report.impacts["T1"].new_arrivals == {"S1": 12, "S2": 22, "S3": 30, "S4": 42}
    assert report.conflicts == (Conflict("SEG-34", "T1", "T5", 40, 42),)


def test_cancelled_train():
    report = assess([TrainCancelled("T3")])
    assert statuses(report)["T3"] == "cancelled"
    assert report.impacts["T3"].new_arrivals is None
    assert all(s == "unaffected" for t, s in statuses(report).items() if t != "T3")
    assert report.no_impact is False


def test_cancellation_beats_delay():
    report = assess([TrainCancelled("T1"), TrainDelayed("T1", 5)])
    assert statuses(report)["T1"] == "cancelled"


def test_closure_flags_users_for_reroute_others_untouched():
    report = assess([TrackClosed("SEG-34")])
    assert statuses(report) == {
        "T1": "needs_reroute", "T2": "unaffected", "T3": "unaffected",
        "T4": "unaffected", "T5": "needs_reroute",
    }
    assert "SEG-34" in report.impacts["T1"].reason
    assert "alternative route" in report.impacts["T1"].reason
    assert report.conflicts == ()


def test_blocked_has_same_routing_effect_as_closed():
    assert statuses(assess([TrackBlocked("SEG-34")])) == statuses(
        assess([TrackClosed("SEG-34")])
    )


def test_unreachable_destination_reports_stranded():
    # S4 touches only SEG-34 and SEG-45; closing both cuts it off entirely.
    report = assess([TrackClosed("SEG-34"), TrackClosed("SEG-45")])
    assert statuses(report) == {
        "T1": "stranded", "T2": "unaffected", "T3": "unaffected",
        "T4": "stranded", "T5": "stranded",
    }
    assert "cannot complete" in report.impacts["T1"].reason
    assert report.impacts["T1"].new_arrivals is None


def test_reduced_speed_shifts_one_train_no_conflict():
    # SEG-26: 20 min -> ceil(20/0.8)=25; T3 arrives S6 at 12+25=37 (+5).
    report = assess([ReducedSpeed("SEG-26", 0.8)])
    assert statuses(report)["T3"] == "times_shifted"
    assert report.impacts["T3"].new_arrivals == {"S2": 12, "S6": 37}
    assert "+5 min" in report.impacts["T3"].reason
    assert report.conflicts == ()


def test_reduced_speed_creating_conflict_is_detected():
    # SEG-56: 9 -> 18 min. T2: SEG-56[20,38]; T4: SEG-56[30,48] -> overlap [30,38].
    report = assess([ReducedSpeed("SEG-56", 0.5)])
    assert report.impacts["T2"].new_arrivals == {"S1": 5, "S5": 20, "S6": 38}
    assert report.impacts["T4"].new_arrivals == {"S4": 23, "S5": 30, "S6": 48}
    assert report.conflicts == (Conflict("SEG-56", "T2", "T4", 30, 38),)


def test_combination_two_anomalies_at_once():
    # SEG-34 closed + T4 delayed 5: T1/T5 need reroute; T4 shifts to
    # SEG-45[28,35] SEG-56[35,44] (no clash with T2's SEG-56[20,29]).
    report = assess([TrackClosed("SEG-34"), TrainDelayed("T4", 5)])
    assert statuses(report) == {
        "T1": "needs_reroute", "T2": "unaffected", "T3": "unaffected",
        "T4": "times_shifted", "T5": "needs_reroute",
    }
    assert report.impacts["T4"].new_arrivals == {"S4": 28, "S5": 35, "S6": 44}
    assert report.conflicts == ()
