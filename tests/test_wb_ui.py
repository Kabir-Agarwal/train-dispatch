"""Gate (West Bengal UI): the WB mode renders all 50 stations on a REAL
GEOGRAPHIC layout (lat/long on a WB outline, zoomable/pannable) and the default
money-shot reroute is drawn. Display layer only — engine untouched; these tests
hit the served page and the snapshot it renders from.
"""

import json
import urllib.request

import pytest

from app.server import serve_in_thread
from app.state import AppState
from data.west_bengal import STATIONS


@pytest.fixture()
def wb_url():
    server, url = serve_in_thread(AppState(dataset="wb"))
    yield url
    server.shutdown()


def _get(url, path):
    with urllib.request.urlopen(url + path, timeout=5) as r:
        assert r.status == 200
        return r.read().decode("utf-8")


def test_page_geo_positions_all_50_wb_stations(wb_url):
    """Every WB station has a real lat/long baked into the page, projected onto
    the WB state outline; the map is zoomable/pannable."""
    html = _get(wb_url, "/")
    assert "WB_GEO" in html and "WB_PRIMARY" in html and "mapWB" in html
    assert "wb-graticule" in html             # geographic graticule (no blob)
    assert "zoom-controls" in html and "Reset view" in html  # zoom/pan UI
    assert "train-legend" in html             # colour->train side legend
    assert len(STATIONS) == 50
    for code in STATIONS:
        assert f"{code}:" in html, f"no WB lat/long for {code}"
    # spot-check real geography: Howrah ~22.58N 88.34E, NJP far north ~26.68N
    assert "22.585" in html and "88.342" in html   # Howrah
    assert "26.680" in html                        # New Jalpaiguri (north)


def test_wb_snapshot_has_50_stations_and_is_wb_mode(wb_url):
    snap = json.loads(_get(wb_url, "/api/state"))
    assert snap["dataset"] == "wb"
    assert len(snap["stations"]) == 50
    assert set(snap["stations"]) == set(STATIONS)
    # every code maps to a unique real name so no raw codes leak via withNames
    names = snap["display_names"]
    for code in snap["stations"]:
        assert code in names and names[code] and names[code] != code
    assert len(set(names[c] for c in snap["stations"])) == 50


def test_default_demo_anomaly_draws_a_reroute(wb_url):
    """WB loads with the deck scenario: close Adra Jn–Bankura (ADRA-BQA) and
    delay T1 by 35 min. At least one train reroutes, and every rerouted train's
    drawn path avoids the closed line (this is the path the map traces)."""
    snap = json.loads(_get(wb_url, "/api/state"))
    assert "track_closed(ADRA-BQA)" in snap["anomalies"]
    assert "train_delayed(T1, 35 min)" in snap["anomalies"]
    rerouted = [t for t in snap["trains"] if t["action"] == "reroute"]
    assert rerouted, "expected at least one rerouted train for the default scenario"
    for t in rerouted:
        assert t["station_times"], "rerouted train must have a drawable path"
        assert "ADRA-BQA" not in (t["path"] or [])


def test_reroute_is_collision_free_and_consistent(wb_url):
    snap = json.loads(_get(wb_url, "/api/state"))
    # passenger view agrees with the board for a rerouted train (no fabrication)
    t = next(t for t in snap["trains"] if t["action"] == "reroute")
    p = json.loads(_get(wb_url, "/api/passenger/" + t["id"]))
    assert p["eta"] == max(t["arrivals"].values())
    assert p["violations"] == []


def test_reset_clears_default_anomaly_back_to_baseline():
    s = AppState(dataset="wb")
    snap0 = s.snapshot()
    # default deck scenario: close Adra Jn–Bankura + delay T1 by 35 min
    assert snap0["anomalies"] == ["track_closed(ADRA-BQA)", "train_delayed(T1, 35 min)"]
    seg0 = next(x for x in snap0["segments"] if x["id"] == "ADRA-BQA")
    assert seg0["status"] == "closed"                # default closure active
    s.reset()
    snap = s.snapshot()
    assert snap["anomalies"] == []                   # default anomalies cleared
    seg = next(x for x in snap["segments"] if x["id"] == "ADRA-BQA")
    assert seg["status"] == "open"                   # Adra Jn–Bankura line reopened


def test_wb_page_keeps_corridor_features(wb_url):
    """Regression: the 7 control rows, ghost preview, how-it-works, legend,
    plain summary, restriction + add-train all still served."""
    html = _get(wb_url, "/")
    for marker in (
        "Close a track", "Block a track", "Reduce speed on a track",
        "Delay a train", "Cancel a train", "Restrict a train from a track",
        "Add a new train", "Reset to baseline",
        "/api/preview", "Apply", "Cancel", "How this works", "plain-summary",
        "train_restricted", "new_trains", "Network map",
    ):
        assert marker in html, marker
