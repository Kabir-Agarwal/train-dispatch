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


@dataclass(frozen=True)
class Action:
    train_id: str
    action: str  # unchanged | depart_delayed | hold | reroute | cancelled | stranded
    path: tuple | None  # the path the train will run (None if it cannot run)
    depart_at: int | None  # actual departure minute (None if it cannot run)
    arrivals: dict | None  # {station: minute} (None if it cannot run)
    added_delay: int | None  # destination arrival minus baseline (None if no run)
    reason: str


@dataclass(frozen=True)
class RecomputeResult:
    actions: dict  # train_id -> Action
    schedule: dict  # train_id -> arrivals (running trains only)
    occupancy_table: tuple
    total_added_delay: int  # net, summed over running trains


def _choose(network, train, base_dep, candidates, table):
    """Best (path, hold, arrivals, occs) by earliest arrival; ties prefer the
    original path, then less hold, then path ids (deterministic)."""
    best = None
    for path in candidates:
        hold, arrivals, occs = min_hold_schedule(network, train, path, base_dep, table)
        key = (arrivals[train.destination], path != train.path, hold, path)
        if best is None or key < best[0]:
            best = (key, path, hold, arrivals, occs)
    _, path, hold, arrivals, occs = best
    return path, hold, arrivals, occs


def recompute_schedule(network, trains, anomalies):
    """Produce a collision-free, delay-minimized schedule after anomalies.
    Every number in every reason string originates here, in the engine."""
    validate_anomalies(network, trains, anomalies)
    effective = apply_anomalies(network, anomalies)
    closed = closed_segment_ids(anomalies)
    cancelled = cancelled_train_ids(anomalies)
    delays = delay_minutes(anomalies)
    baseline_schedule, _ = build_schedule(network, trains)

    actions = {}
    schedule = {}
    table = []
    for train in sorted(trains, key=lambda t: (t.departure, t.id)):
        if train.id in cancelled:
            actions[train.id] = Action(
                train.id, CANCELLED, None, None, None, None,
                f"{train.id} cancelled by admin",
            )
            continue
        admin_delay = delays.get(train.id, 0)
        base_dep = train.departure + admin_delay
        candidates = all_open_paths(effective, train.origin, train.destination)
        if not candidates:
            actions[train.id] = Action(
                train.id, STRANDED, None, None, None, None,
                f"no remaining route from {train.origin} to {train.destination}; "
                f"cannot complete",
            )
            continue

        original_open = not any(s in closed for s in train.path)
        chosen = None
        if original_open:
            as_planned = try_schedule(effective, train, train.path, base_dep, table)
            if as_planned is not None:
                arrivals, occs = as_planned
                chosen = (tuple(train.path), 0, arrivals, occs)
        if chosen is None:
            chosen = _choose(effective, train, base_dep, candidates, table)
        path, hold, arrivals, occs = chosen

        table.extend(occs)
        schedule[train.id] = arrivals
        dest = train.destination
        added = arrivals[dest] - baseline_schedule[train.id][dest]
        depart_at = base_dep + hold
        actions[train.id] = _describe(
            network, effective, train, path, depart_at, arrivals, added,
            admin_delay, hold, closed, table,
        )

    conflicts = find_conflicts(table)
    if conflicts:  # must be unreachable: every placement was checked
        raise RuntimeError(f"recompute produced conflicts: {conflicts}")
    total = sum(a.added_delay for a in actions.values() if a.added_delay is not None)
    return RecomputeResult(
        actions=actions,
        schedule=schedule,
        occupancy_table=tuple(table),
        total_added_delay=total,
    )


def _describe(network, effective, train, path, depart_at, arrivals, added,
              admin_delay, hold, closed, table):
    """Build the per-train Action with an engine-sourced reason."""
    dest = train.destination
    arr = arrivals[dest]
    if path != tuple(train.path):
        via = "-".join(path_stations(effective, train.origin, path))
        closed_used = [s for s in train.path if s in closed]
        if closed_used:
            why = f"planned path uses closed segment(s) {', '.join(closed_used)}"
        else:
            others = blocking_trains(
                effective, train, train.path, train.departure + admin_delay,
                [o for o in table if o.train_id != train.id],
            )
            why = f"avoids conflict with {', '.join(others)} on the planned path"
        extra = f", departing minute {depart_at}" if hold else ""
        return Action(
            train.id, REROUTE, path, depart_at, arrivals, added,
            f"rerouted via {via}{extra} because {why}; "
            f"arrives {dest} at minute {arr} ({added:+d} min)",
        )
    if hold:
        others = blocking_trains(
            effective, train, path, depart_at - hold,
            [o for o in table if o.train_id != train.id],
        )
        return Action(
            train.id, HOLD, path, depart_at, arrivals, added,
            f"held at {train.origin} until minute {depart_at} so "
            f"{', '.join(others)} clear(s) the line; "
            f"arrives {dest} at minute {arr} ({added:+d} min)",
        )
    if admin_delay:
        return Action(
            train.id, DEPART_DELAYED, path, depart_at, arrivals, added,
            f"departs {admin_delay} min late (admin-injected delay); "
            f"arrives {dest} at minute {arr} ({added:+d} min)",
        )
    if added:
        return Action(
            train.id, UNCHANGED, path, depart_at, arrivals, added,
            f"same path and departure; reduced speed adds {added} min "
            f"(arrives {dest} at minute {arr})",
        )
    return Action(
        train.id, UNCHANGED, path, depart_at, arrivals, 0,
        f"proceeds as planned; arrives {dest} at minute {arr}",
    )
