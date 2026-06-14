"""Phase C gate — train priority under conflict.

Value-asserting: proves a higher-priority train is FAVOURED in a contended slot
(claims the line; the lower-priority train waits), that priority overrides both
the train-id tie-break and an earlier departure, that equal priority falls back
to the old (departure, id) order (so the recompute golden is unaffected), and
that collision-free remains absolute.
"""

import data.baseline as baseline
import data.real_corridor as real
import data.west_bengal as wb
from engine.collision import find_conflicts
from engine.model import (
    PRIORITY_EXPRESS,
    PRIORITY_FREIGHT,
    PRIORITY_PASSENGER,
    Train,
)
from engine.recompute import recompute_schedule


def _net():
    return baseline.build_network()


def test_higher_priority_train_claims_contended_slot():
    """Two trains want SEG-12 at the same minute, opposite directions. The
    express proceeds; the freight waits — even though the freight's id sorts
    FIRST (so without priority the freight would have won the slot)."""
    net = _net()
    express = Train("ZEXP", "S1", "S2", ("SEG-12",), 0, priority=PRIORITY_EXPRESS)
    freight = Train("AFRT", "S2", "S1", ("SEG-12",), 0, priority=PRIORITY_FREIGHT)
    res = recompute_schedule(net, [express, freight], [])

    assert res.actions["ZEXP"].action == "unchanged"     # express keeps its slot
    assert res.actions["ZEXP"].depart_at == 0
    assert res.actions["AFRT"].action == "hold"          # freight waits
    assert res.actions["AFRT"].depart_at >= 11
    assert find_conflicts(list(res.occupancy_table)) == []


def test_equal_priority_falls_back_to_id_order_unchanged():
    """Control: with EQUAL priority the id tie-break decides (AFRT < ZEXP), the
    opposite outcome — so priority, not id, drove the test above. This is also
    the old behaviour, i.e. the golden is unaffected."""
    net = _net()
    a = Train("ZEXP", "S1", "S2", ("SEG-12",), 0, priority=PRIORITY_PASSENGER)
    b = Train("AFRT", "S2", "S1", ("SEG-12",), 0, priority=PRIORITY_PASSENGER)
    res = recompute_schedule(net, [a, b], [])
    assert res.actions["AFRT"].action == "unchanged"     # id-first wins now
    assert res.actions["ZEXP"].action == "hold"
    assert find_conflicts(list(res.occupancy_table)) == []


def test_priority_overrides_an_earlier_departure():
    """A higher-priority train that departs LATER still claims the slot; the
    earlier low-priority train is held to clear the line for it."""
    net = _net()
    local = Train("LOCAL", "S1", "S2", ("SEG-12",), 0, priority=PRIORITY_FREIGHT)
    express = Train("EXPR", "S1", "S2", ("SEG-12",), 2, priority=PRIORITY_EXPRESS)
    res = recompute_schedule(net, [local, express], [])

    assert res.actions["EXPR"].action == "unchanged"     # later, but takes the slot
    assert res.actions["EXPR"].depart_at == 2
    assert res.actions["LOCAL"].action == "hold"         # earlier, but yields
    assert res.actions["LOCAL"].depart_at > 2
    assert find_conflicts(list(res.occupancy_table)) == []


def test_collision_free_is_absolute_under_priority():
    """Three trains contending on SEG-12 with mixed priorities: still zero
    conflicts, and exactly one runs unheld."""
    net = _net()
    trains = [
        Train("T_A", "S1", "S2", ("SEG-12",), 0, priority=PRIORITY_FREIGHT),
        Train("T_B", "S2", "S1", ("SEG-12",), 0, priority=PRIORITY_EXPRESS),
        Train("T_C", "S1", "S2", ("SEG-12",), 0, priority=PRIORITY_PASSENGER),
    ]
    res = recompute_schedule(net, trains, [])
    assert find_conflicts(list(res.occupancy_table)) == []
    # the express claims minute 0; the other two are sequenced after it
    assert res.actions["T_B"].depart_at == 0
    assert res.actions["T_A"].depart_at > 0
    assert res.actions["T_C"].depart_at > 0


def test_default_priority_is_passenger_and_no_dataset_train_is_reprioritised():
    """Every shipped train uses the default priority, so adding the field does
    not change any existing schedule (the recompute golden stays byte-identical;
    that gate runs separately)."""
    assert Train("x", "S1", "S2", ("SEG-12",), 0).priority == PRIORITY_PASSENGER
    for mod in (baseline, real, wb):
        for t in mod.build_trains():
            assert t.priority == PRIORITY_PASSENGER
