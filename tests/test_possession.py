"""Phase J gate — possession / maintenance-window scheduling.

Hand-verified case (6-city baseline, SEG-56, 12-min possession): SEG-56 is used by
T2 [20,29] and T4 [30,39]; closing it costs T2 +11 and T4 +15. A naive window at
the segment's first use (min 20) spans [20,32] and displaces BOTH → +26 min. The
scan instead finds an empty window [0,12] that displaces nobody → +0. The smart
window beats the naive one by 26 min.
"""

import pytest

import data.baseline as baseline
import data.west_bengal as wb
from app.state import AppState
from engine.errors import UnknownSegmentError
from engine.possession import POSSESSION_DURATION_MIN, best_possession


def _b():
    return baseline.build_network(), baseline.build_trains()


def test_hand_verified_seg56_smart_window_beats_naive():
    net, trains = _b()
    r = best_possession(net, trains, "SEG-56", 12)
    assert r["best_start"] == 0 and r["best_end"] == 12
    assert r["best_delay"] == 0 and r["best_stranded"] == 0
    assert r["displaced_best"] == []
    assert r["naive_start"] == 20 and r["naive_end"] == 32   # segment's first use
    assert r["naive_delay"] == 26                            # T2 +11, T4 +15
    assert r["displaced_naive"] == ["T2", "T4"]
    assert r["saved_delay"] == 26


def test_smart_window_is_never_worse_than_naive():
    net, trains = _b()
    for seg in ("SEG-12", "SEG-56", "SEG-23"):
        r = best_possession(net, trains, seg, 10)
        assert r["saved_delay"] >= 0 and r["saved_stranded"] >= 0


def test_unused_segment_has_zero_disruption_anywhere():
    """SEG-36 is used by no baseline train, so every window is free."""
    net, trains = _b()
    r = best_possession(net, trains, "SEG-36", 12)
    assert r["best_delay"] == 0 and r["naive_delay"] == 0 and r["saved_delay"] == 0
    assert r["displaced_best"] == [] and r["displaced_naive"] == []


def test_smart_window_avoids_stranding_on_wb_flagged_segment():
    """WB top wear-flagged NFK-MLDT: a naive window strands 3 trains; the scan
    finds an early window that strands none."""
    net, trains = wb.build_network(), wb.build_trains()
    r = best_possession(net, trains, "NFK-MLDT", 60)
    assert r["best_stranded"] == 0
    assert r["naive_stranded"] == 3
    assert r["saved_stranded"] == 3


def test_invalid_duration_and_unknown_segment():
    net, trains = _b()
    assert best_possession(net, trains, "SEG-56", 0) == {"applicable": False}
    with pytest.raises(UnknownSegmentError):
        best_possession(net, trains, "SEG-zzz", 10)


def test_method_is_named_and_reuses_reroute_engine():
    net, trains = _b()
    r = best_possession(net, trains, "SEG-56", 12)
    assert "reuse the reroute engine" in r["method"]


def test_snapshot_schedules_possession_on_the_flagged_segment():
    """Connects to wear flagging: the app schedules the possession on the highest-
    load flagged segment and exposes the smart-vs-naive comparison."""
    s = AppState(dataset="wb")
    snap = s.snapshot()
    pos = snap["possession"]
    assert pos["applicable"] is True
    flagged_ids = [f["id"] for f in snap["maintenance"]["flagged"]]
    assert pos["segment"] == flagged_ids[0]            # the top wear-flagged track
    assert pos["duration"] == POSSESSION_DURATION_MIN
    # the chosen window is at least as good as the naive one
    assert pos["saved_stranded"] >= 0 and pos["saved_delay"] >= 0
