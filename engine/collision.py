"""Collision checker — the hard safety rule.

Two trains on the same segment at the same minute is a conflict, INCLUDING
exact boundary overlap: window [0,10] conflicts with window [10,20] because
both trains are on the segment at minute 10.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class Conflict:
    segment_id: str
    train_a: str
    train_b: str
    start: int  # first shared minute
    end: int  # last shared minute


def windows_overlap(a_start, a_end, b_start, b_end):
    """Inclusive overlap: True if the closed intervals share any minute."""
    return a_start <= b_end and b_start <= a_end


def find_conflicts(occupancy_table):
    """Return all pairwise conflicts in the occupancy table, sorted by
    (segment, first shared minute, train pair). Empty list = safe."""
    by_segment = {}
    for occ in occupancy_table:
        by_segment.setdefault(occ.segment_id, []).append(occ)
    conflicts = []
    for seg_id, occs in by_segment.items():
        for i in range(len(occs)):
            for j in range(i + 1, len(occs)):
                a, b = occs[i], occs[j]
                if a.train_id == b.train_id:
                    continue
                if windows_overlap(a.start, a.end, b.start, b.end):
                    first, second = sorted((a, b), key=lambda o: o.train_id)
                    conflicts.append(
                        Conflict(
                            segment_id=seg_id,
                            train_a=first.train_id,
                            train_b=second.train_id,
                            start=max(a.start, b.start),
                            end=min(a.end, b.end),
                        )
                    )
    conflicts.sort(key=lambda c: (c.segment_id, c.start, c.train_a, c.train_b))
    return conflicts
