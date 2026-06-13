"""Gates for Feature 2 — rule-based dynamic pricing (NOT ML).

Fare changes correctly with distance, occupancy and time-to-departure on
hand-verified inputs; the passenger view returns ETA + fare together; synthetic
occupancy/demand is labelled; the moving-average forecast is real arithmetic;
deterministic over 5 runs. All additive — scheduling/golden gate untouched.
"""

import json
import urllib.request

import pytest

from app.server import serve_in_thread
from app.state import AppState
from engine import pricing


# --- the pricing formula (hand-verified) -------------------------------

def test_fare_formula_hand_verified():
    # base = 20 + 0.5*100 = 70; occ_mult = 1 + 0.6*0.5 = 1.3;
    # surge(ttd=0) = 1 -> time_mult = 1.4;  fare = round(70*1.3*1.4) = round(127.4)
    est = pricing.fare_estimate(100, 0.5, 0)
    assert est["base"] == 70 and est["occupancy_mult"] == 1.3 and est["time_mult"] == 1.4
    assert est["fare"] == 127
    # surge ramps off once departure is >= the window away
    assert pricing.time_surge(120) == 0.0 and pricing.time_surge(0) == 1.0
    assert pricing.time_surge(60) == 0.5


def test_fare_rises_with_occupancy_distance_and_imminence():
    f = pricing.fare_estimate
    assert f(100, 0.9, 0)["fare"] > f(100, 0.4, 0)["fare"]   # fuller -> dearer
    assert f(300, 0.5, 0)["fare"] > f(100, 0.5, 0)["fare"]   # longer -> dearer
    assert f(100, 0.5, 0)["fare"] > f(100, 0.5, 120)["fare"]  # sooner -> dearer


def test_synthetic_occupancy_is_deterministic_and_bounded():
    for tid in ("T1", "T101", "T999"):
        o1, o2 = pricing.synthetic_occupancy(tid), pricing.synthetic_occupancy(tid)
        assert o1 == o2 and 0.35 <= o1 <= 0.95


def test_moving_average_is_real_arithmetic():
    assert pricing.moving_average([10, 20, 30], 2) == [10.0, 15.0, 25.0]
    assert pricing.moving_average([4, 4, 4, 4], 3) == [4.0, 4.0, 4.0, 4.0]
    assert pricing.forecast_next([10, 20, 30], 2) == 25.0
    series = pricing.synthetic_demand_series("T101")
    assert len(series) == 14 and all(5.0 <= v <= 100.0 for v in series)


# --- passenger view: ETA + fare together, consistent with the engine ---

def test_passenger_shows_eta_and_fare_together():
    s = AppState(dataset="real")
    p = s.passenger("T101")
    assert p["eta"] is not None
    assert p["fare"] and p["fare"]["fare"] > 0 and p["fare"]["currency"] == "₹"
    assert "rule-based dynamic pricing" in p["fare_reason"]
    assert p["synthetic_occupancy"] is True
    assert p["occupancy"] is not None
    assert p["fare"]["distance"] == 1090            # T101 NDLS->NGP route km


def test_fare_follows_the_engine_on_reroute_and_delay():
    s = AppState()  # 6-city baseline; T1 runs SEG-12/23/34 (distance 30)
    base = s.passenger("T1")["fare"]["fare"]
    assert s.passenger("T1")["fare"]["distance"] == 30
    # closing SEG-34 reroutes T1 onto a shorter path -> distance & fare change
    s.inject([{"type": "track_closed", "segment": "SEG-34"}])
    after = s.passenger("T1")
    assert after["fare"]["distance"] == 22 and after["fare"]["fare"] != base


def test_cancelled_train_has_no_fare():
    s = AppState()
    s.inject([{"type": "train_cancelled", "train": "T3"}])
    p = s.passenger("T3")
    assert p["eta"] is None and p["fare"] is None


def test_pricing_is_deterministic_over_5_runs():
    runs = [json.dumps(AppState(dataset="wb").passenger("T1"), sort_keys=True,
                       ensure_ascii=True) for _ in range(5)]
    assert all(r == runs[0] for r in runs)


# --- UI surfaces it honestly -------------------------------------------

def test_passenger_panel_and_honesty_in_page():
    server, url = serve_in_thread(AppState(dataset="real"))
    try:
        with urllib.request.urlopen(url + "/", timeout=5) as r:
            html = r.read().decode("utf-8")
        for marker in ("rule-based dynamic pricing", "pass-fare", "synthetic",
                       "production would use real bookings"):
            assert marker in html, marker
        # honesty: never claim ML / AI for pricing
        assert "machine learning" not in html.lower()
    finally:
        server.shutdown()
