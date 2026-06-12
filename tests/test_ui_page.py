"""Gate: ui unit — the served page carries every control the demo needs."""

import urllib.request

import pytest

from app.server import serve_in_thread


@pytest.fixture()
def base_url():
    server, url = serve_in_thread()
    yield url
    server.shutdown()


def test_index_served_with_all_demo_controls(base_url):
    with urllib.request.urlopen(base_url + "/", timeout=5) as r:
        assert r.status == 200
        html = r.read().decode()
    # admin: the five anomaly buttons + reset (admin is the only source)
    for marker in ("track_closed", "track_blocked", "reduced_speed",
                   "train_delayed", "train_cancelled", "Reset to baseline"):
        assert marker in html, marker
    # admin board pieces
    for marker in ("Network — segment status", "Schedule board", "Decision log"):
        assert marker in html, marker
    # passenger view present and minimal
    assert "Passenger view" in html
    assert "pass-eta" in html
    # it talks to the same API the end-to-end gate proved
    for endpoint in ("/api/state", "/api/inject", "/api/reset", "/api/passenger/"):
        assert endpoint in html, endpoint


def test_run_ui_is_one_command():
    src = open("run_ui.py").read()
    assert "make_server" in src and "webbrowser.open" in src


def test_page_is_served_as_valid_utf8(base_url):
    # cp1252 regression guard: the bullet and delta glyphs must arrive as
    # real UTF-8 bytes, decodable, not mojibake.
    with urllib.request.urlopen(base_url + "/", timeout=5) as r:
        raw = r.read()
    html = raw.decode("utf-8")  # raises if the server mangled the bytes
    assert "Δ delay" in html
    assert "•" in html or "•" in html
    assert "â€" not in html  # the classic cp1252 mojibake signature


def test_map_and_preview_controls_present(base_url):
    with urllib.request.urlopen(base_url + "/", timeout=5) as r:
        html = r.read().decode("utf-8")
    for marker in ("Network map", "time-slider", "/api/preview",
                   "Apply", "Cancel", "station_times"):
        assert marker in html, marker
