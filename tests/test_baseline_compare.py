"""Phase B gate — naive hold-all vs reroute-engine comparison.

Value-asserting: proves the reroute engine delivers a real, meaningful delay
reduction vs a naive hold-all dispatcher on the default WB closure, that the
advantage is robust across assumed clearance times (reroute is NEVER worse once
both are kept collision-free), and that the UI snapshot surfaces it.
"""

import data.west_bengal as wb
from app.state import AppState
from engine.anomalies import TrackClosed
from engine.baseline_compare import NAIVE_CLEARANCE_MIN, compare_dispatch


def _wb():
    return wb.build_network(), wb.build_trains(), dict(wb.LOAD_WEIGHTS)


def test_default_closure_comparison_applies_and_affected_set_is_correct():
    net, trains, w = _wb()
    cmp = compare_dispatch(net, trains, [TrackClosed("MYM-BWN")], load_weights=w)
    assert cmp["applicable"] is True
    # exactly the trains whose BOOKED path uses the closed Memari-Barddhaman main
    assert cmp["affected_ids"] == ["T1", "T3"]
    assert cmp["clearance_min"] == NAIVE_CLEARANCE_MIN


def test_reroute_beats_naive_by_a_meaningful_margin():
    net, trains, w = _wb()
    cmp = compare_dispatch(net, trains, [TrackClosed("MYM-BWN")], load_weights=w)
    assert cmp["smart_delay"] < cmp["naive_delay"]       # reroute is better
    assert cmp["reduction_pct"] >= 25                    # and by a real margin
    # both are positive passenger-delay-minutes (something is actually delayed)
    assert cmp["naive_delay"] > 0 and cmp["smart_delay"] > 0
    # sanity band around the ~46% headline (loose so later phases can shift it)
    assert 40 <= cmp["reduction_pct"] <= 60


def test_reroute_never_worse_across_assumed_clearance_times():
    """The advantage is robust: for any plausible blockage length, holding-all is
    at least as costly as rerouting (both kept collision-free)."""
    net, trains, w = _wb()
    for R in (60, 120, 180, 240, 300):
        cmp = compare_dispatch(net, trains, [TrackClosed("MYM-BWN")],
                               clearance_min=R, load_weights=w)
        assert cmp["naive_delay"] >= cmp["smart_delay"], f"naive<smart at R={R}"
        assert cmp["reduction_pct"] >= 0


def test_longer_blockage_gives_at_least_as_much_reduction_at_the_extremes():
    """A very long blockage favours rerouting at least as much as a short one
    (compares the endpoints, which are monotonic even if the middle wobbles)."""
    net, trains, w = _wb()
    short = compare_dispatch(net, trains, [TrackClosed("MYM-BWN")],
                             clearance_min=60, load_weights=w)["reduction_pct"]
    long = compare_dispatch(net, trains, [TrackClosed("MYM-BWN")],
                            clearance_min=600, load_weights=w)["reduction_pct"]
    assert long > short


def test_not_applicable_without_a_closure():
    net, trains, w = _wb()
    # no anomalies at all
    assert compare_dispatch(net, trains, [], load_weights=w) == {"applicable": False}
    # a delay-only anomaly closes no track -> no comparison
    from engine.anomalies import TrainDelayed
    assert compare_dispatch(net, trains, [TrainDelayed("T4", 10)],
                            load_weights=w) == {"applicable": False}


def test_closure_that_blocks_no_train_is_not_applicable():
    """Closing a segment no train's booked path uses -> nobody held -> N/A.
    APDJ-NCB is an unused spur now that T2 terminates at Malda."""
    net, trains, w = _wb()
    used = {sid for t in trains for sid in t.path}
    assert "APDJ-NCB" not in used                     # precondition for this test
    cmp = compare_dispatch(net, trains, [TrackClosed("APDJ-NCB")], load_weights=w)
    assert cmp == {"applicable": False}


def test_snapshot_surfaces_the_comparison_for_the_default_wb_money_shot():
    s = AppState(dataset="wb")                  # default closes MYM-BWN
    snap = s.snapshot()
    dc = snap["dispatch_comparison"]
    assert dc["applicable"] is True
    assert dc["affected_ids"] == ["T1", "T3"]
    assert dc["reduction_pct"] >= 25
    # matches the pure engine computation (no drift between snapshot and engine)
    eng = compare_dispatch(s.network, s.trains, s.anomalies,
                           load_weights=s.load_weights)
    assert dc["reduction_pct"] == eng["reduction_pct"]


def test_reset_clears_the_comparison():
    s = AppState(dataset="wb")
    assert s.snapshot()["dispatch_comparison"]["applicable"] is True
    s.reset()
    assert s.snapshot()["dispatch_comparison"] == {"applicable": False}
