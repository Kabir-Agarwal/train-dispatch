"""Gate: slot unit. Hand-verified minimal holds, boundary respected.

Setup mirrors the T2-delayed-2 scenario: T2 occupies SEG-56 [22,31].
T4's baseline: SEG-45[23,30] SEG-56[30,39].
  hold 0 -> SEG-56[30,39] overlaps [22,31] during [30,31]  -> conflict
  hold 1 -> SEG-56[31,40] shares exactly minute 31         -> conflict (boundary!)
  hold 2 -> SEG-56[32,41]                                  -> clean
"""

from data.baseline import build_network
from engine.model import Train
from engine.recompute import blocking_trains, min_hold_schedule, try_schedule
from engine.scheduler import Occupancy

T4 = Train("T4", "S4", "S6", ("SEG-45", "SEG-56"), 23)
TABLE = [Occupancy("T2", "SEG-56", 22, 31)]


def test_min_hold_is_two_not_one_boundary_counts():
    hold, arrivals, occs = min_hold_schedule(build_network(), T4, T4.path, 23, TABLE)
    assert hold == 2
    assert arrivals == {"S4": 25, "S5": 32, "S6": 41}
    assert [(o.segment_id, o.start, o.end) for o in occs] == [
        ("SEG-45", 25, 32),
        ("SEG-56", 32, 41),
    ]


def test_try_schedule_rejects_boundary_and_accepts_clear():
    net = build_network()
    assert try_schedule(net, T4, T4.path, 24, TABLE) is None  # SEG-56[31,40] touches 31
    assert try_schedule(net, T4, T4.path, 25, TABLE) is not None


def test_zero_hold_when_table_is_empty():
    hold, arrivals, _ = min_hold_schedule(build_network(), T4, T4.path, 23, [])
    assert hold == 0
    assert arrivals == {"S4": 23, "S5": 30, "S6": 39}


def test_blocking_trains_names_the_obstacle():
    assert blocking_trains(build_network(), T4, T4.path, 23, TABLE) == ["T2"]
    assert blocking_trains(build_network(), T4, T4.path, 25, TABLE) == []
