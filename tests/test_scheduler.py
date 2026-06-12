"""Gate: scheduler unit. Hand-verified arrival times and occupancy windows.

Hand verification for T1 (dep 0, S1->S4 via SEG-12[10] SEG-23[8] SEG-34[12]):
  S1@0, S2@0+10=10, S3@10+8=18, S4@18+12=30.
For T5 (dep 40, S4->S1, reverse direction over the same segments):
  S4@40, S3@40+12=52, S2@52+8=60, S1@60+10=70.
"""

import pytest

from engine.errors import ValidationError
from engine.model import Network, Segment, Train
from engine.scheduler import Occupancy, build_schedule, compute_train_schedule


def network():
    return Network(
        stations=["S1", "S2", "S3", "S4"],
        segments=[
            Segment("SEG-12", ("S1", "S2"), 10),
            Segment("SEG-23", ("S2", "S3"), 8),
            Segment("SEG-34", ("S3", "S4"), 12),
        ],
    )


def test_arrival_times_hand_verified():
    train = Train("T1", "S1", "S4", ("SEG-12", "SEG-23", "SEG-34"), 0)
    arrivals, _ = compute_train_schedule(network(), train)
    assert arrivals == {"S1": 0, "S2": 10, "S3": 18, "S4": 30}


def test_arrival_times_with_nonzero_departure():
    train = Train("T1", "S1", "S4", ("SEG-12", "SEG-23", "SEG-34"), 7)
    arrivals, _ = compute_train_schedule(network(), train)
    assert arrivals == {"S1": 7, "S2": 17, "S3": 25, "S4": 37}


def test_occupancy_windows_hand_verified():
    train = Train("T1", "S1", "S4", ("SEG-12", "SEG-23", "SEG-34"), 0)
    _, occs = compute_train_schedule(network(), train)
    assert occs == [
        Occupancy("T1", "SEG-12", 0, 10),
        Occupancy("T1", "SEG-23", 10, 18),
        Occupancy("T1", "SEG-34", 18, 30),
    ]


def test_reverse_direction_hand_verified():
    train = Train("T5", "S4", "S1", ("SEG-34", "SEG-23", "SEG-12"), 40)
    arrivals, occs = compute_train_schedule(network(), train)
    assert arrivals == {"S4": 40, "S3": 52, "S2": 60, "S1": 70}
    assert occs == [
        Occupancy("T5", "SEG-34", 40, 52),
        Occupancy("T5", "SEG-23", 52, 60),
        Occupancy("T5", "SEG-12", 60, 70),
    ]


def test_build_schedule_two_trains():
    trains = [
        Train("T1", "S1", "S4", ("SEG-12", "SEG-23", "SEG-34"), 0),
        Train("T5", "S4", "S1", ("SEG-34", "SEG-23", "SEG-12"), 40),
    ]
    schedule, table = build_schedule(network(), trains)
    assert schedule["T1"]["S4"] == 30
    assert schedule["T5"]["S1"] == 70
    assert len(table) == 6  # 3 segments per train, 2 trains


def test_duplicate_train_ids_rejected():
    trains = [
        Train("T1", "S1", "S2", ("SEG-12",), 0),
        Train("T1", "S2", "S3", ("SEG-23",), 50),
    ]
    with pytest.raises(ValidationError, match="duplicate train ids"):
        build_schedule(network(), trains)
