"""Gate (Phase C): the real-corridor UI renders all 27 stations and both
display attributes, while every 6-city feature still works.

Display layer only — these tests touch the served page and the snapshot the
page renders from; the engine is never imported here and stays zero-diff.
"""

import json
import urllib.request

import pytest

from app.server import serve_in_thread
from app.state import AppState
from data.real_corridor import STATIONS, TRAIN_ATTRS


@pytest.fixture()
def real_url():
    server, url = serve_in_thread(AppState(dataset="real"))
    yield url
    server.shutdown()


def _get(url, path):
    with urllib.request.urlopen(url + path, timeout=5) as r:
        assert r.status == 200
        return r.read().decode("utf-8")


def test_page_geo_positions_all_27_real_stations(real_url):
    """Every real station has a coordinate baked into the page so the map can
    place all 27 on the India outline."""
    html = _get(real_url, "/")
    assert "REAL_COORDS" in html
    assert len(STATIONS) == 27
    for code in STATIONS:
        assert f"{code}:" in html, f"no map coordinate for station {code}"


def test_both_corridors_and_the_bina_et_diamond_are_drawable(real_url):
    """The loop stations (the eastern Bina–Katni–Jabalpur arc) are all placed,
    so the second corridor and the BINA–ET diamond render as lines."""
    html = _get(real_url, "/")
    for loop_code in ("BINA", "SGO", "DMO", "KMZ", "JBP", "NU", "PPI", "ET"):
        assert f"{loop_code}:" in html, f"loop station {loop_code} not placed"


def test_page_renders_both_display_attributes(real_url):
    """Driver employee number and loco class are wired into the board."""
    html = _get(real_url, "/")
    assert "loco_class" in html
    assert "driver_employee_no" in html
    assert "train_attrs" in html


def test_real_snapshot_exposes_27_stations_and_attrs(real_url):
    snap = json.loads(_get(real_url, "/api/state"))
    assert len(snap["stations"]) == 27
    assert set(snap["stations"]) == set(STATIONS)
    attrs = snap["train_attrs"]
    assert len(attrs) == len(TRAIN_ATTRS) == 8
    for tid, a in attrs.items():
        assert a["driver_employee_no"].startswith("DRV-"), tid
        assert a["loco_class"].startswith(("WAP", "WAG", "WDM")), tid


def test_every_station_code_has_a_display_name_so_no_raw_codes_leak(real_url):
    """withNames() humanizes prose by replacing known codes; this holds only if
    every station code maps to a distinct real name."""
    snap = json.loads(_get(real_url, "/api/state"))
    names = snap["display_names"]
    for code in snap["stations"]:
        assert code in names and names[code] and names[code] != code, code
    assert len(set(names[c] for c in snap["stations"])) == 27  # names unique


def test_six_city_ui_features_still_present_on_real_page(real_url):
    """Regression: ghost preview, How-this-works, legend, outline, plain
    summary, the five anomaly controls — all still served."""
    html = _get(real_url, "/")
    for marker in (
        "How this works", "india-outline", "Network map", "plain-summary",
        "/api/preview", "Apply", "Cancel", "Reset to baseline",
        "track_closed", "track_blocked", "reduced_speed",
        "train_delayed", "train_cancelled", "display_names",
        "Illustrative network inspired by Indian Railways",
    ):
        assert marker in html, marker
