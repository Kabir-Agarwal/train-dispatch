"""Gate: collision unit — the most important rule in the system, tested hardest.

Hand verification:
  T1 occupies SEG-12 during [0,10].
  TB (dep 10, same segment) occupies [10,20] -> shares exactly minute 10 -> CONFLICT.
  TC (dep 5) occupies [5,15] -> shares [5,10] -> CONFLICT.
  TD (dep 11) occupies [11,21] -> first free minute after T1 exits -> NO conflict.
"""

import pytest

from engine.collision import Conflict, find_conflicts, windows_overlap
from engine.errors import BaselineConflictError
from engine.model import Network, Segment, Train
from engine.scheduler import Occupancy, load_baseline


def network():
    return Network(
        stations=["S1", "S2", "S3"],
        segments=[
            Segment("SEG-12", ("S1", "S2"), 10),
            Segment("SEG-23", ("S2", "S3"), 8),
        ],
    )


# --- windows_overlap truth table (closed intervals, minutes) ---

def test_overlap_truth_table():
    assert windows_overlap(0, 10, 10, 20) is True   # exact boundary -> conflict
    assert windows_overlap(10, 20, 0, 10) is True   # boundary, order swapped
    assert windows_overlap(0, 10, 5, 15) is True    # partial overlap
    assert windows_overlap(0, 20, 5, 10) is True    # containment
    assert windows_overlap(3, 7, 3, 7) is True      # identical
    assert windows_overlap(0, 10, 11, 20) is False  # adjacent but disjoint
    assert windows_overlap(11, 20, 0, 10) is False  # disjoint, order swapped


# --- find_conflicts ---

def test_exact_boundary_overlap_is_flagged():
    table = [
        Occupancy("T1", "SEG-12", 0, 10),
        Occupancy("TB", "SEG-12", 10, 20),
    ]
    assert find_conflicts(table) == [Conflict("SEG-12", "T1", "TB", 10, 10)]


def test_partial_overlap_is_flagged_with_shared_window():
    table = [
        Occupancy("T1", "SEG-12", 0, 10),
        Occupancy("TC", "SEG-12", 5, 15),
    ]
    assert find_conflicts(table) == [Conflict("SEG-12", "T1", "TC", 5, 10)]


def test_one_minute_gap_is_clean():
    table = [
        Occupancy("T1", "SEG-12", 0, 10),
        Occupancy("TD", "SEG-12", 11, 21),
    ]
    assert find_conflicts(table) == []


def test_same_window_different_segments_is_clean():
    table = [
        Occupancy("T1", "SEG-12", 0, 10),
        Occupancy("T2", "SEG-23", 0, 10),
    ]
    assert find_conflicts(table) == []


def test_opposite_directions_same_segment_still_conflict():
    # Bidirectional single track: direction does not matter.
    table = [
        Occupancy("T1", "SEG-12", 0, 10),   # S1 -> S2
        Occupancy("T2", "SEG-12", 8, 18),   # S2 -> S1
    ]
    assert find_conflicts(table) == [Conflict("SEG-12", "T1", "T2", 8, 10)]


def test_three_trains_overlapping_yields_three_pairwise_conflicts():
    table = [
        Occupancy("T1", "SEG-12", 0, 10),
        Occupancy("T2", "SEG-12", 5, 15),
        Occupancy("T3", "SEG-12", 9, 19),
    ]
    assert find_conflicts(table) == [
        Conflict("SEG-12", "T1", "T2", 5, 10),
        Conflict("SEG-12", "T1", "T3", 9, 10),
        Conflict("SEG-12", "T2", "T3", 9, 15),
    ]


# --- load_baseline: flags a conflicting baseline, accepts a clean one ---

def test_load_baseline_rejects_boundary_conflict():
    trains = [
        Train("T1", "S1", "S2", ("SEG-12",), 0),    # SEG-12 [0,10]
        Train("TB", "S1", "S2", ("SEG-12",), 10),   # SEG-12 [10,20] -> boundary
    ]
    with pytest.raises(BaselineConflictError) as exc:
        load_baseline(network(), trains)
    assert exc.value.conflicts == [Conflict("SEG-12", "T1", "TB", 10, 10)]
    assert "SEG-12" in str(exc.value)


def test_load_baseline_accepts_clean_schedule():
    trains = [
        Train("T1", "S1", "S2", ("SEG-12",), 0),    # SEG-12 [0,10]
        Train("TD", "S1", "S2", ("SEG-12",), 11),   # SEG-12 [11,21] -> clean
    ]
    schedule, table = load_baseline(network(), trains)
    assert schedule == {
        "T1": {"S1": 0, "S2": 10},
        "TD": {"S1": 11, "S2": 21},
    }
    assert len(table) == 2
