"""Baseline scheduler: path validation, per-station arrival times, occupancy table.

Decisions (see PROGRESS.md):
- Zero dwell time at intermediate stations: a train exits one segment and
  enters the next at the same minute.
- An occupancy window is the closed interval [enter_minute, exit_minute].
"""

from dataclasses import dataclass

from .errors import BaselineConflictError, DisconnectedPathError, ValidationError
from .model import Network


@dataclass(frozen=True)
class Occupancy:
    train_id: str
    segment_id: str
    start: int  # minute the train enters the segment
    end: int  # minute the train exits the segment


def validate_path(network, train):
    """Raise a ValidationError subclass if the train's path is not a connected
    route from origin to destination using existing segments."""
    if not train.path:
        raise ValidationError(f"train '{train.id}' has an empty path")
    at = train.origin
    if at not in network.stations:
        raise ValidationError(f"train '{train.id}' origin '{at}' is not a station")
    for seg_id in train.path:
        seg = network.segment(seg_id)  # raises UnknownSegmentError
        a, b = seg.endpoints
        if at not in (a, b):
            raise DisconnectedPathError(
                f"train '{train.id}' path breaks at '{at}': "
                f"segment '{seg_id}' connects {a}-{b}, not '{at}'"
            )
        at = Network.other_end(seg, at)
    if at != train.destination:
        raise DisconnectedPathError(
            f"train '{train.id}' path ends at '{at}', not destination "
            f"'{train.destination}'"
        )


def compute_train_schedule(network, train):
    """Return (arrivals, occupancies) for one train.

    arrivals: {station_id: minute}, including the origin at departure minute.
    occupancies: list of Occupancy, one per path segment, in path order.
    """
    validate_path(network, train)
    arrivals = {train.origin: train.departure}
    occupancies = []
    at = train.origin
    clock = train.departure
    for seg_id in train.path:
        seg = network.segment(seg_id)
        enter = clock
        clock += seg.travel_time
        at = Network.other_end(seg, at)
        arrivals[at] = clock
        occupancies.append(Occupancy(train.id, seg_id, enter, clock))
    return arrivals, occupancies


def build_schedule(network, trains):
    """Return (schedule, occupancy_table) for all trains.

    schedule: {train_id: {station_id: arrival_minute}}
    occupancy_table: flat list of Occupancy across all trains.
    """
    ids = [t.id for t in trains]
    if len(set(ids)) != len(ids):
        raise ValidationError("duplicate train ids")
    schedule = {}
    occupancy_table = []
    for train in trains:
        arrivals, occupancies = compute_train_schedule(network, train)
        schedule[train.id] = arrivals
        occupancy_table.extend(occupancies)
    return schedule, occupancy_table


def load_baseline(network, trains):
    """Build the baseline schedule and refuse to accept one with conflicts.

    Returns (schedule, occupancy_table) or raises BaselineConflictError.
    """
    from .collision import find_conflicts

    schedule, occupancy_table = build_schedule(network, trains)
    conflicts = find_conflicts(occupancy_table)
    if conflicts:
        raise BaselineConflictError(conflicts)
    return schedule, occupancy_table
