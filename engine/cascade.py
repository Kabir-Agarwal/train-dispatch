"""Phase G — delay cascade prediction.

Given a PRIMARY delay on one train, forward-simulate how it propagates through the
network and report the "blast radius": which downstream trains inherit delay (via
shared single-track segments + the engine's collision-free sequencing) and by how
many minutes.

Method — FORWARD RE-SIMULATION DIFF: run the engine's deterministic, greedy,
collision-free deconfliction (`recompute_schedule`, which places trains forward in
time against a growing occupancy table) TWICE — once WITHOUT the primary delay (the
reference) and once WITH it — and report each train's destination-arrival shift.
Because the delay only propagates through shared-segment sequencing, the per-train
diff IS the true knock-on. This module is ADDITIVE: it calls recompute_schedule but
never changes it, so the byte-identical recompute golden is unaffected.
"""

from .anomalies import TrainDelayed
from .recompute import recompute_schedule


def _dest_arrivals(network, trains, anomalies):
    dest = {t.id: t.destination for t in trains}
    res = recompute_schedule(network, trains, anomalies)
    return {tid: (a.arrivals[dest[tid]] if a.arrivals else None)
            for tid, a in res.actions.items()}


def delay_cascade(network, trains, base_anomalies, train_id, minutes):
    """Blast radius of delaying `train_id` by `minutes`, on top of any
    `base_anomalies` already in effect. Returns {"applicable": False} for an
    unknown train or a non-positive delay."""
    if train_id not in {t.id for t in trains} or minutes <= 0:
        return {"applicable": False}

    base = _dest_arrivals(network, trains, list(base_anomalies))
    delayed = _dest_arrivals(
        network, trains, list(base_anomalies) + [TrainDelayed(train_id, minutes)]
    )

    def delta(tid):
        b, d = base.get(tid), delayed.get(tid)
        return None if b is None or d is None else d - b

    primary_delay = delta(train_id)
    downstream = []
    for t in trains:
        if t.id == train_id:
            continue
        d = delta(t.id)
        if d and d > 0:
            downstream.append({"id": t.id, "minutes": d})
    downstream.sort(key=lambda x: (-x["minutes"], x["id"]))

    return {
        "applicable": True,
        "train": train_id,
        "minutes": minutes,
        "primary_delay": primary_delay,
        "downstream": downstream,
        "trains_affected": len(downstream),
        "total_knock_on": sum(x["minutes"] for x in downstream),
        "method": "forward re-simulation diff (collision-free deconfliction, "
                  "with vs without the delay)",
    }
