"""Phase I gate — regenerative-braking synchronization.

Hand-verified case: on one power section P1, a train brakes at minute 10 returning
100 energy-units; another would accelerate at minute 13. With a 1-minute transfer
window the regen is WASTED (events 3 min apart). Coordinating the acceleration —
shifting it 3 min (within a 5-min slack) to minute 10 — lets it absorb the regen:
synchronized recovers 100, unsynchronized 0. Synchronization strictly wins.
"""

from app.state import AppState
from engine.regen_sync import brake_regen_units, coordinate_regen


def test_hand_verified_sync_recovers_more_than_unsync():
    supplies = [{"section": "P1", "time": 10, "energy": 100}]
    demands = [{"section": "P1", "time": 13, "energy": 100}]
    r = coordinate_regen(supplies, demands, window=1, max_shift=5)
    assert r["recovered_unsync"] == 0          # 3 min apart -> regen wasted
    assert r["recovered_sync"] == 100          # shifted to coincide -> absorbed
    assert r["extra_recovered"] == 100         # synchronization strictly wins
    assert r["available_regen"] == 100


def test_already_aligned_needs_no_coordination():
    supplies = [{"section": "P1", "time": 10, "energy": 100}]
    demands = [{"section": "P1", "time": 10, "energy": 100}]
    r = coordinate_regen(supplies, demands, window=1, max_shift=5)
    assert r["recovered_unsync"] == 100 and r["recovered_sync"] == 100
    assert r["extra_recovered"] == 0


def test_insufficient_slack_cannot_synchronize():
    supplies = [{"section": "P1", "time": 10, "energy": 100}]
    demands = [{"section": "P1", "time": 13, "energy": 100}]
    r = coordinate_regen(supplies, demands, window=1, max_shift=2)   # gap 3 > 2
    assert r["recovered_sync"] == 0 and r["extra_recovered"] == 0


def test_different_power_section_cannot_transfer():
    supplies = [{"section": "P1", "time": 10, "energy": 100}]
    demands = [{"section": "P2", "time": 10, "energy": 100}]   # other section
    assert coordinate_regen(supplies, demands, window=1, max_shift=5)["recovered_sync"] == 0


def test_recovery_is_capped_by_the_smaller_side():
    supplies = [{"section": "P1", "time": 10, "energy": 100}]
    demands = [{"section": "P1", "time": 10, "energy": 60}]    # demand limits it
    assert coordinate_regen(supplies, demands, window=1)["recovered_sync"] == 60


def test_brake_regen_units_is_quadratic_in_speed():
    assert brake_regen_units(60) == round(0.85 * 3600)         # 3060
    assert brake_regen_units(80) > brake_regen_units(60)


def test_snapshot_recovers_regen_by_coordination_on_live_wb():
    """Live case on the default WB deck scenario (close ADRA-BQA + delay T1 by
    35 min): a brake/accelerate supply–demand pair coincides at NJP (minute 542).
    A same-minute transfer wastes the regen; coordinating within 3 min recovers
    one pair * brake_regen_units(60)=3060 = 3060."""
    snap = AppState(dataset="wb").snapshot()
    rg = snap["regen_sync"]
    assert rg["applicable"] is True
    assert rg["recovered_unsync"] == 0             # coincident -> wasted uncoordinated
    assert rg["recovered_sync"] == 3060            # coordinated capture
    assert rg["extra_recovered"] == 3060
    assert rg["pair_count"] == 1
    assert set(rg["sections"]) == {"NJP"}
    assert "v²" in rg["method"]
