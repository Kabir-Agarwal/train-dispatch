"""Impact detection: who is affected by injected anomalies, and how.

Phase 2 ONLY detects and classifies impact. It does NOT reroute, hold, or
resolve conflicts — that is Phase 3.
"""

from collections import deque
from dataclasses import dataclass, replace

from .anomalies import (
    apply_anomalies,
    cancelled_train_ids,
    closed_segment_ids,
    delay_minutes,
    reduced_segments,
    validate_anomalies,
)
from .collision import find_conflicts
from .model import CLOSED
from .scheduler import compute_train_schedule

UNAFFECTED = "unaffected"
TIMES_SHIFTED = "times_shifted"
NEEDS_REROUTE = "needs_reroute"
STRANDED = "stranded"
CANCELLED = "cancelled"


def destination_reachable(network, origin, destination):
    """BFS over OPEN (non-closed) segments. Always terminates: each station
    is visited at most once."""
    if origin == destination:
        return True
    seen = {origin}
    queue = deque([origin])
    while queue:
        station = queue.popleft()
        for seg_id in network.segment_ids():
            seg = network.segment(seg_id)
            if seg.status == CLOSED or station not in seg.endpoints:
                continue
            nxt = seg.endpoints[0] if seg.endpoints[1] == station else seg.endpoints[1]
            if nxt == destination:
                return True
            if nxt not in seen:
                seen.add(nxt)
                queue.append(nxt)
    return False
