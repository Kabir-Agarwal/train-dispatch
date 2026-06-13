"""Application state: ONE source of truth for both views.

The admin board and the passenger view are rendered from the SAME
RecomputeResult — they cannot disagree (and a gate proves it).
The admin is the only anomaly source; anomalies accumulate until reset.
"""

import data.baseline
import data.real_corridor
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

from .display import DISPLAY_NAMES, safe_summary
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


def _train_view(a):
    """One train as both views' JSON shape; station_times is the ordered
    (station, minute) walk the map animates along."""
    return {
        "id": a.train_id,
        "action": a.action,
        "path": list(a.path) if a.path else None,
        "depart_at": a.depart_at,
        "arrivals": a.arrivals,
        "added_delay": a.added_delay,
        "reason": a.reason,
        "station_times": (
            [[st, m] for st, m in a.arrivals.items()] if a.arrivals else None
        ),
    }


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
    def __init__(self, phraser=None, dataset="baseline"):
        if dataset == "real":
            module = data.real_corridor
            self.display_names = dict(module.DISPLAY_NAMES)
            self.train_attrs = {k: dict(v) for k, v in module.TRAIN_ATTRS.items()}
        elif dataset == "baseline":
            module = data.baseline
            self.display_names = dict(DISPLAY_NAMES)
            self.train_attrs = {}
        else:
            from engine.errors import ValidationError
            raise ValidationError(f"unknown dataset '{dataset}'")
        self.dataset = dataset
        self.network = module.build_network()
        self.trains = module.build_trains()
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
        new_anomalies = list(self.anomalies)
        for p in payloads:
            anomaly = parse_anomaly(p)
            if anomaly not in new_anomalies:  # dedupe repeated injections
                new_anomalies.append(anomaly)
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
            trains.append(_train_view(a))
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
            "display_names": dict(self.display_names),
            "train_attrs": {k: dict(v) for k, v in self.train_attrs.items()},
            "summary_text": safe_summary(self.result.actions)
            if self.anomalies else "",
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


    def preview(self, payloads):
        """GHOST PREVIEW: what WOULD happen if these anomalies were injected
        on top of the active ones. Runs the SAME engine recompute as inject()
        but mutates nothing. Returns predicted segments/trains/log + a delta
        table against the current state."""
        candidate = list(self.anomalies)
        for p in payloads:
            anomaly = parse_anomaly(p)
            if anomaly not in candidate:
                candidate.append(anomaly)
        result = recompute_schedule(self.network, self.trains, candidate)
        log = build_decision_log(self.network, self.trains, candidate, result)
        current = self.result
        deltas = []
        seg_changes = {}
        from engine.anomalies import apply_anomalies as _apply
        eff = _apply(self.network, candidate)
        cur_eff = _apply(self.network, self.anomalies) if self.anomalies \
            else self.network
        for seg_id in sorted(eff.segment_ids()):
            new_seg = eff.segment(seg_id)
            if new_seg.status != cur_eff.segment(seg_id).status:
                seg_changes[seg_id] = new_seg.status
        for tid in sorted(result.actions):
            new = result.actions[tid]
            old = current.actions[tid]
            old_arr = None if old.arrivals is None \
                else old.arrivals[ [t for t in self.trains if t.id == tid][0].destination ]
            new_arr = None if new.arrivals is None \
                else new.arrivals[ [t for t in self.trains if t.id == tid][0].destination ]
            changed = (new.action != old.action or new.path != old.path
                       or new.arrivals != old.arrivals)
            deltas.append({
                "id": tid,
                "old_action": old.action,
                "new_action": new.action,
                "old_arrival": old_arr,
                "new_arrival": new_arr,
                "delay_change": (
                    None if old_arr is None or new_arr is None
                    else new_arr - old_arr
                ),
                "changed": changed,
            })
        return {
            "preview": True,
            "anomalies": [describe_anomaly(a) for a in candidate],
            "segment_changes": seg_changes,
            "trains": [_train_view(result.actions[tid])
                       for tid in sorted(result.actions)],
            "deltas": deltas,
            "decision_log": [
                {"train_id": e.train_id, "change": e.change,
                 "text": safe_phrase_log_entry(self.phraser, e)[0]}
                for e in log.entries
            ],
            "total_added_delay": result.total_added_delay,
        }
