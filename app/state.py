"""Application state: ONE source of truth for both views.

The admin board and the passenger view are rendered from the SAME
RecomputeResult — they cannot disagree (and a gate proves it).
The admin is the only anomaly source; anomalies accumulate until reset.
"""

from data.baseline import build_network, build_trains
from engine.anomalies import (
    ReducedSpeed,
    TrackBlocked,
    TrackClosed,
    TrainCancelled,
    TrainDelayed,
)
from engine.decision_log import (
    build_decision_log,
    describe_anomaly,
    fact_entries_for_all_trains,
)
from engine.errors import DispatchError, ValidationError
from engine.phrasing import (
    get_phraser,
    safe_phrase_log_entry,
    safe_phrase_passenger_eta,
    safe_phrase_trigger,
)
from engine.recompute import Action, RecomputeResult, recompute_schedule
from engine.scheduler import load_baseline

_ANOMALY_TYPES = {
    "track_closed": lambda d: TrackClosed(d["segment"]),
    "track_blocked": lambda d: TrackBlocked(d["segment"]),
    "reduced_speed": lambda d: ReducedSpeed(d["segment"], float(d["factor"])),
    "train_cancelled": lambda d: TrainCancelled(d["train"]),
    "train_delayed": lambda d: TrainDelayed(d["train"], int(d["minutes"])),
}


def parse_anomaly(payload):
    """JSON dict -> anomaly object; ValidationError on bad shape."""
    kind = payload.get("type")
    if kind not in _ANOMALY_TYPES:
        raise ValidationError(f"unknown anomaly type '{kind}'")
    try:
        return _ANOMALY_TYPES[kind](payload)
    except (KeyError, TypeError, ValueError) as exc:
        raise ValidationError(f"bad parameters for {kind}: {exc}") from exc


def _baseline_result(network, trains):
    """Shape the untouched baseline like a RecomputeResult so both views
    always render from the same structure."""
    schedule, table = load_baseline(network, trains)
    actions = {}
    for t in trains:
        arrivals = schedule[t.id]
        actions[t.id] = Action(
            t.id, "unchanged", tuple(t.path), t.departure, arrivals, 0,
            f"proceeds as planned; arrives {t.destination} at minute "
            f"{arrivals[t.destination]}",
        )
    return RecomputeResult(
        actions=actions, schedule=schedule,
        occupancy_table=tuple(table), total_added_delay=0,
    )


class AppState:
    def __init__(self, phraser=None):
        self.network = build_network()
        self.trains = build_trains()
        self.phraser = phraser or get_phraser()
        self.reset()

    def reset(self):
        self.anomalies = []
        self.result = _baseline_result(self.network, self.trains)
        self.log = None
        self._facts = fact_entries_for_all_trains(
            self.network, self.trains, [], self.result
        )

    def inject(self, payloads):
        """Admin injects one or more anomalies (the ONLY anomaly source).
        On any error the previous state is kept and the error re-raised."""
        new_anomalies = self.anomalies + [parse_anomaly(p) for p in payloads]
        result = recompute_schedule(self.network, self.trains, new_anomalies)
        self.anomalies = new_anomalies
        self.result = result
        self.log = build_decision_log(
            self.network, self.trains, new_anomalies, result
        )
        self._facts = fact_entries_for_all_trains(
            self.network, self.trains, new_anomalies, result
        )

    def _effective_segments(self):
        from engine.anomalies import apply_anomalies

        eff = apply_anomalies(self.network, self.anomalies) if self.anomalies \
            else self.network
        out = []
        for seg_id in sorted(eff.segment_ids()):
            seg = eff.segment(seg_id)
            out.append({
                "id": seg.id,
                "endpoints": list(seg.endpoints),
                "travel_time": seg.travel_time,
                "status": seg.status,
                "speed_factor": seg.speed_factor,
                "effective_time": seg.effective_travel_time(),
            })
        return out

    def snapshot(self):
        """Everything the admin view shows. All numbers from the engine."""
        trains = []
        for tid in sorted(self.result.actions):
            a = self.result.actions[tid]
            trains.append({
                "id": tid,
                "action": a.action,
                "path": list(a.path) if a.path else None,
                "depart_at": a.depart_at,
                "arrivals": a.arrivals,
                "added_delay": a.added_delay,
                "reason": a.reason,
            })
        log_lines = []
        trigger_text = ""
        if self.log is not None:
            trigger_text, _ = safe_phrase_trigger(self.phraser, self.log)
            for entry in self.log.entries:
                text, violations = safe_phrase_log_entry(self.phraser, entry)
                log_lines.append({
                    "train_id": entry.train_id,
                    "change": entry.change,
                    "text": text,
                    "violations": violations,
                })
        return {
            "stations": list(self.network.stations),
            "segments": self._effective_segments(),
            "anomalies": [describe_anomaly(a) for a in self.anomalies],
            "trigger_text": trigger_text,
            "trains": trains,
            "decision_log": log_lines,
            "total_added_delay": self.result.total_added_delay,
        }

    def passenger(self, train_id):
        """Passenger view: ONLY the chosen train's ETA + a short reason.
        The minute comes from the same engine result the admin board uses."""
        if train_id not in self._facts:
            raise ValidationError(f"train '{train_id}' does not exist")
        entry = self._facts[train_id]
        text, violations = safe_phrase_passenger_eta(self.phraser, entry)
        return {
            "train_id": train_id,
            "eta": entry.arrival,  # engine value, None if cancelled/stranded
            "status": entry.change,
            "text": text,
            "violations": violations,
        }
