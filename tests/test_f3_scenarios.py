"""Gate: SPEC F3 scenarios — every expected value hand-computed.

Baseline (for reference):
  T1 S1->S4 [12,23,34] dep0  S4@30   T2 S1->S6 [15,56] dep5  S6@29
  T3 S2->S6 [26]      dep12 S6@32   T4 S4->S6 [45,56] dep23 S6@39
  T5 S4->S1 [34,23,12] dep40 S1@70
"""

from data.baseline import build_network, build_trains
from engine.anomalies import ReducedSpeed, TrackClosed, TrainDelayed
from engine.collision import find_conflicts
from engine.model import Train
from engine.recompute import recompute_schedule, try_schedule
from engine.scheduler import Occupancy


def recompute(anomalies):
    result = recompute_schedule(build_network(), build_trains(), anomalies)
    # SAFETY IS ABSOLUTE: every scenario's final table must be conflict-free.
    assert find_conflicts(list(result.occupancy_table)) == []
    return result


def seg_windows(result, seg_id):
    return sorted(
        (o.train_id, o.start, o.end)
        for o in result.occupancy_table
        if o.segment_id == seg_id
    )


# --- F3 normal + adversarial 2 (second-order conflict), one scenario ---

def test_closure_reroutes_t1_and_resolves_second_order_conflict_with_t2():
    """SEG-34 closed. Hand-computed expectations:
    T1 reroutes via S1-S5-S4 (22 min): SEG-15[0,15] SEG-45[15,22], S4@22 (-8).
    That reroute steals SEG-15 from T2 (baseline SEG-15[5,20]) -> second-order
    conflict, so T2 reroutes via S1-S2-S3-S6: S6@34 (+5).
    T3, T4 keep their paths (T4's SEG-45[23,30] starts after T1 clears at 22).
    T5 reroutes via S4-S5-S1: SEG-45[40,47] SEG-15[47,62], S1@62 (-8).
    Net total: -8 +5 +0 +0 -8 = -11 (two trains take the shorter detour)."""
    result = recompute([TrackClosed("SEG-34")])
    t1 = result.actions["T1"]
    assert t1.action == "reroute"
    assert t1.path == ("SEG-15", "SEG-45")
    assert t1.arrivals == {"S1": 0, "S5": 15, "S4": 22}
    assert t1.added_delay == -8
    assert "SEG-34" in t1.reason

    t2 = result.actions["T2"]
    assert t2.action == "reroute"
    assert t2.path == ("SEG-12", "SEG-23", "SEG-36")
    assert t2.arrivals == {"S1": 5, "S2": 15, "S3": 23, "S6": 34}
    assert t2.added_delay == 5
    assert "T1" in t2.reason  # the why: T1 now owns SEG-15 first

    assert result.actions["T3"].action == "unchanged"
    assert result.actions["T4"].action == "unchanged"

    t5 = result.actions["T5"]
    assert t5.action == "reroute"
    assert t5.path == ("SEG-45", "SEG-15")
    assert t5.arrivals == {"S4": 40, "S5": 47, "S1": 62}
    assert t5.added_delay == -8

    assert result.total_added_delay == -11
    # shared segments stay strictly sequenced
    assert seg_windows(result, "SEG-15") == [("T1", 0, 15), ("T5", 47, 62)]
    assert seg_windows(result, "SEG-45") == [
        ("T1", 15, 22), ("T4", 23, 30), ("T5", 40, 47),
    ]


# --- F3 adversarial 1: two trains, one remaining track -> sequenced ---

def test_single_remaining_exit_sequences_t1_then_t2():
    """SEG-15 closed: SEG-12 becomes S1's only exit. T1 (dep 0) takes it
    [0,10]; T2 must wait and follows [11,21] — never both on it.
    T2: reroute via S1-S2-S3-S6 departing 11, S6@40 (+11). Everyone else
    keeps their plan. Total +11."""
    result = recompute([TrackClosed("SEG-15")])
    assert result.actions["T1"].action == "unchanged"

    t2 = result.actions["T2"]
    assert t2.action == "reroute"
    assert t2.path == ("SEG-12", "SEG-23", "SEG-36")
    assert t2.depart_at == 11
    assert t2.arrivals == {"S1": 11, "S2": 21, "S3": 29, "S6": 40}
    assert t2.added_delay == 11

    # the sequencing itself: T2 enters SEG-12 only after T1 exits
    # (T5 also crosses SEG-12 much later, on its unchanged plan)
    assert seg_windows(result, "SEG-12") == [
        ("T1", 0, 10), ("T2", 11, 21), ("T5", 60, 70),
    ]

    for tid in ("T3", "T4", "T5"):
        assert result.actions[tid].action == "unchanged"
    assert result.total_added_delay == 11


# --- F3 adversarial 3: the delay-optimal move would collide -> slower safe ---

