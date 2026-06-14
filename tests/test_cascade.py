"""Phase G gate — delay cascade prediction (blast radius).

Value-asserting on a HAND-VERIFIED case: on the 6-city baseline, T2 and T4 share
SEG-56 with exactly one minute of clearance (T2 [20,29], T4 [30,39]). Delaying T2
by 2 pushes its SEG-56 window to [22,31], so T4 must wait — inheriting +2. The
cascade must report precisely: primary T2 +2, downstream {T4: +2}, nobody else.
"""

import data.baseline as baseline
from app.state import AppState
from engine.cascade import delay_cascade


def _net():
    return baseline.build_network(), baseline.build_trains()


def test_hand_verified_t2_delay_knocks_on_t4_exactly():
    net, trains = _net()
    c = delay_cascade(net, trains, [], "T2", 2)
    assert c["applicable"] is True
    assert c["train"] == "T2" and c["minutes"] == 2
    assert c["primary_delay"] == 2                       # T2's own arrival shift
    assert c["downstream"] == [{"id": "T4", "minutes": 2}]   # only T4, +2
    assert c["trains_affected"] == 1
    assert c["total_knock_on"] == 2


def test_isolated_train_has_no_blast_radius():
    """T3 runs S2->S6 on SEG-26, which no other baseline train uses — delaying it
    cascades to nobody."""
    net, trains = _net()
    c = delay_cascade(net, trains, [], "T3", 5)
    assert c["applicable"] is True
    assert c["primary_delay"] == 5
    assert c["downstream"] == [] and c["trains_affected"] == 0


def test_larger_delay_still_hits_t4_and_is_monotonic():
    net, trains = _net()
    small = delay_cascade(net, trains, [], "T2", 2)["total_knock_on"]
    big = delay_cascade(net, trains, [], "T2", 12)
    t4 = next((d for d in big["downstream"] if d["id"] == "T4"), None)
    assert t4 is not None and t4["minutes"] >= 2          # T4 still inherits
    assert big["total_knock_on"] >= small                 # a bigger delay never reduces the blast


def test_not_applicable_for_unknown_train_or_zero_delay():
    net, trains = _net()
    assert delay_cascade(net, trains, [], "T999", 5) == {"applicable": False}
    assert delay_cascade(net, trains, [], "T2", 0) == {"applicable": False}


def test_method_is_named_and_honest():
    net, trains = _net()
    c = delay_cascade(net, trains, [], "T2", 2)
    assert "forward re-simulation diff" in c["method"]


def test_snapshot_surfaces_blast_radius_for_an_active_delay():
    s = AppState()                                        # 6-city baseline
    assert s.snapshot()["delay_cascade"] == {"applicable": False}   # nothing yet
    s.inject([{"type": "train_delayed", "train": "T2", "minutes": 2}])
    cas = s.snapshot()["delay_cascade"]
    assert cas["applicable"] is True
    assert cas["train"] == "T2"
    assert cas["downstream"] == [{"id": "T4", "minutes": 2}]
    # matches the pure engine computation (no snapshot/engine drift)
    eng = delay_cascade(s.network, s.trains, [], "T2", 2)
    assert cas["downstream"] == eng["downstream"]


def test_cascade_clears_when_delay_removed():
    s = AppState()
    s.inject([{"type": "train_delayed", "train": "T2", "minutes": 2}])
    assert s.snapshot()["delay_cascade"]["applicable"] is True
    s.reset()
    assert s.snapshot()["delay_cascade"] == {"applicable": False}
