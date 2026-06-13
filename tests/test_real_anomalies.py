"""Gate: Phase B — every anomaly type on the REAL two-corridor network.
All minutes hand-computed from the published km (trunk: 12616; loop: 11271).

Baseline anchors: T101 NDLS->NGP@1090; T103 BPL->NGP@419; T107 ET->BINA@698
(loop, dep 100); T108 JBP->ET@946 (dep 700); loop BINA->ET = 598 min,
trunk BINA->ET = 230 min.
"""

import time

from app.state import AppState
from data.real_corridor import build_network, build_trains
from engine.anomalies import (
    ReducedSpeed,
    TrackBlocked,
    TrackClosed,
    TrainCancelled,
    TrainDelayed,
)
from engine.collision import find_conflicts
from engine.recompute import recompute_schedule


def recompute(anomalies):
    result = recompute_schedule(build_network(), build_trains(), anomalies)
    assert find_conflicts(list(result.occupancy_table)) == []  # safety absolute
    return result


def test_closure_now_reroutes_via_the_real_loop():
    """track_closed(BPL-RKMP): the Phase A outcome was 'stranded'; with the
    real loop it must REROUTE. Hand-computed:
    T101 NDLS->NGP: trunk to BINA (563) + loop (598) + ET->NGP (297) -> 1458.
    T103 BPL->NGP: north to BINA (138) + loop (598) + 297 -> dep 30, 1063.
    T107 ET->BINA (loop is its only remaining path) cannot cross the
    single-track loop while T103 [168..766] and then the rerouted T101
    [563..1161] occupy it from the other side (the JBP crossing squeeze
    makes every intermediate hold collide with one of them); the first
    clear slot is dep 1162 — after T101 exits PPI-ET at 1161 — arriving
    BINA @ 1760 (+1062). Costly but collision-free; origin-holds only."""
    result = recompute([TrackClosed("BPL-RKMP")])
    t101 = result.actions["T101"]
    assert t101.action == "reroute"
    assert t101.arrivals["NGP"] == 1458
    assert t101.added_delay == 368
    assert "BINA-SGO" in t101.path and "PPI-ET" in t101.path

    t103 = result.actions["T103"]
    assert t103.action == "reroute"
    assert t103.arrivals["NGP"] == 1063
    assert t103.added_delay == 644

    t107 = result.actions["T107"]
    assert t107.action == "hold"
    assert t107.depart_at == 1162  # first minute after T101 clears PPI-ET
    assert t107.arrivals["BINA"] == 1760
    assert t107.added_delay == 1062
    assert "T103" in t107.reason  # the first blocker at its planned time

    for tid in ("T102", "T104", "T105", "T106", "T108"):
        assert result.actions[tid].action == "unchanged", tid
    assert result.total_added_delay == 368 + 644 + 1062  # 2074


def test_blocked_has_same_routing_effect_as_closed():
    a = recompute([TrackClosed("BPL-RKMP")])
    b = recompute([TrackBlocked("BPL-RKMP")])
    assert {t: x.action for t, x in a.actions.items()} == \
        {t: x.action for t, x in b.actions.items()}


def test_reduced_speed_shifts_users_and_resolves_knock_on():
    """NRKR-NGP 86 -> 172. T101 and T104 shift +86 in place. KNOCK-ON: the
    +86 shift of T104's tail moves its AMLA-PAR window to [195,258], into
    slowed T103's planned [252,315] -> T103 (lower priority, dep 30 > 5)
    must hold 53 min (dep 83) and arrives NGP @ 558 (+139). The engine
    catches the second-order conflict my first hand-pass missed."""
    result = recompute([ReducedSpeed("NRKR-NGP", 0.5)])
    assert result.actions["T101"].action == "unchanged"
    assert result.actions["T101"].arrivals["NGP"] == 1176
    assert result.actions["T101"].added_delay == 86
    assert result.actions["T104"].action == "unchanged"
    assert result.actions["T104"].arrivals["BZU"] == 281
    assert result.actions["T104"].added_delay == 86
    t103 = result.actions["T103"]
    assert t103.action == "hold"
    assert t103.depart_at == 83
    assert t103.arrivals["NGP"] == 558
    assert t103.added_delay == 139
    assert "T104" in t103.reason
    assert result.total_added_delay == 86 + 86 + 139  # 311


def test_harmless_delay_shifts_only_that_train():
    result = recompute([TrainDelayed("T108", 10)])
    assert result.actions["T108"].action == "depart_delayed"
    assert result.actions["T108"].arrivals["ET"] == 956
    for tid in ("T101", "T102", "T103", "T104", "T105", "T106", "T107"):
        assert result.actions[tid].action == "unchanged", tid
    assert result.total_added_delay == 10


def test_cancellation_excludes_train_others_untouched():
    result = recompute([TrainCancelled("T101")])
    assert result.actions["T101"].action == "cancelled"
    assert not any(o.train_id == "T101" for o in result.occupancy_table)
    assert result.total_added_delay == 0


def test_double_closure_strands_honestly():
    # BPL-RKMP + PPI-ET cuts BOTH routes between the BINA side and ET.
    result = recompute([TrackClosed("BPL-RKMP"), TrackClosed("PPI-ET")])
    for tid in ("T101", "T103", "T107", "T108"):
        assert result.actions[tid].action == "stranded", tid
    for tid in ("T102", "T104", "T105", "T106"):
        assert result.actions[tid].action == "unchanged", tid


def test_ghost_preview_equals_apply_on_real_data():
    payload = [{"type": "track_closed", "segment": "BPL-RKMP"}]
    s = AppState(dataset="real")
    predicted = s.preview(payload)
    assert s.snapshot()["anomalies"] == []  # nothing applied
    s.inject(payload)
    applied = s.snapshot()
    assert predicted["trains"] == applied["trains"]
    assert predicted["total_added_delay"] == applied["total_added_delay"]
    deltas = {d["id"]: d for d in predicted["deltas"]}
    assert deltas["T101"]["new_action"] == "reroute"
    assert (deltas["T101"]["old_arrival"], deltas["T101"]["new_arrival"]) == (1090, 1458)
    assert predicted["segment_changes"] == {"BPL-RKMP": "closed"}
    # passenger view consistent with the rerouted board
    p = s.passenger("T101")
    assert p["eta"] == 1458 and p["violations"] == []


def test_recompute_performance_on_real_network():
    net, trains = build_network(), build_trains()
    t0 = time.perf_counter()
    result = recompute_schedule(net, trains, [TrackClosed("BPL-RKMP")])
    elapsed = time.perf_counter() - t0
    assert find_conflicts(list(result.occupancy_table)) == []
    assert elapsed < 2.0, elapsed
    print(f"\nperf: closure recompute on 27-station/8-train network = "
          f"{elapsed*1000:.0f} ms")