def test_safety_beats_delay_t2_rejects_faster_colliding_departure():
    """With SEG-15 closed, T2's delay-optimal move is its reroute at its
    planned minute 5 (S6@34) — but that puts it on SEG-12 [5,15] against
    T1 [0,10]: a collision. Engine must take the slower option (depart 11,
    S6@40) instead. Prove the rejected move really collides, and that the
    engine's chosen schedule does not contain it."""
    rejected = try_schedule(
        build_network(),
        Train("T2", "S1", "S6", ("SEG-12", "SEG-23", "SEG-36"), 5),
        ("SEG-12", "SEG-23", "SEG-36"),
        5,
        [Occupancy("T1", "SEG-12", 0, 10)],
    )
    assert rejected is None  # the faster move is a collision — unrepresentable

    result = recompute([TrackClosed("SEG-15")])
    assert result.actions["T2"].arrivals["S6"] == 40  # slower, safe
    assert result.actions["T2"].arrivals["S6"] > 34  # delay lost to safety


# --- pure hold: stay on path, wait for the line to clear ---

def test_hold_when_waiting_beats_every_reroute():
    """T2 delayed 2 min -> T2 SEG-56[22,31]. T4's plan hits it (and minute-31
    boundary at hold 1), so minimal hold is 2: depart 25, SEG-45[25,32]
    SEG-56[32,41], S6@41 (+2). Rerouting via S4-S3-S6 would cost +15. The
    engine holds. T5 keeps its plan (no over-reaction; its path is clear).
    Total: T2 +2, T4 +2 = +4."""
    result = recompute([TrainDelayed("T2", 2)])
    t2 = result.actions["T2"]
    assert t2.action == "depart_delayed"
    assert t2.arrivals == {"S1": 7, "S5": 22, "S6": 31}

    t4 = result.actions["T4"]
    assert t4.action == "hold"
    assert t4.path == ("SEG-45", "SEG-56")  # same path — not rerouted
    assert t4.depart_at == 25
    assert t4.arrivals == {"S4": 25, "S5": 32, "S6": 41}
    assert t4.added_delay == 2
    assert "T2" in t4.reason and "until minute 25" in t4.reason

    assert result.actions["T5"].action == "unchanged"  # 70, not "improved"
    assert seg_windows(result, "SEG-56") == [("T2", 22, 31), ("T4", 32, 41)]
    assert result.total_added_delay == 4


# --- delayed train forces a follower to choose reroute over hold ---

def test_delayed_t1_makes_t5_reroute_instead_of_waiting():
    """T1 +12: keeps its path, S4@42, now on SEG-34 [30,42]. T5 (dep 40,
    needs SEG-34 at 40) would have to hold 3 min and arrive S1@73; the open
    detour S4-S5-S1 arrives S1@62 — engine picks the reroute.
    Total: +12 (T1) - 8 (T5) = +4."""
    result = recompute([TrainDelayed("T1", 12)])
    t1 = result.actions["T1"]
    assert t1.action == "depart_delayed"
    assert t1.arrivals == {"S1": 12, "S2": 22, "S3": 30, "S4": 42}

    t5 = result.actions["T5"]
    assert t5.action == "reroute"
    assert t5.path == ("SEG-45", "SEG-15")
    assert t5.arrivals == {"S4": 40, "S5": 47, "S1": 62}
    assert "T1" in t5.reason  # why it moved

    for tid in ("T2", "T3", "T4"):
        assert result.actions[tid].action == "unchanged"
    assert result.total_added_delay == 4


# --- reduced speed cascade: slowdown, reroute, second-order reroute ---

def test_reduced_speed_cascade_all_three_effects():
    """SEG-56 at half speed (9 -> 18 min). Hand-computed:
    T2 stays: SEG-15[5,20] SEG-56[20,38], S6@38 (+9) — slowed, not held.
    T4: plan would need a 9-min hold (S6@57); reroute S4-S3-S6 departing 31
    (waits for T1 to clear SEG-34 at 30) arrives S6@54 (+15) — better.
    T5: T4 now sits on SEG-34 [31,43] over T5's planned entry at 40 ->
    second-order; detour S4-S5-S1 is clear (T4 left SEG-45): S1@62 (-8).
    Total: +9 +15 -8 = +16."""
    result = recompute([ReducedSpeed("SEG-56", 0.5)])
    t2 = result.actions["T2"]
    assert t2.action == "unchanged"
    assert t2.arrivals == {"S1": 5, "S5": 20, "S6": 38}
    assert t2.added_delay == 9

    t4 = result.actions["T4"]
    assert t4.action == "reroute"
    assert t4.path == ("SEG-34", "SEG-36")
    assert t4.depart_at == 31
    assert t4.arrivals == {"S4": 31, "S3": 43, "S6": 54}
    assert t4.added_delay == 15

    t5 = result.actions["T5"]
    assert t5.action == "reroute"
    assert t5.path == ("SEG-45", "SEG-15")
    assert t5.arrivals == {"S4": 40, "S5": 47, "S1": 62}

    assert result.actions["T1"].action == "unchanged"
    assert result.actions["T3"].action == "unchanged"
    assert result.total_added_delay == 16
    assert seg_windows(result, "SEG-34") == [("T1", 18, 30), ("T4", 31, 43)]
