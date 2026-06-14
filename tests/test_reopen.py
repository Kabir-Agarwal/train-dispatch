"""Gate: selective track REOPEN — reopen ONE closed/restricted segment without a
full reset, recomputing via the existing engine. Other restrictions and added
trains are preserved; unknown/already-open segments are rejected cleanly.
"""

import json
import urllib.request

import pytest

from app.server import serve_in_thread
from app.state import AppState
from engine.errors import ValidationError


def _seg(snap, sid):
    return next(s for s in snap["segments"] if s["id"] == sid)


def test_reopen_clears_a_single_closure_and_recomputes():
    s = AppState(dataset="baseline")
    s.inject([{"type": "track_closed", "segment": "SEG-34"}])
    assert _seg(s.snapshot(), "SEG-34")["status"] == "closed"
    s.reopen("SEG-34")
    snap = s.snapshot()
    assert _seg(snap, "SEG-34")["status"] == "open"
    assert snap["anomalies"] == []          # the only anomaly is gone
    # recomputed back to the all-clear plan
    assert all(t["action"] == "unchanged" for t in snap["trains"])


def test_reopen_only_targets_the_named_segment():
    s = AppState(dataset="baseline")
    s.inject([
        {"type": "track_closed", "segment": "SEG-34"},
        {"type": "track_closed", "segment": "SEG-15"},
    ])
    s.reopen("SEG-34")
    snap = s.snapshot()
    assert _seg(snap, "SEG-34")["status"] == "open"     # reopened
    assert _seg(snap, "SEG-15")["status"] == "closed"   # the other stays closed
    assert "track_closed(SEG-15)" in snap["anomalies"]
    assert "track_closed(SEG-34)" not in snap["anomalies"]


def test_reopen_clears_a_speed_restriction_too():
    s = AppState(dataset="baseline")
    s.inject([{"type": "reduced_speed", "segment": "SEG-56", "factor": 0.5}])
    assert _seg(s.snapshot(), "SEG-56")["status"] == "reduced-speed"
    s.reopen("SEG-56")
    assert _seg(s.snapshot(), "SEG-56")["status"] == "open"


def test_reopen_preserves_other_restrictions_and_added_trains():
    s = AppState(dataset="baseline")
    s.inject(
        [{"type": "track_closed", "segment": "SEG-34"},
         {"type": "train_restricted", "train": "T1", "segment": "SEG-15"}],
        new_trains=[{"origin": "S1", "destination": "S6", "departure": 0}],
    )
    added_before = s.snapshot()["added_train_ids"]
    assert added_before, "precondition: a train was added"
    s.reopen("SEG-34")
    snap = s.snapshot()
    assert _seg(snap, "SEG-34")["status"] == "open"
    # the per-train restriction survives (it is not a segment closure)
    assert any("train_restricted" in a and "T1" in a for a in snap["anomalies"])
    assert snap["added_train_ids"] == added_before     # added train kept


def test_reopen_default_wb_money_shot_segment():
    s = AppState(dataset="wb")                 # default closes MYM-BWN
    assert "track_closed(MYM-BWN)" in s.snapshot()["anomalies"]
    s.reopen("MYM-BWN")
    snap = s.snapshot()
    assert _seg(snap, "MYM-BWN")["status"] == "open"
    assert snap["anomalies"] == []


def test_reopen_segment_with_no_closure_is_rejected():
    s = AppState(dataset="baseline")
    s.inject([{"type": "track_closed", "segment": "SEG-34"}])
    with pytest.raises(ValidationError):
        s.reopen("SEG-15")                     # SEG-15 is open -> nothing to reopen


def test_reopen_unknown_segment_is_rejected():
    s = AppState(dataset="baseline")
    s.inject([{"type": "track_closed", "segment": "SEG-34"}])
    with pytest.raises(ValidationError):
        s.reopen("SEG-does-not-exist")


def test_reopen_http_endpoint_round_trip():
    server, url = serve_in_thread(AppState(dataset="wb"))
    try:
        body = json.dumps({"segment": "MYM-BWN"}).encode()
        req = urllib.request.Request(
            url + "/api/reopen", data=body, method="POST",
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=5) as r:
            snap = json.loads(r.read().decode())
        assert _seg(snap, "MYM-BWN")["status"] == "open"
        assert snap["anomalies"] == []
        # a bad request reopens nothing and returns 400, not a crash
        bad = urllib.request.Request(
            url + "/api/reopen",
            data=json.dumps({"segment": "MYM-BWN"}).encode(), method="POST",
            headers={"Content-Type": "application/json"},
        )
        try:
            urllib.request.urlopen(bad, timeout=5)
            assert False, "expected HTTP 400 for already-open segment"
        except urllib.error.HTTPError as e:
            assert e.code == 400
    finally:
        server.shutdown()
