"""Phase L — freight handling (CONNECTED to the existing system, not standalone).

Two parts:

1. YARD CLASSIFICATION (core algorithm): sort N inbound wagons to M destination
   ("classification") tracks under two real constraints — track LENGTH (capacity)
   and HAZMAT ADJACENCY (no two hazardous wagons next to each other on a track) —
   while MINIMISING reshuffles. Method: greedy constrained classification — each
   wagon goes to its destination's track; it is reworked (a reshuffle) only when
   that track is full or placing it would put two hazmat wagons adjacent. Reworks
   only when forced, so forced reshuffles are minimised. The yard data is
   SYNTHETIC and clearly labelled — not a real wagon manifest.

2. CONNECTION to the network: each destination track's wagons become a FREIGHT
   train (lowest priority, PRIORITY_FREIGHT from Phase C) bound for that
   destination. Because freight is the lowest priority, the existing recompute
   makes it YIELD to express/passenger trains under contention — reused, not
   reinvented (see app.state._freight_yield_demo + tests).
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class Wagon:
    id: str
    dest: str          # destination classification track
    hazmat: bool = False


def synthetic_yard():
    """A fixed, deterministic, clearly-SYNTHETIC inbound rake: (wagons, capacities).
    NOT real wagon data — illustrative for the demo. Destinations are real WB
    freight sinks (New Jalpaiguri, Kharagpur, Asansol coalfield)."""
    inbound = [
        ("W1", "ASN", False), ("W2", "ASN", True),  ("W3", "KGP", False),
        ("W4", "NJP", False), ("W5", "ASN", False), ("W6", "ASN", True),
        ("W7", "KGP", True),  ("W8", "NJP", False), ("W9", "KGP", False),
        ("W10", "NJP", True), ("W11", "ASN", False), ("W12", "KGP", False),
    ]
    wagons = [Wagon(i, d, h) for i, d, h in inbound]
    capacities = {"NJP": 4, "KGP": 4, "ASN": 3}     # synthetic track lengths
    return wagons, capacities


def _would_violate_hazmat(track_wagons, wagon):
    """True if appending `wagon` puts two hazmat wagons adjacent on the track."""
    return wagon.hazmat and bool(track_wagons) and track_wagons[-1].hazmat


def classify(wagons, capacities):
    """Greedy constrained classification. Returns the per-track contents, the
    reworked wagons (reshuffles), and a validity flag. Deterministic."""
    tracks = {dest: [] for dest in capacities}
    rework = []
    for w in wagons:
        track = tracks.get(w.dest)
        if track is None:
            rework.append({"id": w.id, "dest": w.dest, "reason": "no-track-for-dest"})
        elif len(track) >= capacities[w.dest]:
            rework.append({"id": w.id, "dest": w.dest, "reason": "track-full"})
        elif _would_violate_hazmat(track, w):
            rework.append({"id": w.id, "dest": w.dest, "reason": "hazmat-adjacency"})
        else:
            track.append(w)
    return {
        "tracks": tracks,                      # dest -> [Wagon, ...] in placed order
        "rework": rework,                      # wagons that needed a reshuffle
        "reshuffles": len(rework),
        "valid": is_valid_classification(tracks, capacities),
    }


def is_valid_classification(tracks, capacities):
    """No track over capacity, and no two hazmat wagons adjacent on any track."""
    for dest, wagons in tracks.items():
        if len(wagons) > capacities.get(dest, 0):
            return False
        for a, b in zip(wagons, wagons[1:]):
            if a.hazmat and b.hazmat:
                return False
    return True
