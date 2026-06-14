"""Application state: ONE source of truth for both views.

The admin board and the passenger view are rendered from the SAME
RecomputeResult — they cannot disagree (and a gate proves it).
The admin is the only anomaly source; anomalies accumulate until reset.
"""

import re

import data.baseline
import data.real_corridor
import data.west_bengal
from engine.anomalies import (
    SEGMENT_ANOMALIES,
    MaintenanceClosure,
    ReducedSpeed,
    TrackBlocked,
    TrackClosed,
    TrainCancelled,
    TrainDelayed,
    TrainRestricted,
    apply_anomalies,
)
from engine.maintenance import flagged_segments, segment_load
from engine.baseline_compare import compare_dispatch
from engine import pricing
from engine.decision_log import (
    build_decision_log,
    describe_anomaly,
    fact_entries_for_all_trains,
)
from engine.errors import BaselineConflictError, DispatchError, ValidationError
from engine.model import Train
from engine.routes import all_open_paths
from engine.phrasing import (
    get_phraser,
    safe_phrase_log_entry,
    safe_phrase_passenger_eta,
    safe_phrase_trigger,
)
from engine.recompute import Action, RecomputeResult, recompute_schedule

from .display import DISPLAY_NAMES, safe_summary
from engine.scheduler import build_schedule, load_baseline

_ANOMALY_TYPES = {
    "track_closed": lambda d: TrackClosed(d["segment"]),
    "track_blocked": lambda d: TrackBlocked(d["segment"]),
    "reduced_speed": lambda d: ReducedSpeed(d["segment"], float(d["factor"])),
    "train_cancelled": lambda d: TrainCancelled(d["train"]),
    "train_delayed": lambda d: TrainDelayed(d["train"], int(d["minutes"])),
    "train_restricted": lambda d: TrainRestricted(d["train"], d["segment"]),
    "maintenance_closure": lambda d: MaintenanceClosure(d["segment"]),
}

# Inspection threshold for the cumulative-load heuristic, per dataset (chosen so
# the genuinely high-load corridors flag). Load weight = train length (coaches)
# where the dataset provides it, else 1.
_MAINT_THRESHOLD = {"baseline": 2, "real": 70, "wb": 50}


def parse_anomaly(payload):
    """JSON dict -> anomaly object; ValidationError on bad shape."""
    kind = payload.get("type")
    if kind not in _ANOMALY_TYPES:
        raise ValidationError(f"unknown anomaly type '{kind}'")
    try:
        return _ANOMALY_TYPES[kind](payload)
    except (KeyError, TypeError, ValueError) as exc:
        raise ValidationError(f"bad parameters for {kind}: {exc}") from exc


