"""Phase L gate — freight handling (yard classification + network connection).

Part 1 hand-verified yard instance: destinations A (cap 3) and B (cap 2), inbound
[a1, a2(haz), a3(haz), b1, b2, b3]. a1,a2 go to track A; a3 would put two hazmat
wagons adjacent on A → reworked; b1,b2 fill B; b3 overflows B (cap 2) → reworked.
Result: 2 reshuffles, both tracks valid (no hazmat adjacency, within capacity).

Part 2 connection: a freight train (PRIORITY_FREIGHT, Phase C) yields to an
express on a shared single-track segment — reusing the existing recompute, not a
new mechanism.
"""

import data.baseline as baseline
from app.state import AppState
from engine.collision import find_conflicts
from engine.freight import (
    Wagon,
    classify,
    is_valid_classification,
    synthetic_yard,
)
from engine.model import (
    PRIORITY_EXPRESS,
    PRIORITY_FREIGHT,
    PRIORITY_PASSENGER,
    Train,
)
from engine.recompute import recompute_schedule

_CAPS = {"A": 3, "B": 2}
_INBOUND = [
    Wagon("a1", "A"), Wagon("a2", "A", True), Wagon("a3", "A", True),
    Wagon("b1", "B"), Wagon("b2", "B"), Wagon("b3", "B"),
]


# --- Part 1: yard classification ------------------------------------------

def test_hand_verified_classification_under_hazmat_and_length():
    r = classify(_INBOUND, _CAPS)
    assert [w.id for w in r["tracks"]["A"]] == ["a1", "a2"]
    assert [w.id for w in r["tracks"]["B"]] == ["b1", "b2"]
    assert r["reshuffles"] == 2
    reasons = {x["id"]: x["reason"] for x in r["rework"]}
    assert reasons == {"a3": "hazmat-adjacency", "b3": "track-full"}
    assert r["valid"] is True


def test_validity_check_catches_both_violations():
    # over capacity
    assert is_valid_classification({"A": [Wagon("1", "A"), Wagon("2", "A")]}, {"A": 1}) is False
    # two hazmat adjacent
    bad = {"A": [Wagon("1", "A", True), Wagon("2", "A", True)]}
    assert is_valid_classification(bad, {"A": 5}) is False
    # clean
    ok = {"A": [Wagon("1", "A", True), Wagon("2", "A"), Wagon("3", "A", True)]}
    assert is_valid_classification(ok, {"A": 5}) is True


def test_synthetic_yard_is_deterministic_valid_and_labelled():
    w1, c1 = synthetic_yard()
    w2, c2 = synthetic_yard()
    assert [(w.id, w.dest, w.hazmat) for w in w1] == [(w.id, w.dest, w.hazmat) for w in w2]
    r = classify(w1, c1)
    assert r["valid"] is True and r["reshuffles"] == 2
    # capacities respected on every track
    for dest, wagons in r["tracks"].items():
        assert len(wagons) <= c1[dest]


# --- Part 2: connection to the network (Phase C priority) -----------------

def test_freight_train_yields_to_express_under_contention():
    net = baseline.build_network()
    express = Train("EXP", "S1", "S2", ("SEG-12",), 0, priority=PRIORITY_EXPRESS)
    freight = Train("FRT", "S2", "S1", ("SEG-12",), 0, priority=PRIORITY_FREIGHT)
    res = recompute_schedule(net, [express, freight], [])
    assert res.actions["EXP"].action == "unchanged" and res.actions["EXP"].depart_at == 0
    assert res.actions["FRT"].action == "hold" and res.actions["FRT"].depart_at >= 11
    assert find_conflicts(list(res.occupancy_table)) == []     # still collision-free


def test_freight_is_lowest_priority_and_yields_to_a_passenger_too():
    assert PRIORITY_FREIGHT < PRIORITY_PASSENGER < PRIORITY_EXPRESS
    net = baseline.build_network()
    passenger = Train("PAS", "S1", "S2", ("SEG-12",), 0)            # default PASSENGER
    freight = Train("FRT", "S2", "S1", ("SEG-12",), 0, priority=PRIORITY_FREIGHT)
    res = recompute_schedule(net, [passenger, freight], [])
    assert res.actions["PAS"].action == "unchanged"
    assert res.actions["FRT"].action == "hold"                     # freight yields


def test_snapshot_exposes_yard_and_priority_connection():
    snap = AppState(dataset="wb").snapshot()
    fr = snap["freight"]
    assert fr["applicable"] is True and fr["synthetic"] is True
    assert fr["valid"] is True and fr["reshuffles"] == 2
    assert len(fr["freight_trains"]) == 3                          # one per destination track
    assert all(t["priority"] == "freight" for t in fr["freight_trains"])
    # the connection: a freight train yields to an express via the live engine
    assert fr["priority_demo"]["freight_yields"] is True
    assert fr["priority_demo"]["freight"]["action"] == "hold"
