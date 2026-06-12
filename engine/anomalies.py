"""Admin-injected anomalies: types, validation, and application to the network.

The admin view is the ONLY anomaly source. Anomalies are injected as a list
(combinations = a list with more than one entry).

Decisions (see PROGRESS.md):
- track_closed and track_blocked have the same routing effect (segment status
  -> closed); the label is kept for reporting.
- reduced_speed factor is the fraction of full speed, in (0, 1):
  effective time = ceil(travel_time / factor).
- closed/blocked beats reduced_speed if both hit the same segment.
- multiple delays for one train add up; cancellation beats delay.
"""

from dataclasses import dataclass, replace

from .errors import UnknownTrainError, ValidationError
from .model import CLOSED, REDUCED_SPEED, Network


@dataclass(frozen=True)
class TrackClosed:
    segment_id: str
    kind = "track_closed"


@dataclass(frozen=True)
class TrackBlocked:
    segment_id: str
    kind = "track_blocked"


@dataclass(frozen=True)
class ReducedSpeed:
    segment_id: str
    factor: float
    kind = "reduced_speed"


@dataclass(frozen=True)
class TrainCancelled:
    train_id: str
    kind = "train_cancelled"


@dataclass(frozen=True)
class TrainDelayed:
    train_id: str
    minutes: int
    kind = "train_delayed"


SEGMENT_ANOMALIES = (TrackClosed, TrackBlocked, ReducedSpeed)
TRAIN_ANOMALIES = (TrainCancelled, TrainDelayed)


def validate_anomalies(network, trains, anomalies):
    """Reject anomalies referencing unknown segments/trains or with bad values."""
    if not anomalies:
        raise ValidationError("no anomalies given")
    train_ids = {t.id for t in trains}
    for a in anomalies:
        if isinstance(a, SEGMENT_ANOMALIES):
            network.segment(a.segment_id)  # raises UnknownSegmentError
        elif isinstance(a, TRAIN_ANOMALIES):
            if a.train_id not in train_ids:
                raise UnknownTrainError(f"train '{a.train_id}' does not exist")
        else:
            raise ValidationError(f"unknown anomaly type: {a!r}")
        if isinstance(a, ReducedSpeed) and not (0 < a.factor < 1):
            raise ValidationError(
                f"reduced_speed factor must be in (0, 1), got {a.factor}"
            )
        if isinstance(a, TrainDelayed) and (
            not isinstance(a.minutes, int) or a.minutes <= 0
        ):
            raise ValidationError(
                f"train_delayed minutes must be a positive integer, got {a.minutes}"
            )


def closed_segment_ids(anomalies):
    return {a.segment_id for a in anomalies if isinstance(a, (TrackClosed, TrackBlocked))}


def reduced_segments(anomalies):
    return {a.segment_id: a.factor for a in anomalies if isinstance(a, ReducedSpeed)}


def cancelled_train_ids(anomalies):
    return {a.train_id for a in anomalies if isinstance(a, TrainCancelled)}


def delay_minutes(anomalies):
    delays = {}
    for a in anomalies:
        if isinstance(a, TrainDelayed):
            delays[a.train_id] = delays.get(a.train_id, 0) + a.minutes
    return delays


def apply_anomalies(network, anomalies):
    """Return a NEW Network with anomaly effects applied; original untouched."""
    closed = closed_segment_ids(anomalies)
    reduced = reduced_segments(anomalies)
    new_segments = []
    for seg_id in network.segment_ids():
        seg = network.segment(seg_id)
        if seg_id in closed:
            seg = replace(seg, status=CLOSED)
        elif seg_id in reduced:
            seg = replace(seg, status=REDUCED_SPEED, speed_factor=reduced[seg_id])
        new_segments.append(seg)
    return Network(network.stations, new_segments)