def _next_train_id(existing_ids):
    """Deterministic next 'T<n>' id not already taken (keeps the drift guard's
    T-id grammar). Baseline -> T6.., real corridor -> T109.."""
    nums = [int(m.group(1)) for tid in existing_ids
            if (m := re.fullmatch(r"T(\d+)", tid))]
    n = (max(nums) + 1) if nums else 1
    while f"T{n}" in existing_ids:
        n += 1
    return f"T{n}"


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
        elif dataset == "wb":
            module = data.west_bengal
            self.display_names = dict(module.DISPLAY_NAMES)
            self.train_attrs = {}
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
        # Maintenance heuristic config (display layer): per-train load weight
        # (train length / coaches) and the inspection threshold.
        self.load_weights = dict(getattr(module, "LOAD_WEIGHTS", {}))
        self.maint_threshold = _MAINT_THRESHOLD.get(dataset, 2)
        self.phraser = phraser or get_phraser()
        self.reset()
        if dataset == "wb":
            # Default demo anomaly (money-shot): closing the Memari–Barddhaman
            # main forces the Howrah trains onto the Dankuni chord — a visible
            # reroute across the mesh. "Reset to baseline" clears it.
            self.inject([{"type": "track_closed", "segment": "MYM-BWN"}])

    def reset(self):
        self.anomalies = []
        self.added_trains = []  # admin-added live trains (cleared on reset)
        try:
            self.result = _baseline_result(self.network, self.trains)
        except BaselineConflictError:
            # A dense nominal timetable (the WB state mesh) is not conflict-free
            # as published; show the engine's collision-free deconfliction as
            # the baseline instead (still ZERO anomalies — just safe slotting).
            self.result = recompute_schedule(self.network, self.trains, [])
        self.log = None
        self._facts = fact_entries_for_all_trains(
            self.network, self.trains, [], self.result
        )
        self.comparison = self._dispatch_comparison()

    def _all_trains(self):
        return self.trains + self.added_trains

    def _dispatch_comparison(self):
        """Phase B: naive hold-all vs reroute engine for the active closure(s).
        Cached on each state change (it runs extra recomputes) and read by
        snapshot(); {"applicable": False} when no track is closed."""
        return compare_dispatch(
            self.network, self._all_trains(), self.anomalies,
            load_weights=self.load_weights,
        )

    def _make_train(self, spec, anomalies, already_added):
        """Validate an add-train spec and build a Train with a fastest currently-
        open path. Raises (and mutates nothing) on a bad/unreachable request —
        the engine then schedules it collision-free (hold/reroute) on recompute.
        """
        try:
            origin = spec["origin"]
            destination = spec["destination"]
            departure = int(spec["departure"])
        except (KeyError, TypeError, ValueError) as exc:
            raise ValidationError(f"bad new-train spec: {exc}") from exc
        if origin not in self.network.stations:
            raise ValidationError(f"unknown origin station '{origin}'")
        if destination not in self.network.stations:
            raise ValidationError(f"unknown destination station '{destination}'")
        if origin == destination:
            raise ValidationError("a new train's origin and destination must differ")
        if departure < 0:
            raise ValidationError("a new train's departure minute must be >= 0")
        effective = apply_anomalies(self.network, anomalies) if anomalies \
            else self.network
        candidates = all_open_paths(effective, origin, destination)
        if not candidates:
            raise DispatchError(
                f"cannot place a train from {origin} to {destination}: "
                f"no available route"
            )
        existing = {t.id for t in self.trains} | {t.id for t in already_added}
        return Train(_next_train_id(existing), origin, destination,
                     candidates[0], departure)

    def inject(self, payloads, new_trains=None):
        """Admin applies anomalies and/or adds new trains (the ONLY mutation
        source). All-or-nothing: on any error the previous state is kept and
        the error re-raised."""
        new_anomalies = list(self.anomalies)
        for p in payloads or []:
            anomaly = parse_anomaly(p)
            if anomaly not in new_anomalies:  # dedupe repeated injections
                new_anomalies.append(anomaly)
        new_added = list(self.added_trains)
        for spec in (new_trains or []):
            new_added.append(self._make_train(spec, new_anomalies, new_added))
        all_trains = self.trains + new_added
        if new_anomalies:
            result = recompute_schedule(self.network, all_trains, new_anomalies)
        elif new_added:
            # added trains, no active anomaly: re-plan against an untouched net
            result = recompute_schedule(self.network, all_trains, [])
        else:
            raise ValidationError("no anomalies given")
        self.anomalies = new_anomalies
        self.added_trains = new_added
        self.result = result
        self.log = build_decision_log(
            self.network, all_trains, new_anomalies, result
        )
        self._facts = fact_entries_for_all_trains(
            self.network, all_trains, new_anomalies, result
        )
        self.comparison = self._dispatch_comparison()

    def reopen(self, segment_id):
        """Selectively REOPEN one previously closed/blocked/maintenance/speed-
        reduced segment (remove every segment-level anomaly targeting it) and
        recompute via the existing engine. Per-train restrictions, train delays/
        cancellations, and other segments' closures are left untouched — this is
        a surgical undo, NOT a full reset. Unknown or already-open segment ->
        ValidationError, state unchanged."""
        self.network.segment(segment_id)   # raises UnknownSegmentError if unknown
        remaining = [a for a in self.anomalies
                     if not (isinstance(a, SEGMENT_ANOMALIES)
                             and a.segment_id == segment_id)]
        if len(remaining) == len(self.anomalies):
            raise ValidationError(
                f"segment '{segment_id}' has no closure/restriction to reopen"
            )
        all_trains = self.trains + self.added_trains
        if remaining:
            result = recompute_schedule(self.network, all_trains, remaining)
        elif self.added_trains:
            result = recompute_schedule(self.network, all_trains, [])
        else:
            # nothing left to apply -> the clean baseline (collision-free slotting
            # if the nominal timetable is not conflict-free, e.g. the WB mesh)
            try:
                result = _baseline_result(self.network, self.trains)
            except BaselineConflictError:
                result = recompute_schedule(self.network, self.trains, [])
        self.anomalies = remaining
        self.result = result
        self.log = (build_decision_log(self.network, all_trains, remaining, result)
                    if remaining or self.added_trains else None)
        self._facts = fact_entries_for_all_trains(
            self.network, all_trains, remaining, result
        )
        self.comparison = self._dispatch_comparison()

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

    def _maintenance(self):
        """Cumulative-load heuristic over the PLANNED paths (NOT a prediction
        model): per-segment load score, usage count, crossings/hour, and which
        segments cross the inspection threshold. Deterministic."""
        all_trains = self._all_trains()
        load = segment_load(self.network, all_trains, self.load_weights)
        flagged = flagged_segments(load, self.maint_threshold)
        flagged_set = set(flagged)
        # crossings per hour over the planned horizon
        sched = build_schedule(self.network, all_trains)[0]
        horizon = max((m for arr in sched.values() for m in arr.values()), default=0)
        hours = max(horizon / 60.0, 1e-9)

        def freq(c):
            return round(c / hours, 2)

        segs = {}
        for sid, s in load.items():
            segs[sid] = {
                "load_score": s["load_score"],
                "usage_count": s["usage_count"],
                "frequency_per_hour": freq(s["usage_count"]),
                "flagged": sid in flagged_set,
            }
        flagged_list = []
        for sid in flagged:
            s = load[sid]
            ends = self.network.segment(sid).endpoints
            flagged_list.append({
                "id": sid,
                "endpoints": list(ends),
                "load_score": s["load_score"],
                "usage_count": s["usage_count"],
                "frequency_per_hour": freq(s["usage_count"]),
                "reason": (f"cumulative load {s['load_score']:g} ≥ inspection "
                           f"threshold {self.maint_threshold} "
                           f"({s['usage_count']} trains, ~{freq(s['usage_count'])}/h)"),
            })
        return {
            "heuristic": "cumulative-load heuristic (not an AI prediction)",
            "threshold": self.maint_threshold,
            "weighted": bool(self.load_weights),
            "segments": segs,
            "flagged": flagged_list,
        }

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
            "dataset": self.dataset,
            "stations": list(self.network.stations),
            "display_names": dict(self.display_names),
            "train_attrs": {k: dict(v) for k, v in self.train_attrs.items()},
            "summary_text": safe_summary(self.result.actions)
            if (self.anomalies or self.added_trains) else "",
            "segments": self._effective_segments(),
            "maintenance": self._maintenance(),
            "anomalies": [describe_anomaly(a) for a in self.anomalies],
            "added_train_ids": [t.id for t in self.added_trains],
            "trigger_text": trigger_text,
            "trains": trains,
            "decision_log": log_lines,
            "total_added_delay": self.result.total_added_delay,
            "dispatch_comparison": getattr(self, "comparison", {"applicable": False}),
        }

    def passenger(self, train_id):
        """Passenger view: the chosen train's ETA (engine value) AND a rule-based
        dynamic fare estimate. Both stay consistent with the live engine result —
        the fare is recomputed from the train's CURRENT path (so a reroute changes
        distance) and CURRENT departure (so a delay changes the time premium)."""
        if train_id not in self._facts:
            raise ValidationError(f"train '{train_id}' does not exist")
        entry = self._facts[train_id]
        text, violations = safe_phrase_passenger_eta(self.phraser, entry)
        out = {
            "train_id": train_id,
            "eta": entry.arrival,  # engine value, None if cancelled/stranded
            "status": entry.change,
            "text": text,
            "violations": violations,
            "fare": None,
            "fare_reason": "",
            "fare_frozen": False,
            "occupancy": None,
            "synthetic_occupancy": True,  # demo data — production = real bookings
        }
        action = self.result.actions.get(train_id)
        if action is not None and action.path:   # only running trains have a fare
            occ = pricing.synthetic_occupancy(train_id)
            # EMERGENCY FREEZE (Phase D ethics): if this train is disrupted by an
            # active anomaly (rerouted / held / delayed / slowed), price it as if
            # UNDISRUPTED — its nominal route + nominal departure — so the incident
            # never surges the passenger's fare. Otherwise price the live service.
            orig = next((t for t in self._all_trains() if t.id == train_id), None)
            disrupted = bool(self.anomalies) and orig is not None and (
                action.action != "unchanged" or (action.added_delay or 0) != 0
            )
            if disrupted:
                dist = pricing.route_distance(self.network, orig.path)
                est = pricing.fare_estimate(dist, occ, orig.departure)
                out["fare_frozen"] = True
                out["fare_reason"] = pricing.frozen_fare_reason(est)
            else:
                dist = pricing.route_distance(self.network, action.path)
                est = pricing.fare_estimate(dist, occ, action.depart_at)
                out["fare_reason"] = pricing.fare_reason(est)
            out["fare"] = est
            out["occupancy"] = occ
            # stretch: a REAL moving-average forecast on openly-synthetic demand
            series = pricing.synthetic_demand_series(train_id)
            out["demand_series"] = series
            out["demand_forecast"] = pricing.moving_average(series, 3)
            out["demand_next"] = pricing.forecast_next(series, 3)
        return out


    def preview(self, payloads, new_trains=None):
        """GHOST PREVIEW: what WOULD happen if these anomalies were injected
        and/or these new trains added on top of the active state. Runs the SAME
        engine recompute as inject() but mutates nothing. Returns predicted
        segments/trains/log + a delta table against the current state."""
        candidate = list(self.anomalies)
        for p in payloads or []:
            anomaly = parse_anomaly(p)
            if anomaly not in candidate:
                candidate.append(anomaly)
        candidate_added = list(self.added_trains)
        for spec in (new_trains or []):
            candidate_added.append(
                self._make_train(spec, candidate, candidate_added)
            )
        all_trains = self.trains + candidate_added
        result = recompute_schedule(self.network, all_trains, candidate)
        log = build_decision_log(self.network, all_trains, candidate, result)
        current = self.result
        dest_by_id = {t.id: t.destination for t in all_trains}
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
            old = current.actions.get(tid)  # None => a brand-new previewed train
            dest = dest_by_id[tid]
            old_arr = None if old is None or old.arrivals is None \
                else old.arrivals[dest]
            new_arr = None if new.arrivals is None else new.arrivals[dest]
            changed = (old is None or new.action != old.action
                       or new.path != old.path or new.arrivals != old.arrivals)
            deltas.append({
                "id": tid,
                "old_action": None if old is None else old.action,
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
            "added_train_ids": [t.id for t in candidate_added],
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
