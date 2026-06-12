"""Recompute engine (Phase 3): after an anomaly, produce a collision-free,
delay-minimized schedule with a clear per-train action.

Strategy (greedy, per PLAN: not a solver):
- Trains are placed one at a time in baseline-departure priority order against
  a growing occupancy table, so every placement is checked against EVERYTHING
  scheduled so far — second-order conflicts cannot survive.
- A train keeps its original path and timing if that is conflict-free as-is
  (never over-react, never churn an untouched train onto a "better" route).
- Otherwise the engine tries every open path with the smallest origin-hold
  that clears the table, and picks the earliest arrival; collision-free is a
  hard constraint of the search, so the delay-optimal-but-colliding move is
  unrepresentable. Safety beats delay by construction.
- After all trains: the WHOLE table is re-checked; any conflict is a bug and
  raises (it must never happen).
"""

from dataclasses import dataclass, replace

from .anomalies import (
    apply_anomalies,
    cancelled_train_ids,
    closed_segment_ids,
    delay_minutes,
    validate_anomalies,
)
from .collision import find_conflicts
from .routes import all_open_paths, path_stations
from .scheduler import build_schedule, compute_train_schedule

UNCHANGED = "unchanged"
DEPART_DELAYED = "depart_delayed"
HOLD = "hold"
REROUTE = "reroute"
CANCELLED = "cancelled"
STRANDED = "stranded"


def try_schedule(network, train, path, departure, table):
    """Schedule train on path at departure; return (arrivals, occs) if it does
    not conflict with the existing occupancy table, else None."""
    cand = replace(train, path=tuple(path), departure=departure)
    arrivals, occs = compute_train_schedule(network, cand)
    if find_conflicts(list(table) + occs):
        return None
    return arrivals, occs


def min_hold_schedule(network, train, path, base_departure, table):
    """Smallest hold h >= 0 such that the path is conflict-free departing at
    base_departure + h. Always exists: departing after the whole table clears
    conflicts with nothing. Returns (hold, arrivals, occs)."""
    max_h = (max((o.end for o in table), default=0) + 1) - base_departure
    for hold in range(0, max(max_h, 0) + 1):
        result = try_schedule(network, train, path, base_departure + hold, table)
        if result is not None:
            arrivals, occs = result
            return hold, arrivals, occs
    raise RuntimeError(
        f"no conflict-free slot found for train '{train.id}' — impossible"
    )


def blocking_trains(network, train, path, departure, table):
    """Who occupies this path if the train departed right now? (the 'why' for
    holds and conflict-avoidance reroutes)"""
    cand = replace(train, path=tuple(path), departure=departure)
    _, occs = compute_train_schedule(network, cand)
    conflicts = find_conflicts(list(table) + occs)
    others = set()
    for c in conflicts:
        for tid in (c.train_a, c.train_b):
            if tid != train.id:
                others.add(tid)
    return sorted(others)
