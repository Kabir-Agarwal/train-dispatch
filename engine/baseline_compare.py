"""Phase B — naive-baseline comparison.

Quantifies the reroute engine's value against a NAIVE hold-all dispatcher that
does not reroute: when a track is closed it simply holds the trains whose booked
path uses that track until the line reopens, then runs them on their original
route. Both policies are kept collision-free by the SAME engine, so the only
difference measured is reroute-vs-wait — the comparison is apples-to-apples, not
a strawman that ignores conflicts.

HONESTY / assumptions (surfaced in the UI):
- A closed track has no scheduled reopen in this model, so the naive policy needs
  an assumed clearance time: NAIVE_CLEARANCE_MIN. The reported reduction grows
  with longer blockages and shrinks with shorter ones; we state the assumption.
- "Passenger-delay-minutes" weights each train's lateness by its coach count
  (LOAD_WEIGHTS) as an ILLUSTRATIVE load proxy — not real booking data.

This module is ADDITIVE: it calls recompute_schedule but never changes it, so the
byte-identical recompute golden is unaffected.
"""

import dataclasses

from .anomalies import (
    MaintenanceClosure,
    TrackBlocked,
    TrackClosed,
    closed_segment_ids,
)
from .recompute import recompute_schedule
from .scheduler import compute_train_schedule

# Assumed minutes until a fully-closed track reopens, for the naive hold-all
# baseline only. A serious blockage (e.g. a few hours) is the realistic case for
# a "track closed" event; the reroute advantage is larger for longer closures.
NAIVE_CLEARANCE_MIN = 180

_CLOSURE_TYPES = (TrackClosed, TrackBlocked, MaintenanceClosure)


def _total_passenger_delay(result, base_arrival, dest, load_weights):
    """Sum over trains of max(0, lateness) * coaches, lateness vs the no-anomaly
    nominal arrival. Trains the policy fails to run (no arrivals) are skipped."""
    total = 0
    for tid, action in result.actions.items():
        if not action.arrivals:
            continue
        late = max(0, action.arrivals[dest[tid]] - base_arrival[tid])
        total += late * load_weights.get(tid, 1)
    return total


def compare_dispatch(network, trains, anomalies,
                     clearance_min=NAIVE_CLEARANCE_MIN, load_weights=None):
    """Compare naive hold-all vs the reroute engine for the active closure(s).

    Returns a dict. When no track is closed (or no train is blocked by it) the
    comparison does not apply: {"applicable": False}.
    """
    load_weights = load_weights or {}
    closed = closed_segment_ids(anomalies)
    affected = [t for t in trains if closed & set(t.path)]
    if not closed or not affected:
        return {"applicable": False}

    dest = {t.id: t.destination for t in trains}
    base_arrival = {}
    for t in trains:
        arr, _ = compute_train_schedule(network, t)
        base_arrival[t.id] = arr[t.destination]

    # (b) reroute engine: the real managed schedule under the closure.
    smart = recompute_schedule(network, trains, anomalies)
    smart_delay = _total_passenger_delay(smart, base_arrival, dest, load_weights)

    # (a) naive hold-all: the closure is assumed to clear at clearance_min; the
    # blocked trains are held until then and run their ORIGINAL route (no
    # rerouting), everyone deconflicted by the same engine. Non-closure anomalies
    # (delays, speed limits) are kept so only the closure handling differs.
    keep = [a for a in anomalies if not isinstance(a, _CLOSURE_TYPES)]
    affected_ids = {t.id for t in affected}
    naive_trains = [
        dataclasses.replace(t, departure=max(t.departure, clearance_min))
        if t.id in affected_ids else t
        for t in trains
    ]
    naive = recompute_schedule(network, naive_trains, keep)
    naive_delay = _total_passenger_delay(naive, base_arrival, dest, load_weights)

    reduction = (round((naive_delay - smart_delay) / naive_delay * 100)
                 if naive_delay > 0 else 0)
    return {
        "applicable": True,
        "naive_delay": naive_delay,
        "smart_delay": smart_delay,
        "reduction_pct": reduction,
        "affected_ids": sorted(affected_ids),
        "clearance_min": clearance_min,
        "metric": "passenger-delay-minutes (coaches × minutes late; illustrative load)",
    }
