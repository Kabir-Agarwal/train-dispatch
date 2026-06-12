"""Gate: server unit — THE DEMO SEQUENCE over real HTTP:
inject anomaly -> recompute -> reasoning visible -> passenger ETA updates.
All expected values hand-verified in earlier phases."""

import json
import urllib.request
import urllib.error

import pytest

from app.server import serve_in_thread


@pytest.fixture()
def base_url():
    server, url = serve_in_thread()
    yield url
    server.shutdown()


def get(url):
    with urllib.request.urlopen(url, timeout=5) as r:
        return r.status, json.loads(r.read())


def post(url, payload=None):
    data = json.dumps(payload or {}).encode()
    req = urllib.request.Request(
        url, data=data, headers={"Content-Type": "application/json"}
    )
    with urllib.request.urlopen(req, timeout=5) as r:
        return r.status, json.loads(r.read())


def test_full_demo_sequence_end_to_end(base_url):
    # 1. baseline board
    code, snap = get(f"{base_url}/api/state")
    assert code == 200
    assert snap["anomalies"] == []
    code, p2 = get(f"{base_url}/api/passenger/T2")
    assert (code, p2["eta"]) == (200, 29)  # baseline S6@29

    # 2. admin injects: track S3-S4 closed (the demo's anomaly)
    code, snap = post(f"{base_url}/api/inject", {
        "anomalies": [{"type": "track_closed", "segment": "SEG-34"}],
    })
    assert code == 200

    # 3. recompute visible on the board: T1 rerouted, S4@22
    t1 = next(t for t in snap["trains"] if t["id"] == "T1")
    assert t1["action"] == "reroute"
    assert t1["arrivals"]["S4"] == 22

    # 4. the reasoning log is visible and names the second-order fix
    assert [e["train_id"] for e in snap["decision_log"]] == ["T1", "T2", "T5"]
    t2_line = snap["decision_log"][1]["text"]
    assert "T1" in t2_line and "34" in t2_line

    # 5. passenger ETA updated and CONSISTENT with the board
    code, p2 = get(f"{base_url}/api/passenger/T2")
    assert code == 200
    assert p2["eta"] == 34
    t2 = next(t for t in snap["trains"] if t["id"] == "T2")
    assert p2["eta"] == t2["arrivals"]["S6"]  # same engine value, same minute
    assert "minute 34" in p2["text"]
    assert p2["violations"] == []

    # 6. (stretch step) second anomaly accumulates
    code, snap = post(f"{base_url}/api/inject", {
        "anomalies": [{"type": "train_delayed", "train": "T4", "minutes": 5}],
    })
    assert code == 200
    assert len(snap["anomalies"]) == 2
    t4 = next(t for t in snap["trains"] if t["id"] == "T4")
    assert t4["arrivals"]["S6"] == 44

    # 7. reset -> baseline again
    code, snap = post(f"{base_url}/api/reset")
    assert code == 200
    assert snap["anomalies"] == []
    code, p2 = get(f"{base_url}/api/passenger/T2")
    assert p2["eta"] == 29


def test_bad_requests_get_400_never_crash(base_url):
    with pytest.raises(urllib.error.HTTPError) as exc:
        post(f"{base_url}/api/inject", {
            "anomalies": [{"type": "track_closed", "segment": "SEG-99"}],
        })
    assert exc.value.code == 400
    assert "SEG-99" in json.loads(exc.value.read())["error"]

    with pytest.raises(urllib.error.HTTPError) as exc:
        get(f"{base_url}/api/passenger/T9")
    assert exc.value.code == 400

    # the server is still alive and consistent after the failures
    code, snap = get(f"{base_url}/api/state")
    assert code == 200
    assert snap["anomalies"] == []


def test_unknown_route_404(base_url):
    with pytest.raises(urllib.error.HTTPError) as exc:
        get(f"{base_url}/api/nope")
    assert exc.value.code == 404
