"""Gate: scenario unit — the SPEC F2 adversarial cases on the real baseline.

SEG-36 (S3-S6, 11 min) is in the network but used by NO baseline train.
"""

from data.baseline import build_network, build_trains
from engine.anomalies import ReducedSpeed, TrackClosed, TrainDelayed
from engine.impact import assess_impact
from engine.scheduler import build_schedule


def assess(anomalies):
    return assess_impact(build_network(), build_trains(), anomalies)


def test_adversarial_1_no_impact_anomaly_changes_nothing():
    # SPEC F2-A1: anomaly on a segment no train uses -> "no impact",
    # schedule unchanged (never invent changes).
    report = assess([TrackClosed("SEG-36")])
    assert report.no_impact is True
    assert all(i.status == "unaffected" for i in report.impacts.values())
    assert report.conflicts == ()
    # arrivals identical to the untouched baseline, train by train
    baseline_schedule, _ = build_schedule(build_network(), build_trains())
    for tid, impact in report.impacts.items():
        assert impact.new_arrivals == baseline_schedule[tid]


def test_adversarial_1b_reduced_speed_on_unused_segment_also_no_impact():
    report = assess([ReducedSpeed("SEG-36", 0.5)])
    assert report.no_impact is True


def test_adversarial_2_harmless_small_delay_shifts_only_that_train():
    # SPEC F2-A2: small delay causing no conflict -> NO reroute/hold;
    # only that train's times shift (don't over-react).
    report = assess([TrainDelayed("T1", 5)])
    assert report.impacts["T1"].status == "times_shifted"  # not reroute/hold
    assert report.conflicts == ()
    for tid in ("T2", "T3", "T4", "T5"):
        assert report.impacts[tid].status == "unaffected"
    assert report.impacts["T1"].new_arrivals == {"S1": 5, "S2": 15, "S3": 23, "S4": 35}


def test_adversarial_3_unreachable_destination_is_stranded_and_terminates():
    # SPEC F2-A3: destination unreachable -> "stranded", never loop or
    # fabricate a route. (Completing at all proves no infinite loop.)
    report = assess([TrackClosed("SEG-34"), TrackClosed("SEG-45")])
    for tid in ("T1", "T4", "T5"):
        assert report.impacts[tid].status == "stranded"
        assert report.impacts[tid].new_arrivals is None  # nothing fabricated
    for tid in ("T2", "T3"):
        assert report.impacts[tid].status == "unaffected"


def test_normal_case_closure_identifies_affected_trains():
    # SPEC F2 normal: track_closed(S3-S4) -> segment closed, affected trains
    # identified (T1 and T5 use SEG-34; alternatives exist via S5/S6).
    report = assess([TrackClosed("SEG-34")])
    assert report.impacts["T1"].status == "needs_reroute"
    assert report.impacts["T5"].status == "needs_reroute"
    assert report.no_impact is False
