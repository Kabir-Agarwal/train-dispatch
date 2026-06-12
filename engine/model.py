"""Network data model: stations, segments, trains.

Decisions (see PROGRESS.md):
- Stations are a plain appendable list (Phase 6 wants a live 7th station).
- Segments are bidirectional single-track: occupancy applies regardless of direction.
- Times are integer minutes.
"""

import math
from dataclasses import dataclass

OPEN = "open"
CLOSED = "closed"
REDUCED_SPEED = "reduced-speed"
SEGMENT_STATUSES = (OPEN, CLOSED, REDUCED_SPEED)

from .errors import UnknownSegmentError, ValidationError


@dataclass(frozen=True)
class Segment:
    id: str
    endpoints: tuple  # (station_a, station_b)
    travel_time: int  # minutes at full speed
    status: str = OPEN
    speed_factor: float = 1.0  # fraction of full speed; 0.5 = half speed

    def effective_travel_time(self):
        """Minutes to traverse at current speed (rounded up to whole minutes)."""
        return math.ceil(self.travel_time / self.speed_factor)


@dataclass(frozen=True)
class Train:
    id: str
    origin: str
    destination: str
    path: tuple  # ordered segment ids
    departure: int  # minute the train leaves its origin


class Network:
    def __init__(self, stations, segments):
        self.stations = list(stations)  # appendable list
        if len(set(self.stations)) != len(self.stations):
            raise ValidationError("duplicate station ids in station list")
        self._segments = {}
        for seg in segments:
            self.add_segment(seg)

    def add_station(self, station_id):
        if station_id in self.stations:
            raise ValidationError(f"station '{station_id}' already exists")
        self.stations.append(station_id)

    def add_segment(self, seg):
        if seg.id in self._segments:
            raise ValidationError(f"duplicate segment id '{seg.id}'")
        a, b = seg.endpoints
        for end in (a, b):
            if end not in self.stations:
                raise ValidationError(
                    f"segment '{seg.id}' endpoint '{end}' is not a known station"
                )
        if a == b:
            raise ValidationError(f"segment '{seg.id}' connects a station to itself")
        if not isinstance(seg.travel_time, int) or seg.travel_time <= 0:
            raise ValidationError(
                f"segment '{seg.id}' travel_time must be a positive integer"
            )
        if seg.status not in SEGMENT_STATUSES:
            raise ValidationError(
                f"segment '{seg.id}' status '{seg.status}' not in {SEGMENT_STATUSES}"
            )
        if not (0 < seg.speed_factor <= 1):
            raise ValidationError(
                f"segment '{seg.id}' speed_factor must be in (0, 1], got {seg.speed_factor}"
            )
        self._segments[seg.id] = seg

    def segment(self, seg_id):
        if seg_id not in self._segments:
            raise UnknownSegmentError(f"segment '{seg_id}' does not exist")
        return self._segments[seg_id]

    def segment_ids(self):
        return list(self._segments)

    @staticmethod
    def other_end(seg, station):
        a, b = seg.endpoints
        if station == a:
            return b
        if station == b:
            return a
        raise ValidationError(
            f"station '{station}' is not an endpoint of segment '{seg.id}'"
        )
