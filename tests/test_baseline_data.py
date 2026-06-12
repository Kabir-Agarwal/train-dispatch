"""Gate: data unit — the full Phase 1 end-to-end load.

All expected values below are hand-verified in data/baseline.py's docstring.
"""

import pytest

from data.baseline import build_network, build_trains, conflicting_trains
from engine.collision import Conflict, find_conflicts
from engine.errors import BaselineConflictError
from engine.scheduler import Occupancy, build_schedule, load_baseline


def test_network_shape():
    net = build_network()
    assert net.stations == ["S1", "S2", "S3", "S4", "S5", "S6"]
    assert sorted(net.segment_ids()) == [
        "SEG-12", "SEG-15", "SEG-23", "SEG-26", "SEG-34", "SEG-36", "SEG-45", "SEG-56",
    ]
    assert net.segment("SEG-34").travel_time == 12
    assert 4 <= len(build_trains()) <= 6


def test_clean_baseline_loads_with_zero_conflicts():
    schedule, table = load_baseline(build_network(), build_trains())
    assert find_conflicts(table) == []
    assert len(table) == 11  # 3+2+1+2+3 segment occupations


def test_all_arrivals_hand_verified():
    schedule, _ = load_baseline(build_network(), build_trains())
    assert schedule == {
        "T1": {"S1": 0, "S2": 10, "S3": 18, "S4": 30},
        "T2": {"S1": 5, "S5": 20, "S6": 29},
        "T3": {"S2": 12, "S6": 32},
        "T4": {"S4": 23, "S5": 30, "S6": 39},
        "T5": {"S4": 40, "S3": 52, "S2": 60, "S1": 70},
    }


def test_occupancy_table_hand_verified():
    _, table = load_baseline(build_network(), build_trains())
    assert set(table) == {
        Occupancy("T1", "SEG-12", 0, 10),
        Occupancy("T1", "SEG-23", 10, 18),
        Occupancy("T1", "SEG-34", 18, 30),
        Occupancy("T2", "SEG-15", 5, 20),
        Occupancy("T2", "SEG-56", 20, 29),
        Occupancy("T3", "SEG-26", 12, 32),
        Occupancy("T4", "SEG-45", 23, 30),
        Occupancy("T4", "SEG-56", 30, 39),
        Occupancy("T5", "SEG-34", 40, 52),
        Occupancy("T5", "SEG-23", 52, 60),
        Occupancy("T5", "SEG-12", 60, 70),
    }


def test_tightest_clean_gap_is_one_minute_on_seg56():
    # T2 exits SEG-56 at 29, T4 enters at 30 — clean, and proves the checker
    # is not over-flagging near-misses.
    _, table = load_baseline(build_network(), build_trains())
    seg56 = sorted(
        [o for o in table if o.segment_id == "SEG-56"], key=lambda o: o.start
    )
    assert [(o.train_id, o.start, o.end) for o in seg56] == [
        ("T2", 20, 29),
        ("T4", 30, 39),
    ]


def test_conflicting_baseline_is_flagged_at_load():
    with pytest.raises(BaselineConflictError) as exc:
        load_baseline(build_network(), conflicting_trains())
    # T4 dep 22 -> SEG-56[29,38]; T2 -> SEG-56[20,29]; shared minute = 29.
    assert exc.value.conflicts == [Conflict("SEG-56", "T2", "T4", 29, 29)]


def test_conflicting_baseline_schedule_still_computable_for_reporting():
    # build_schedule (no safety gate) computes; the conflict is then findable.
    schedule, table = build_schedule(build_network(), conflicting_trains())
    assert schedule["T4"] == {"S4": 22, "S5": 29, "S6": 38}
    assert find_conflicts(table) == [Conflict("SEG-56", "T2", "T4", 29, 29)]
