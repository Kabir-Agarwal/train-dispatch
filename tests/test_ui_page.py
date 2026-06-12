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
