"""Gate: state unit — including THE consistency test (SPEC F6 adversarial 1):
the passenger ETA must equal the engine's computed arrival on the admin board,
for every train, in every scenario. The two views can never disagree."""

import pytest

from app.state import AppState, parse_anomaly
from engine.anomalies import TrackClosed
from engine.errors import ValidationError


def fresh():
    return AppState()


def admin_arrival(snapshot, tid):
    train = next(t for t in snapshot["trains"] if t["id"] == tid)
    if train["arrivals"] is None:
        return None
    dest = list(train["arrivals"])[-1] if train["arrivals"] else None
    # destination = last station in arrival order; safer: max by minute
    return max(train["arrivals"].values())


def test_baseline_state_before_any_anomaly():
    s = fresh()
    snap = s.snapshot()
    assert snap["anomalies"] == []
    assert snap["decision_log"] == []
    assert snap["total_added_delay"] == 0
    t1 = next(t for t in snap["trains"] if t["id"] == "T1")
    assert t1["action"] == "unchanged"
    assert t1["arrivals"] == {"S1": 0, "S2": 10, "S3": 18, "S4": 30}
    # passenger sees the same baseline minute
    assert s.passenger("T1")["eta"] == 30
    assert s.passenger("T3")["eta"] == 32


def test_inject_closure_updates_board_log_and_passenger():
    s = fresh()
    s.inject([{"type": "track_closed", "segment": "SEG-34"}])
    snap = s.snapshot()
    assert snap["anomalies"] == ["track_closed(SEG-34)"]
    seg = next(x for x in snap["segments"] if x["id"] == "SEG-34")
    assert seg["status"] == "closed"
    t1 = next(t for t in snap["trains"] if t["id"] == "T1")
    assert t1["action"] == "reroute"
    assert t1["arrivals"]["S4"] == 22
    assert [e["train_id"] for e in snap["decision_log"]] == ["T1", "T2", "T5"]
    assert snap["total_added_delay"] == -11
    # passenger view: same engine minutes, short reason text, guard-clean
    p2 = s.passenger("T2")
    assert p2["eta"] == 34
    assert "minute 34" in p2["text"]
    assert p2["violations"] == []


def test_consistency_passenger_equals_admin_for_every_train_every_scenario():
    scenarios = [
        [],
        [{"type": "track_closed", "segment": "SEG-34"}],
        [{"type": "track_closed", "segment": "SEG-15"}],
        [{"type": "train_delayed", "train": "T2", "minutes": 2}],
        [{"type": "train_delayed", "train": "T1", "minutes": 12}],
        [{"type": "reduced_speed", "segment": "SEG-56", "factor": 0.5}],
        [{"type": "track_closed", "segment": "SEG-34"},
         {"type": "track_closed", "segment": "SEG-45"}],
        [{"type": "train_cancelled", "train": "T3"}],
    ]
    for payloads in scenarios:
        s = fresh()
        if payloads:
            s.inject(payloads)
        snap = s.snapshot()
        for train in snap["trains"]:
            p = s.passenger(train["id"])
            if train["arrivals"] is None:
                assert p["eta"] is None  # nothing fabricated, both views agree
            else:
                # destination arrival on the admin board == passenger ETA
                assert p["eta"] == max(train["arrivals"].values()), (
                    payloads, train["id"],
                )
            assert p["violations"] == []


def test_second_anomaly_accumulates():
    s = fresh()
    s.inject([{"type": "track_closed", "segment": "SEG-34"}])
    s.inject([{"type": "train_delayed", "train": "T4", "minutes": 5}])
    snap = s.snapshot()
    assert snap["anomalies"] == [
        "track_closed(SEG-34)", "train_delayed(T4, 5 min)",
    ]
    t4 = next(t for t in snap["trains"] if t["id"] == "T4")
    assert t4["action"] == "depart_delayed"
    assert t4["arrivals"] == {"S4": 28, "S5": 35, "S6": 44}  # Phase 2 verified


def test_reset_restores_baseline():
    s = fresh()
    s.inject([{"type": "track_closed", "segment": "SEG-34"}])
    s.reset()
    snap = s.snapshot()
    assert snap["anomalies"] == []
    assert s.passenger("T1")["eta"] == 30


def test_bad_injection_rejected_and_state_kept():
    s = fresh()
    s.inject([{"type": "track_closed", "segment": "SEG-34"}])
    before = s.snapshot()
    with pytest.raises(ValidationError):
        s.inject([{"type": "warp_drive", "segment": "SEG-12"}])
    with pytest.raises(ValidationError):
        s.inject([{"type": "reduced_speed", "segment": "SEG-56", "factor": 2}])
    assert s.snapshot() == before  # state untouched by failed injections


def test_parse_anomaly_bad_params():
    with pytest.raises(ValidationError, match="bad parameters"):
        parse_anomaly({"type": "train_delayed", "train": "T1"})  # minutes missing
    assert parse_anomaly({"type": "track_closed", "segment": "SEG-12"}) == TrackClosed("SEG-12")
