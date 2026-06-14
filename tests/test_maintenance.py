"""Gates for Feature 1 — cumulative-load wear flagging (cumulative-load heuristic).

Load accumulates correctly (hand-verified, weighted and default); the threshold
flags the right segments; a MaintenanceClosure reroutes via the EXISTING engine
(byte-identical to a track closure, just labelled differently); collision-free
and deterministic. Plus the app surfaces it honestly.
"""

import json
import urllib.request

import pytest

from app.server import serve_in_thread
from app.state import AppState
from data.baseline import build_network, build_trains
from engine.anomalies import (
    MaintenanceClosure,
    TrackClosed,
    apply_anomalies,
    closed_segment_ids,
)
from engine.collision import find_conflicts
from engine.decision_log import describe_anomaly
from engine.maintenance import flagged_segments, segment_load
from engine.recompute import recompute_schedule


# --- load accumulation -------------------------------------------------

def test_default_weight_load_equals_usage_count():
    net, tr = build_network(), build_trains()
    load = segment_load(net, tr)               # no weights -> all 1
    # hand count over baseline paths: T1 & T5 share SEG-12/23/34; T2 & T4 share SEG-56
    assert load["SEG-12"] == {"usage_count": 2, "load_score": 2.0, "trains": ["T1", "T5"]}
    assert load["SEG-56"]["usage_count"] == 2 and load["SEG-56"]["load_score"] == 2.0
    assert load["SEG-36"] == {"usage_count": 0, "load_score": 0.0, "trains": []}
    for sid, s in load.items():               # default weight => score == count
        assert s["load_score"] == float(s["usage_count"]), sid


def test_weighted_load_accumulates_per_train_length():
    net, tr = build_network(), build_trains()
    load = segment_load(net, tr, {"T1": 5, "T2": 3})   # others default to 1
    assert load["SEG-12"]["load_score"] == 6.0   # T1(5) + T5(1)
    assert load["SEG-23"]["load_score"] == 6.0
    assert load["SEG-34"]["load_score"] == 6.0
    assert load["SEG-56"]["load_score"] == 4.0   # T2(3) + T4(1)
    assert load["SEG-15"]["load_score"] == 3.0   # T2(3)


def test_threshold_flags_the_right_segments_busiest_first():
    net, tr = build_network(), build_trains()
    load = segment_load(net, tr, {"T1": 5, "T2": 3})
    assert flagged_segments(load, 6) == ["SEG-12", "SEG-23", "SEG-34"]   # load 6
    assert flagged_segments(load, 4) == ["SEG-12", "SEG-23", "SEG-34", "SEG-56"]
    assert flagged_segments(load, 99) == []                              # nothing


# --- maintenance closure reuses the existing reroute engine ------------

def test_maintenance_closure_is_a_closure_for_routing():
    a = MaintenanceClosure("SEG-34")
    assert closed_segment_ids([a]) == {"SEG-34"}             # shuts the segment
    assert apply_anomalies(build_network(), [a]).segment("SEG-34").status == "closed"
    assert describe_anomaly(a) == "maintenance_closure(SEG-34)"   # labelled distinctly


def test_maintenance_closure_reroutes_identically_to_a_track_closure():
    net, tr = build_network(), build_trains()
    maint = recompute_schedule(net, tr, [MaintenanceClosure("SEG-34")])
    closed = recompute_schedule(net, tr, [TrackClosed("SEG-34")])
    # the existing engine handles it: byte-identical actions to a normal closure
    for tid in maint.actions:
        ma, ca = maint.actions[tid], closed.actions[tid]
        assert (ma.action, ma.path, ma.depart_at, ma.arrivals) == \
               (ca.action, ca.path, ca.depart_at, ca.arrivals), tid
    assert maint.actions["T1"].action == "reroute"
    assert "SEG-34" not in (maint.actions["T1"].path or ())
    assert find_conflicts(list(maint.occupancy_table)) == []      # safety absolute


def test_maintenance_closure_is_deterministic():
    net, tr = build_network(), build_trains()
    runs = [
        tuple((k, v.action, v.path, tuple(sorted((v.arrivals or {}).items())))
              for k, v in sorted(recompute_schedule(
                  net, tr, [MaintenanceClosure("SEG-34")]).actions.items()))
        for _ in range(5)
    ]
    assert all(r == runs[0] for r in runs)


# --- app surfaces it honestly ------------------------------------------

def test_snapshot_exposes_maintenance_flags_with_load_and_honest_label():
    s = AppState(dataset="real")
    m = s.snapshot()["maintenance"]
    assert "cumulative-load heuristic" in m["heuristic"]
    assert "not an AI prediction" in m["heuristic"]      # honesty
    assert m["flagged"], "expected some flagged high-load segments on the real corridor"
    for f in m["flagged"]:
        assert f["load_score"] >= m["threshold"]
        assert "cumulative load" in f["reason"]
        seg = s.snapshot()["maintenance"]["segments"][f["id"]]
        assert seg["flagged"] is True


def test_maintenance_closure_via_inject_reroutes_and_is_labelled():
    s = AppState()  # 6-city baseline
    s.inject([{"type": "maintenance_closure", "segment": "SEG-34"}])
    snap = s.snapshot()
    assert "maintenance_closure(SEG-34)" in snap["anomalies"]
    t1 = next(t for t in snap["trains"] if t["id"] == "T1")
    assert t1["action"] == "reroute"
    assert "SEG-34" not in (t1["path"] or [])


def test_page_has_maintenance_panel_and_honest_text():
    server, url = serve_in_thread(AppState(dataset="wb"))
    try:
        with urllib.request.urlopen(url + "/", timeout=5) as r:
            html = r.read().decode("utf-8")
        for marker in ("Cumulative-load wear flagging", "cumulative-load heuristic",
                       "maintenance_closure", "Schedule maintenance", "maint-group",
                       "inspection due"):
            assert marker in html, marker
        # honesty: the only mention of "AI prediction" must be the disclaimer
        assert html.count("AI prediction") == html.count("not an AI prediction")
        # Phase E honesty rename: the "predictive maintenance" framing is gone
        assert "predictive maintenance" not in html.lower()
    finally:
        server.shutdown()


def test_http_maintenance_closure_round_trip():
    server, url = serve_in_thread(AppState(dataset="wb"))
    try:
        # the WB money-shot segment MYM-BWN is flagged; close it for maintenance
        body = json.dumps({"anomalies": [{"type": "maintenance_closure",
                                          "segment": "MYM-BWN"}]}).encode()
        req = urllib.request.Request(url + "/api/inject", data=body,
                                     headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=5) as r:
            snap = json.loads(r.read().decode())
        assert "maintenance_closure(MYM-BWN)" in snap["anomalies"]
        assert any(t["action"] == "reroute" for t in snap["trains"])
    finally:
        server.shutdown()
