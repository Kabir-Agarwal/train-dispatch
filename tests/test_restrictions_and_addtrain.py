"""Gates for the two new engine features:

  Feature 2 — per-train path restriction: one train is barred from a segment
  while other trains still use it; it reroutes if an allowed path exists, or
  strands if none does. The collision-free rule stays absolute.

  Feature 3 — add a train live: a new train is scheduled collision-free against
  existing traffic (holding/rerouting as needed), or reported unplaceable.

All hand-verified on the 6-city baseline (well-known schedule) plus the real
corridor for the diamond reroute.
"""

from data.baseline import build_network, build_trains
from data.real_corridor import build_network as real_network
from data.real_corridor import build_trains as real_trains
from engine.anomalies import (
    TrainRestricted,
    apply_anomalies,
    closed_segment_ids,
    restricted_segments,
)
from engine.collision import find_conflicts
from engine.model import Train
from engine.recompute import recompute_schedule
from engine.routes import all_open_paths


# --- Feature 2: per-train path restriction ------------------------------

def test_restricted_train_avoids_segment_while_others_use_it():
    net, trains = build_network(), build_trains()
    res = recompute_schedule(net, trains, [TrainRestricted("T1", "SEG-34")])
    t1 = res.actions["T1"]
    assert t1.action == "reroute"
    assert "SEG-34" not in (t1.path or ())          # the restricted train avoids it
    assert "barred" in t1.reason                     # engine reason explains why
    # T5 also routes over SEG-34 and is NOT restricted -> it still uses it
    assert "SEG-34" in (res.actions["T5"].path or ())
    assert find_conflicts(list(res.occupancy_table)) == []   # safety absolute


def test_restriction_is_per_train_not_a_global_closure():
    net = build_network()
    a = TrainRestricted("T1", "SEG-34")
    # apply_anomalies must NOT touch the segment's global status...
    assert apply_anomalies(net, [a]).segment("SEG-34").status == "open"
    # ...and the closed set stays empty (it is not a closure)
    assert closed_segment_ids([a]) == set()
    assert restricted_segments([a]) == {"T1": {"SEG-34"}}


def test_restricted_train_reroutes_via_an_allowed_path_when_one_exists():
    net, trains = build_network(), build_trains()
    res = recompute_schedule(net, trains, [TrainRestricted("T1", "SEG-34")])
    t1 = res.actions["T1"]
    # it actually completes to its destination on the allowed reroute
    assert t1.arrivals is not None and t1.arrivals["S4"] is not None
    # the chosen path is a real open path that omits the barred segment
    assert "SEG-34" not in t1.path
    assert t1.path in all_open_paths(net, "S1", "S4", frozenset({"SEG-34"}))


def test_restricted_train_strands_when_no_allowed_path_remains():
    net, trains = build_network(), build_trains()
    # S4's only segments are SEG-34 (S3-S4) and SEG-45 (S4-S5); bar both for T1
    res = recompute_schedule(
        net, trains,
        [TrainRestricted("T1", "SEG-34"), TrainRestricted("T1", "SEG-45")],
    )
    assert res.actions["T1"].action == "stranded"
    assert res.actions["T1"].arrivals is None
    # everyone else is unaffected and the table is still safe
    assert find_conflicts(list(res.occupancy_table)) == []


def test_restriction_reroutes_onto_the_real_diamond_loop():
    net, trains = real_network(), real_trains()
    # T101 NDLS->NGP normally runs the trunk through BHS-BPL; bar it from BHS-BPL
    res = recompute_schedule(net, trains, [TrainRestricted("T101", "BHS-BPL")])
    t101 = res.actions["T101"]
    assert t101.action == "reroute"
    assert "BHS-BPL" not in t101.path
    # T102 (also trunk via BHS-BPL, unrestricted) keeps using it
    assert "BHS-BPL" in (res.actions["T102"].path or ())
    assert find_conflicts(list(res.occupancy_table)) == []


# --- Feature 3: add a train live ----------------------------------------

def test_added_train_that_fits_is_scheduled_conflict_free():
    net, trains = build_network(), build_trains()
    # SEG-36 (S3->S6) is used by NO baseline train; a late departure fits cleanly
    path = all_open_paths(net, "S3", "S6")[0]
    new = Train("T9", "S3", "S6", path, 40)
    res = recompute_schedule(net, trains + [new], [])
    t9 = res.actions["T9"]
    assert t9.action == "unchanged"
    assert t9.arrivals["S6"] == 51                      # 40 + 11 (SEG-36)
    assert find_conflicts(list(res.occupancy_table)) == []


def test_added_train_that_conflicts_is_held_or_rerouted():
    net, trains = build_network(), build_trains()
    # T1 holds SEG-12 [0,10]; a new S1->S2 train departing at 0 contends for it
    path = all_open_paths(net, "S1", "S2")[0]
    new = Train("T9", "S1", "S2", path, 0)
    res = recompute_schedule(net, trains + [new], [])
    t9 = res.actions["T9"]
    assert t9.action in ("hold", "reroute", "depart_delayed")
    assert t9.arrivals is not None                      # still placed, just adapted
    assert find_conflicts(list(res.occupancy_table)) == []
    # existing higher-priority train T1 keeps its original plan
    assert res.actions["T1"].action == "unchanged"


def test_added_train_with_no_route_is_reported_not_forced():
    net, trains = build_network(), build_trains()
    # If S6 is unreachable (all its segments barred for this train), it cannot
    # be placed: all_open_paths returns nothing, so it strands rather than being
    # forced onto a fabricated path.
    res = recompute_schedule(
        net, trains + [Train("T9", "S1", "S6", all_open_paths(net, "S1", "S6")[0], 0)],
        [TrainRestricted("T9", "SEG-56"),
         TrainRestricted("T9", "SEG-26"),
         TrainRestricted("T9", "SEG-36")],
    )
    assert res.actions["T9"].action == "stranded"
    assert res.actions["T9"].arrivals is None
    assert find_conflicts(list(res.occupancy_table)) == []


def test_empty_anomaly_recompute_reproduces_baseline():
    # the add-train code path calls recompute with NO anomalies; it must just
    # reproduce the conflict-free baseline (every train unchanged, zero delay).
    net, trains = build_network(), build_trains()
    res = recompute_schedule(net, trains, [])
    assert all(a.action == "unchanged" for a in res.actions.values())
    assert res.total_added_delay == 0
    assert find_conflicts(list(res.occupancy_table)) == []
