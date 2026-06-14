"""Phase A gate — single-track / opposing-move safety.

Investigation (PROGRESS.md) found NO engine gap: every link is a single shared
segment (no double-track), occupancy is keyed by segment_id regardless of
direction, so a head-on is detected, and the deconfliction sequences opposing
trains (one waits at a station). These gates LOCK that behavior so Phases B-F
can't regress it. Value-asserting: they pin the actual conflict and the resolved
schedule, not just "no exception".
"""

import data.baseline as baseline
import data.west_bengal as wb
from engine.collision import Conflict, find_conflicts
from engine.model import Train
from engine.recompute import recompute_schedule
from engine.scheduler import compute_train_schedule


def _pairs_with_multiple_segments(net):
    seen = {}
    for sid in net.segment_ids():
        key = frozenset(net.segment(sid).endpoints)
        seen.setdefault(key, []).append(sid)
    return {tuple(k): v for k, v in seen.items() if len(v) > 1}


def test_network_is_single_track_no_double_track_links():
    """Every physical link is ONE segment shared by both directions: no station
    pair has two parallel segments (which would be de-facto double track)."""
    for mod in (baseline, wb):
        net = mod.build_network()
        assert _pairs_with_multiple_segments(net) == {}


def test_reverse_direction_uses_the_same_segment_id():
    """A train going B->A occupies the IDENTICAL segment id as one going A->B —
    the root reason a head-on is even detectable."""
    # WB adjacency maps both orderings to one id
    assert wb._route("HWH", "BLY") == wb._route("BLY", "HWH") == ("HWH-BLY",)
    # baseline ships this too: T1 (S1->S4) and T5 (S4->S1) share SEG-12/23/34
    trains = {t.id: t for t in baseline.build_trains()}
    assert set(trains["T1"].path) & set(trains["T5"].path) == {
        "SEG-12", "SEG-23", "SEG-34"
    }


def test_headon_opposite_directions_same_segment_is_detected():
    """DETECTION: two trains driven onto one segment in opposite directions at
    overlapping times produce a real conflict (direction is irrelevant)."""
    net = baseline.build_network()
    down = Train("D", "S1", "S2", ("SEG-12",), 0)   # S1 -> S2
    up = Train("U", "S2", "S1", ("SEG-12",), 0)     # S2 -> S1 (reverse, same id)
    occ = []
    for t in (down, up):
        _, o = compute_train_schedule(net, t)
        occ += o
    assert find_conflicts(occ) == [
        Conflict(segment_id="SEG-12", train_a="D", train_b="U", start=0, end=10)
    ]


def test_recompute_sequences_opposing_trains_one_waits_at_station():
    """RESOLUTION: the engine holds the opposing train at its station until the
    single track clears; the resulting table is collision-free."""
    net = baseline.build_network()
    down = Train("D", "S1", "S2", ("SEG-12",), 0)
    up = Train("U", "S2", "S1", ("SEG-12",), 0)
    res = recompute_schedule(net, [down, up], [])

    # one proceeds, the other is held at its origin station past the clearance
    assert res.actions["D"].action == "unchanged"
    assert res.actions["D"].arrivals == {"S1": 0, "S2": 10}
    assert res.actions["U"].action == "hold"
    assert res.actions["U"].depart_at == 11               # after D clears at 10
    assert res.actions["U"].arrivals == {"S2": 11, "S1": 21}
    assert "held at S2" in res.actions["U"].reason

    # the single track is never shared at the same minute
    seg12 = sorted((o.start, o.end) for o in res.occupancy_table
                   if o.segment_id == "SEG-12")
    assert seg12 == [(0, 10), (11, 21)]
    assert find_conflicts(list(res.occupancy_table)) == []


def test_wb_real_single_track_headon_is_resolved_collision_free():
    """The same guarantee on a real WB single-track segment (Howrah-Bally):
    two opposing services are sequenced, never on the link together."""
    net = wb.build_network()
    down = Train("WD", "HWH", "BLY", wb._route("HWH", "BLY"), 0)
    up = Train("WU", "BLY", "HWH", wb._route("BLY", "HWH"), 0)
    res = recompute_schedule(net, [down, up], [])

    assert find_conflicts(list(res.occupancy_table)) == []     # collision-free
    held = [a for a in res.actions.values() if a.depart_at > 0]
    assert len(held) == 1                                       # exactly one waits
    # and they never overlap on the shared segment
    occ = sorted((o.start, o.end) for o in res.occupancy_table
                 if o.segment_id == "HWH-BLY")
    assert occ[0][1] <= occ[1][0] or occ[1][1] <= occ[0][0]
