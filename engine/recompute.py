"""Recompute engine (Phase 3): after an anomaly, produce a collision-free,
greedily delay-minimized (not proven-optimal) schedule with a clear per-train action.

Strategy (greedy, per PLAN: not a solver):
- Trains are placed one at a time in (priority, baseline-departure) order against
  a growing occupancy table, so every placement is checked against EVERYTHING
  scheduled so far — second-order conflicts cannot survive. Higher-priority trains
  are placed first and so claim contended slots; lower-priority trains wait.
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
    restricted_segments,
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


def index_table(table):
    """Index the committed occupancy table by segment:
    segment_id -> [(start, end, train_id), ...]. Built ONCE per train placement
    so a candidate is tested only against the segments it actually uses, instead
    of re-scanning (and re-pairing) the whole table on every probe."""
    idx = {}
    for o in table:
        idx.setdefault(o.segment_id, []).append((o.start, o.end, o.train_id))
    return idx


def _as_index(table_or_index):
    """Accept either a prebuilt index (dict, what recompute passes once per
    placement) or a raw occupancy table (list, what direct callers/tests pass)."""
    return table_or_index if isinstance(table_or_index, dict) \
        else index_table(table_or_index)


def _occs_conflict(idx, occs, self_id):
    """True iff some candidate occupancy overlaps a committed occupancy of a
    DIFFERENT train on the same segment. This is exactly a non-empty
    find_conflicts(table + occs): the committed table is already conflict-free,
    and a simple path's occupancies are on distinct segments, so the only
    conflicts find_conflicts could ever report are these candidate-vs-committed
    cross pairs. (Inclusive overlap, matching collision.windows_overlap.)"""
    for o in occs:
        for cs, ce, tid in idx.get(o.segment_id, ()):
            if tid != self_id and o.start <= ce and cs <= o.end:
                return True
    return False


def _occs_blockers(idx, occs, self_id):
    """The other trains whose committed occupancies overlap these — the same set
    find_conflicts would surface, used for the 'why' text."""
    others = set()
    for o in occs:
        for cs, ce, tid in idx.get(o.segment_id, ()):
            if tid != self_id and o.start <= ce and cs <= o.end:
                others.add(tid)
    return sorted(others)


def try_schedule(network, train, path, departure, table_or_index):
    """Schedule train on path at departure; return (arrivals, occs) if it does
    not conflict with the occupancy table (raw list or prebuilt index), else
    None."""
    idx = _as_index(table_or_index)
    cand = replace(train, path=tuple(path), departure=departure)
    arrivals, occs = compute_train_schedule(network, cand)
    if _occs_conflict(idx, occs, train.id):
        return None
    return arrivals, occs


def min_hold_schedule(network, train, path, base_departure, idx):
    """Smallest hold h >= 0 such that the path is conflict-free departing at
    base_departure + h. Computed analytically rather than by a minute-by-minute
    scan: a committed occupancy [cs, ce] on a segment this train would occupy at
    [e, x] (at base_departure) forbids exactly the holds h with e+h <= ce and
    cs <= x+h, i.e. the closed interval [cs - x, ce - e]. The answer is the
    smallest h >= 0 in NO forbidden interval. This returns the identical minimal
    hold the old upward scan returned (a feasible hold always exists — departing
    after the whole table clears conflicts with nothing). Returns
    (hold, arrivals, occs)."""
    idx = _as_index(idx)
    cand0 = replace(train, path=tuple(path), departure=base_departure)
    arrivals0, occs0 = compute_train_schedule(network, cand0)
    forbidden = []
    for o in occs0:
        for cs, ce, tid in idx.get(o.segment_id, ()):
            if tid == train.id:
                continue
            hi = ce - o.start          # ce - e
            if hi >= 0:                # only holds h >= 0 matter
                forbidden.append((max(cs - o.end, 0), hi))   # [cs - x, ce - e]
    hold = 0
    for lo, hi in sorted(forbidden):
        if lo > hold:
            break                      # gap at `hold`: clears every earlier interval
        if hi >= hold:
            hold = hi + 1              # interval covers `hold`; jump just past it
    if hold == 0:
        return 0, arrivals0, occs0
    cand = replace(train, path=tuple(path), departure=base_departure + hold)
    arrivals, occs = compute_train_schedule(network, cand)
    return hold, arrivals, occs


def blocking_trains(network, train, path, departure, idx):
    """Who occupies this path if the train departed at `departure`? (the 'why'
    for holds and conflict-avoidance reroutes)"""
    idx = _as_index(idx)
    cand = replace(train, path=tuple(path), departure=departure)
    _, occs = compute_train_schedule(network, cand)
    return _occs_blockers(idx, occs, train.id)


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


def _choose(network, train, base_dep, candidates, idx):
    """Best (path, hold, arrivals, occs) by earliest arrival; ties prefer the
    original path, then less hold, then path ids (deterministic)."""
    best = None
    for path in candidates:
        hold, arrivals, occs = min_hold_schedule(network, train, path, base_dep, idx)
        key = (arrivals[train.destination], path != train.path, hold, path)
        if best is None or key < best[0]:
            best = (key, path, hold, arrivals, occs)
    _, path, hold, arrivals, occs = best
    return path, hold, arrivals, occs


def recompute_schedule(network, trains, anomalies):
    """Produce a collision-free, delay-minimized schedule after anomalies.
    Every number in every reason string originates here, in the engine.

    `anomalies` may be empty: that path re-plans the given train set against an
    untouched network (used when a train is added live with no active anomaly).
    The empty case is the ONLY one that skips validate_anomalies, which by
    contract rejects an empty list elsewhere."""
    if anomalies:
        validate_anomalies(network, trains, anomalies)
    effective = apply_anomalies(network, anomalies)
    closed = closed_segment_ids(anomalies)
    cancelled = cancelled_train_ids(anomalies)
    delays = delay_minutes(anomalies)
    restricted = restricted_segments(anomalies)
    baseline_schedule, _ = build_schedule(network, trains)

    actions = {}
    schedule = {}
    table = []
    # Placement order = priority first (higher precedence claims contended slots),
    # then the original (departure, id) tie-break. With all trains at the default
    # priority this is identical to the old ordering, so the recompute golden is
    # unchanged; differing priorities favour the higher-priority train.
    for train in sorted(trains, key=lambda t: (-t.priority, t.departure, t.id)):
        if train.id in cancelled:
            actions[train.id] = Action(
                train.id, CANCELLED, None, None, None, None,
                f"{train.id} cancelled by admin",
            )
            continue
        admin_delay = delays.get(train.id, 0)
        base_dep = train.departure + admin_delay
        forbidden = restricted.get(train.id, frozenset())
        candidates = all_open_paths(
            effective, train.origin, train.destination, forbidden
        )
        if not candidates:
            barred = [s for s in train.path if s in forbidden]
            note = f" (barred from {', '.join(barred)})" if barred else ""
            actions[train.id] = Action(
                train.id, STRANDED, None, None, None, None,
                f"no remaining route from {train.origin} to {train.destination}"
                f"{note}; cannot complete",
            )
            continue

        original_open = (not any(s in closed for s in train.path)
                         and not any(s in forbidden for s in train.path))
        # Index the committed table ONCE for this train: the as-planned probe,
        # every candidate's min-hold, and the blocking-train 'why' all test
        # against it (built pre-extend, so it holds only OTHER trains' windows).
        idx = index_table(table)
        chosen = None
        if original_open:
            as_planned = try_schedule(effective, train, train.path, base_dep, idx)
            if as_planned is not None:
                arrivals, occs = as_planned
                chosen = (tuple(train.path), 0, arrivals, occs)
        if chosen is None:
            chosen = _choose(effective, train, base_dep, candidates, idx)
        path, hold, arrivals, occs = chosen

        table.extend(occs)
        schedule[train.id] = arrivals
        dest = train.destination
        added = arrivals[dest] - baseline_schedule[train.id][dest]
        depart_at = base_dep + hold
        actions[train.id] = _describe(
            network, effective, train, path, depart_at, arrivals, added,
            admin_delay, hold, closed, forbidden, idx,
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
              admin_delay, hold, closed, forbidden, idx):
    """Build the per-train Action with an engine-sourced reason. `idx` is the
    pre-extend committed index (other trains only), so blocking_trains sees the
    same windows the old `[o for o in table if o.train_id != train.id]` did."""
    dest = train.destination
    arr = arrivals[dest]
    if path != tuple(train.path):
        via = "-".join(path_stations(effective, train.origin, path))
        closed_used = [s for s in train.path if s in closed]
        restricted_used = [s for s in train.path if s in forbidden]
        if closed_used:
            why = f"planned path uses closed segment(s) {', '.join(closed_used)}"
        elif restricted_used:
            why = (f"this train is barred from segment(s) "
                   f"{', '.join(restricted_used)}")
        else:
            others = blocking_trains(
                effective, train, train.path, train.departure + admin_delay, idx,
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
            effective, train, path, depart_at - hold, idx,
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
