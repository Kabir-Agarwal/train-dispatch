"""Gates for the live-action features at the app + page layer:

  - restrict-a-train and add-a-train flow through AppState.inject / .preview;
  - ghost preview for both mutates nothing;
  - the HTTP API accepts the new `new_trains` channel;
  - reset clears added trains;
  - the served page carries the new control rows and wiring.
"""

import json
import urllib.request

import pytest

from app.server import serve_in_thread
from app.state import AppState, _next_train_id
from engine.errors import DispatchError


def fresh():
    return AppState()  # 6-city baseline


# --- restrict a train (AppState) ----------------------------------------

def test_restrict_reroutes_one_train_others_unchanged():
    s = fresh()
    s.inject([{"type": "train_restricted", "train": "T1", "segment": "SEG-34"}])
    snap = s.snapshot()
    assert snap["anomalies"] == ["train_restricted(T1, SEG-34)"]
    t1 = next(t for t in snap["trains"] if t["id"] == "T1")
    t5 = next(t for t in snap["trains"] if t["id"] == "T5")
    assert t1["action"] == "reroute"
    assert "SEG-34" not in (t1["path"] or [])
    assert "SEG-34" in (t5["path"] or [])         # unrestricted train still uses it
    # passenger view stays consistent + guard-clean for the rerouted train
    p1 = s.passenger("T1")
    assert p1["eta"] == max(t1["arrivals"].values())
    assert p1["violations"] == []


def test_restrict_then_reset_clears_it():
    s = fresh()
    s.inject([{"type": "train_restricted", "train": "T1", "segment": "SEG-34"}])
    s.reset()
    snap = s.snapshot()
    assert snap["anomalies"] == []
    assert s.passenger("T1")["eta"] == 30          # back to baseline


# --- add a train live (AppState) ----------------------------------------

def test_add_train_schedules_and_appears_with_badge():
    s = fresh()
    s.inject([], new_trains=[{"origin": "S3", "destination": "S6", "departure": 40}])
    snap = s.snapshot()
    assert snap["added_train_ids"] == ["T6"]       # deterministic next id
    t6 = next(t for t in snap["trains"] if t["id"] == "T6")
    assert t6["action"] == "unchanged"
    assert max(t6["arrivals"].values()) == 51      # 40 + SEG-36 (11)
    assert s.passenger("T6")["eta"] == 51          # both views agree


def test_add_train_that_conflicts_is_adapted_not_forced():
    s = fresh()
    # S1->S2 departing 0 contends with T1 on SEG-12 [0,10]; engine adapts it
    s.inject([], new_trains=[{"origin": "S1", "destination": "S2", "departure": 0}])
    snap = s.snapshot()
    t6 = next(t for t in snap["trains"] if t["id"] == "T6")
    assert t6["action"] in ("hold", "reroute", "depart_delayed")
    assert t6["arrivals"] is not None


def test_add_train_impossible_is_reported_and_state_untouched():
    s = fresh()
    # isolate S6 first (close all three of its segments), then try to add to S6
    s.inject([
        {"type": "track_closed", "segment": "SEG-56"},
        {"type": "track_closed", "segment": "SEG-26"},
        {"type": "track_closed", "segment": "SEG-36"},
    ])
    before = s.snapshot()
    with pytest.raises(DispatchError, match="no available route"):
        s.inject([], new_trains=[{"origin": "S1", "destination": "S6", "departure": 0}])
    assert s.snapshot() == before                  # nothing committed on failure


def test_add_train_reset_clears_added_trains():
    s = fresh()
    s.inject([], new_trains=[{"origin": "S3", "destination": "S6", "departure": 40}])
    assert s.snapshot()["added_train_ids"] == ["T6"]
    s.reset()
    assert s.snapshot()["added_train_ids"] == []
    with pytest.raises(DispatchError):
        s.passenger("T6")                          # the added train is gone


def test_next_train_id_is_deterministic():
    assert _next_train_id({"T1", "T2", "T3", "T4", "T5"}) == "T6"
    assert _next_train_id({"T101", "T108"}) == "T109"
    assert _next_train_id(set()) == "T1"


# --- ghost preview mutates nothing for the new actions ------------------

def test_preview_add_train_changes_nothing():
    s = fresh()
    body = s.preview([], new_trains=[{"origin": "S3", "destination": "S6", "departure": 40}])
    assert body["preview"] is True
    assert "T6" in body["added_train_ids"]
    assert any(d["id"] == "T6" and d["old_action"] is None for d in body["deltas"])
    # the live state is untouched: no added train committed
    assert s.snapshot()["added_train_ids"] == []


def test_preview_restriction_changes_nothing():
    s = fresh()
    body = s.preview([{"type": "train_restricted", "train": "T1", "segment": "SEG-34"}])
    assert body["preview"] is True
    assert s.snapshot()["anomalies"] == []         # nothing committed


# --- HTTP API accepts the new_trains channel ----------------------------

@pytest.fixture()
def base_url():
    server, url = serve_in_thread()
    yield url
    server.shutdown()


def _post(url, path, payload):
    data = json.dumps(payload).encode()
    req = urllib.request.Request(
        url + path, data=data, headers={"Content-Type": "application/json"}
    )
    with urllib.request.urlopen(req, timeout=5) as r:
        return r.status, json.loads(r.read().decode())


def test_http_add_train_and_restrict(base_url):
    # preview an add-train
    code, body = _post(base_url, "/api/preview",
                       {"new_trains": [{"origin": "S3", "destination": "S6",
                                        "departure": 40}]})
    assert code == 200 and "T6" in body["added_train_ids"]
    # apply it
    code, snap = _post(base_url, "/api/inject",
                       {"new_trains": [{"origin": "S3", "destination": "S6",
                                        "departure": 40}]})
    assert code == 200 and snap["added_train_ids"] == ["T6"]
    # apply a restriction on top
    code, snap = _post(base_url, "/api/inject",
                       {"anomalies": [{"type": "train_restricted",
                                       "train": "T1", "segment": "SEG-34"}]})
    assert code == 200
    assert "train_restricted(T1, SEG-34)" in snap["anomalies"]


# --- the served page carries the new control rows -----------------------

def test_page_has_restrict_and_add_train_controls(base_url):
    with urllib.request.urlopen(base_url + "/", timeout=5) as r:
        html = r.read().decode("utf-8")
    for marker in (
        "Restrict a train from a track", "train_restricted",
        "Add a new train", "new_trains", "triggerAddTrain",
        "added_train_ids", "added-tag",
        # every action still one labeled row with a caption
        "Close a track", "Block a track", "Reduce speed on a track",
        "Delay a train", "Cancel a train", "Reset to baseline",
    ):
        assert marker in html, marker
