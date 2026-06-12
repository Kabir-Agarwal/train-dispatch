"""Decision log (SPEC F4): every engine change produces a structured entry —
trigger, change, reason, numbers. Everything here is ENGINE OUTPUT; the
phrasing layer may only re-word these facts, never add to them.

Each entry carries its own allow-lists (`numbers`, `entities`) used by the
drift guard to verify any phrased text against engine values.
"""

import re
from dataclasses import dataclass

from .anomalies import (
    ReducedSpeed,
    TrackBlocked,
    TrackClosed,
    TrainCancelled,
    TrainDelayed,
    delay_minutes,
)

ID_PATTERN = re.compile(r"\b(?:SEG-\d+|T\d+|S\d+)\b")
NUMBER_PATTERN = re.compile(r"\d+(?:\.\d+)?")


def describe_anomaly(a):
    if isinstance(a, TrackClosed):
        return f"track_closed({a.segment_id})"
    if isinstance(a, TrackBlocked):
        return f"track_blocked({a.segment_id})"
    if isinstance(a, ReducedSpeed):
        return f"reduced_speed({a.segment_id}, factor {a.factor})"
    if isinstance(a, TrainCancelled):
        return f"train_cancelled({a.train_id})"
    if isinstance(a, TrainDelayed):
        return f"train_delayed({a.train_id}, {a.minutes} min)"
    raise ValueError(f"unknown anomaly: {a!r}")


def ids_in(text):
    return set(ID_PATTERN.findall(text))


def numbers_in(text):
    stripped = ID_PATTERN.sub(" ", text)
    return {float(n) for n in NUMBER_PATTERN.findall(stripped)}


@dataclass(frozen=True)
class LogEntry:
    train_id: str
    change: str  # the action: reroute | hold | depart_delayed | unchanged(+delay) | cancelled | stranded
    reason: str  # engine-produced reason, verbatim
    destination: str
    arrival: int | None  # destination arrival minute (None if train cannot run)
    added_delay: int | None
    numbers: frozenset  # every numeric value phrasing may use (floats)
    entities: frozenset  # every T*/S*/SEG-* id phrasing may mention


@dataclass(frozen=True)
class DecisionLog:
    trigger: str  # e.g. "track_closed(SEG-34) + train_delayed(T4, 5 min)"
    entries: tuple  # one LogEntry per CHANGED train, ordered by train id
    total_added_delay: int
    trigger_numbers: frozenset
    trigger_entities: frozenset


def _entry(network, train, action, admin_delays):
    numbers = set()
    entities = {train.id, train.origin, train.destination}
    entities.update(train.path)  # old path segments are engine facts
    if action.path:
        entities.update(action.path)
    if action.arrivals:
        for station, minute in action.arrivals.items():
            entities.add(station)
            numbers.add(float(minute))
    if action.depart_at is not None:
        numbers.add(float(action.depart_at))
    if action.added_delay is not None:
        numbers.add(float(action.added_delay))
        numbers.add(float(abs(action.added_delay)))
    if train.id in admin_delays:
        numbers.add(float(admin_delays[train.id]))
    # everything in the engine reason is engine output: allow it
    entities.update(ids_in(action.reason))
    numbers.update(numbers_in(action.reason))
    return LogEntry(
        train_id=train.id,
        change=action.action,
        reason=action.reason,
        destination=train.destination,
        arrival=None if action.arrivals is None else action.arrivals[train.destination],
        added_delay=action.added_delay,
        numbers=frozenset(numbers),
        entities=frozenset(entities),
    )


def build_decision_log(network, trains, anomalies, result):
    """One entry per train the engine changed (any action other than a clean
    'unchanged', including slowed-in-place trains with shifted times)."""
    trigger = " + ".join(describe_anomaly(a) for a in anomalies)
    admin_delays = delay_minutes(anomalies)
    by_id = {t.id: t for t in trains}
    entries = []
    for tid in sorted(result.actions):
        action = result.actions[tid]
        changed = action.action != "unchanged" or (action.added_delay or 0) != 0
        if changed:
            entries.append(_entry(network, by_id[tid], action, admin_delays))
    return DecisionLog(
        trigger=trigger,
        entries=tuple(entries),
        total_added_delay=result.total_added_delay,
        trigger_numbers=frozenset(numbers_in(trigger)),
        trigger_entities=frozenset(ids_in(trigger)),
    )


def fact_entries_for_all_trains(network, trains, anomalies, result):
    """Fact packs (LogEntry) for EVERY train, changed or not — the passenger
    view needs an ETA for every train, with the same allow-list guarantees."""
    admin_delays = delay_minutes(anomalies)
    return {
        t.id: _entry(network, t, result.actions[t.id], admin_delays)
        for t in trains
    }
