"""Phase H gate — eco-driving speed profiles.

Hand-verified case (a single segment): 10 km to be covered in 10 min = an average
of 60 km/h, against a 110 km/h line cap. With traction energy ~ v² × distance:
  flat-out  = 110² × 10 = 121 000 units
  eco (60)  =  60² × 10 =  36 000 units
  saved     =  85 000 units  = 1 − (60/110)²  = 70 %.
The profile must meet the arrival time and use less energy than flat-out.
"""

from app.state import AppState
from engine.eco_driving import VMAX_KMPH, eco_profile


def test_hand_verified_segment_profile_and_energy():
    p = eco_profile(10, 10)                      # 10 km in 10 min, default cap 110
    assert p["feasible"] is True
    assert p["meets_arrival"] is True            # holds 60 km/h over the 10 min
    assert p["cruise_speed_kmph"] == 60.0
    assert p["vmax_kmph"] == VMAX_KMPH
    assert p["energy_flatout_units"] == 121000
    assert p["energy_eco_units"] == 36000
    assert p["energy_saved_units"] == 85000
    assert p["energy_saved_pct"] == 70
    assert p["energy_eco_units"] < p["energy_flatout_units"]   # uses less energy


def test_profile_phases_are_cruise_coast_brake_and_cover_the_distance():
    p = eco_profile(10, 10)
    names = [ph["phase"] for ph in p["phases"]]
    assert names == ["cruise", "coast", "brake"]
    assert p["phases"][0]["power"] == "on"
    assert p["phases"][1]["power"] == "off" and p["phases"][2]["power"] == "off"
    assert round(sum(ph["km"] for ph in p["phases"]), 2) == 10.0   # covers the route


def test_more_slack_saves_more_energy():
    """A looser schedule (lower required average speed) saves strictly more."""
    tight = eco_profile(10, 10)["energy_saved_pct"]     # 60 km/h -> 70%
    slack = eco_profile(10, 15)["energy_saved_pct"]     # 40 km/h -> 87%
    assert slack > tight


def test_schedule_faster_than_line_limit_is_infeasible():
    p = eco_profile(10, 5)                       # needs 120 km/h > 110 cap
    assert p["feasible"] is False
    assert p["meets_arrival"] is False
    assert p["energy_saved_pct"] == 0


def test_zero_or_negative_inputs_not_applicable():
    assert eco_profile(0, 10) == {"applicable": False}
    assert eco_profile(10, 0) == {"applicable": False}


def test_method_is_named_and_honest():
    p = eco_profile(10, 10)
    assert "cruise–coast–brake" in p["method"]
    assert "not a traction simulation" in p["method"]


def test_snapshot_exposes_fleet_eco_saving():
    snap = AppState(dataset="wb").snapshot()
    eco = snap["eco_driving"]
    assert eco["applicable"] is True
    assert eco["fleet_saved_pct"] > 0
    assert eco["total_eco_units"] < eco["total_flatout_units"]
    assert len(eco["trains"]) >= 1
    # each per-train row meets the arrival (feasible) and saves energy
    for row in eco["trains"]:
        assert row["energy_saved_pct"] > 0
        assert row["distance_km"] > 0
    # a normal undelayed run holds the scheduled ~60 km/h -> the 70% headline
    assert eco["fleet_saved_pct"] == 70
