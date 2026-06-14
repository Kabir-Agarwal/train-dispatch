"""Phase K gate — passenger re-accommodation (Connection-Scan).

Hand-verified CSA case: A->B (train X, 0->10), B->C (train Z, 12->20), plus a
slower direct A->C (W, 0->30) and a B->C that departs too early to catch (Y, 8).
From A at time 0 the earliest arrival at C is 20 via X then Z (1 transfer) — not
the 30 direct, and not the missed Y.

Hand-verified LIVE case: cancelling T5 (PRR->HWH) strands most pairs, but a
passenger ADRA->KGP (ready at minute 65) is re-accommodated via T4
(ADRA->MDN->KGP), arriving at minute 233.
"""

import data.west_bengal as wb
from app.state import AppState
from engine.reaccommodation import earliest_journey, reaccommodate

CONNS = [
    {"from": "A", "to": "B", "dep": 0, "arr": 10, "train": "X"},
    {"from": "B", "to": "C", "dep": 8, "arr": 18, "train": "Y"},   # departs before A->B arrives
    {"from": "B", "to": "C", "dep": 12, "arr": 20, "train": "Z"},  # catchable
    {"from": "A", "to": "C", "dep": 0, "arr": 30, "train": "W"},   # slower direct
]


def test_csa_finds_earliest_two_leg_journey():
    j = earliest_journey(CONNS, "A", "C", 0)
    assert j["eta"] == 20                                  # X then Z, not the 30 direct
    assert [l["train"] for l in j["legs"]] == ["X", "Z"]
    assert j["transfers"] == 1


def test_csa_does_not_board_a_missed_connection():
    """The B->C that departs at 8 can't be caught (A->B arrives at 10); CSA uses
    the 12-departure instead."""
    j = earliest_journey(CONNS, "A", "C", 0)
    assert j["legs"][1]["train"] == "Z" and j["legs"][1]["dep"] == 12


def test_csa_unreachable_returns_none():
    assert earliest_journey(CONNS, "C", "A", 0) is None    # nothing goes back to A
    # also: too late to board anything from A
    assert earliest_journey(CONNS, "A", "C", 1) is None    # all A-departures left at 0


def test_live_cancel_T5_reaccommodates_ADRA_to_KGP_via_T4():
    net, trains = wb.build_network(), wb.build_trains()
    r = reaccommodate(net, trains, "T5")
    assert r["applicable"] is True
    p = next(x for x in r["passengers"] if x["from"] == "ADRA" and x["to"] == "KGP")
    assert p["stranded"] is False
    assert p["ready"] == 65
    assert p["eta"] == 233
    assert [l["train"] for l in p["legs"]] == ["T4", "T4"]   # ADRA->MDN->KGP on T4
    assert [(l["from"], l["to"]) for l in p["legs"]] == [("ADRA", "MDN"), ("MDN", "KGP")]


def test_live_cancel_T6_reaccommodates_PKU_to_SRC_via_T5():
    net, trains = wb.build_network(), wb.build_trains()
    r = reaccommodate(net, trains, "T6")
    p = next(x for x in r["passengers"] if x["from"] == "PKU" and x["to"] == "SRC")
    assert p["stranded"] is False and p["eta"] == 300
    assert all(l["train"] == "T5" for l in p["legs"])       # PKU->MCA->ULB->SRC on T5


def test_unknown_train_is_not_applicable():
    net, trains = wb.build_network(), wb.build_trains()
    assert reaccommodate(net, trains, "T999") == {"applicable": False}


def test_snapshot_surfaces_reaccommodation_when_a_train_is_cancelled():
    s = AppState(dataset="wb")
    assert s.snapshot()["reaccommodation"] == {"applicable": False}   # nothing cancelled
    s.inject([{"type": "train_cancelled", "train": "T5"}])
    ra = s.snapshot()["reaccommodation"]
    assert ra["applicable"] is True and ra["cancelled"] == "T5"
    assert ra["reaccommodated"] >= 1
    p = next(x for x in ra["passengers"] if x["from"] == "ADRA" and x["to"] == "KGP")
    assert p["eta"] == 233 and p["stranded"] is False
