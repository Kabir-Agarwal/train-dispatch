"""Impact detection: who is affected by injected anomalies, and how.

Phase 2 ONLY detects and classifies impact. It does NOT reroute, hold, or
resolve conflicts — that is Phase 3.
"""

from collections import deque
from dataclasses import dataclass, replace

from .anomalies import (
    apply_anomalies,
    cancelled_train_ids,
    closed_segment_ids,
    delay_minutes,
    reduced_segments,
    validate_anomalies,
)
from .collision import find_conflicts
from .model import CLOSED
from .scheduler import compute_train_schedule

UNAFFECTED = "unaffected"
TIMES_SHIFTED = "times_shifted"
NEEDS_REROUTE = "needs_reroute"
STRANDED = "stranded"
CANCELLED = "cancelled"


def destination_reachable(network, origin, destination):
    """BFS over OPEN (non-closed) segments. Always terminates: each station
    is visited at most once."""
    if origin == destination:
        return True
    seen = {origin}
    queue = deque([origin])
    while queue:
        station = queue.popleft()
        for seg_id in network.segment_ids():
            seg = network.segment(seg_id)
            if seg.status == CLOSED or station not in seg.endpoints:
                continue
            nxt = seg.endpoints[0] if seg.endpoints[1] == station else seg.endpoints[1]
            if nxt == destination:
                return True
            if nxt not in seen:
                seen.add(nxt)
                queue.append(nxt)
    return False


@dataclass(frozen=True)
class TrainImpact:
    train_id: str
    status: str  # one of the constants above
    reason: str  # human-readable, every number comes from the engine
    new_arrivals: dict | None  # {station: minute}; None when train cannot run


@dataclass(frozen=True)
class ImpactReport:
    impacts: dict  # train_id -> TrainImpact
    conflicts: tuple  # Conflicts among still-running trains (Phase 3 resolves)
    no_impact: bool  # True iff nothing changed for anyone


def assess_impact(network, trains, anomalies):
    """Classify every train under the injected anomalies. Detection only."""
    validate_anomalies(network, trains, anomalies)
    effective = apply_anomalies(network, anomalies)
    closed = closed_segment_ids(anomalies)
    reduced = reduced_segments(anomalies)
    cancelled = cancelled_train_ids(anomalies)
    delays = delay_minutes(anomalies)

    impacts = {}
    occupancy = []
    for train in trains:
        if train.id in cancelled:
            impacts[train.id] = TrainImpact(
                train.id, CANCELLED, f"{train.id} cancelled by admin", None
            )
            continue
        blocked = [s for s in train.path if s in closed]
        if blocked:
            if destination_reachable(effective, train.origin, train.destination):
                impacts[train.id] = TrainImpact(
                    train.id,
                    NEEDS_REROUTE,
                    f"path uses closed segment(s) {', '.join(blocked)}; "
                    f"an alternative route to {train.destination} exists",
                    None,
                )
            else:
                impacts[train.id] = TrainImpact(
                    train.id,
                    STRANDED,
                    f"no remaining route from {train.origin} to "
                    f"{train.destination}; cannot complete",
                    None,
                )
            continue
        delay = delays.get(train.id, 0)
        slowed = sorted(set(train.path) & set(reduced))
        baseline_arrivals, _ = compute_train_schedule(network, train)
        arrivals, occs = compute_train_schedule(
            effective, replace(train, departure=train.departure + delay)
        )
        occupancy.extend(occs)
        if delay == 0 and not slowed:
            impacts[train.id] = TrainImpact(
                train.id, UNAFFECTED, "no change", arrivals
            )
            continue
        dest = train.destination
        added = arrivals[dest] - baseline_arrivals[dest]
        causes = []
        if delay:
            causes.append(f"departure delayed {delay} min")
        if slowed:
            causes.append(f"reduced speed on {', '.join(slowed)}")
        impacts[train.id] = TrainImpact(
            train.id,
            TIMES_SHIFTED,
            f"{'; '.join(causes)}; arrives {dest} at minute {arrivals[dest]} "
            f"(+{added} min vs baseline)",
            arrivals,
        )

    conflicts = tuple(find_conflicts(occupancy))
    no_impact = (
        all(i.status == UNAFFECTED for i in impacts.values()) and not conflicts
    )
    return ImpactReport(impacts=impacts, conflicts=conflicts, no_impact=no_impact)
