"""Phase J — possession / maintenance-window scheduling.

A "possession" takes a track segment out of service for a fixed DURATION so it can
be maintained (it pairs with the cumulative-load wear flagging: the flagged
segments are the ones that need possessions). The question is WHEN to schedule it
so the timetable is disrupted as little as possible.

Method — MINIMUM-DISRUPTION WINDOW SEARCH, reusing the reroute engine:
- Per-train displacement cost comes from the existing engine: recompute the
  schedule with the segment CLOSED; a train that must reroute pays its added
  delay (max 0), and a train with no alternative is STRANDED.
- A candidate window [start, start+duration] DISPLACES exactly the trains whose
  baseline occupancy of the segment overlaps it (a train using the segment
  outside the window is unaffected).
- Each window is scored by (trains stranded, total added delay) — avoid
  stranding first, then minimise delay — and the lowest-scoring start wins.
- The "naive" window is a fixed one placed at the segment's FIRST use (a naive
  "do it as soon as the line is busy"); the smart window is the scan minimum.

Pure and deterministic; calls recompute_schedule once but never changes it, so the
byte-identical recompute golden is unaffected. The disruption is an ESTIMATE
(displaced trains rerouted around the possession), labelled as such.
"""

from .anomalies import TrackClosed
from .recompute import recompute_schedule
from .scheduler import compute_train_schedule

# Default maintenance-block length the app schedules on a wear-flagged segment.
POSSESSION_DURATION_MIN = 60

_METHOD = ("minimum-disruption possession window: reuse the reroute engine for "
           "per-train displacement cost, scan windows for the least "
           "(stranded, added-delay) — estimate, displaced trains rerouted")


def _overlaps(enter, exit_, start, end):
    return enter <= end and start <= exit_           # inclusive interval overlap


def best_possession(network, trains, segment_id, duration,
                    naive_start=None, horizon=None, step=1):
    """Lowest-disruption possession window of `duration` minutes on `segment_id`,
    vs a naive fixed window at the segment's first use. Returns a dict."""
    network.segment(segment_id)                      # validates the segment exists
    if duration <= 0:
        return {"applicable": False}

    # baseline occupancy of this segment, per train (when each train uses it)
    occ = {}
    max_arr = 0
    for t in trains:
        arrivals, occs = compute_train_schedule(network, t)
        max_arr = max(max_arr, max(arrivals.values()))
        for o in occs:
            if o.segment_id == segment_id:
                occ[t.id] = (o.start, o.end)

    # per-train displacement cost if the segment is unavailable (reroute engine)
    closed = recompute_schedule(network, trains, [TrackClosed(segment_id)])
    cost, stranded = {}, set()
    for tid, a in closed.actions.items():
        if a.path is None:                           # no reroute -> stranded
            stranded.add(tid)
            cost[tid] = 0
        else:
            cost[tid] = max(0, a.added_delay or 0)

    if horizon is None:
        horizon = max_arr
    if naive_start is None:
        naive_start = min((e for e, _ in occ.values()), default=0)

    def score(start):
        end = start + duration
        disp = sorted(tid for tid, (e, x) in occ.items() if _overlaps(e, x, start, end))
        s_ct = sum(1 for tid in disp if tid in stranded)
        delay = sum(cost[tid] for tid in disp if tid not in stranded)
        return s_ct, delay, disp

    # scan every start; pick the least (stranded, delay), earliest on a tie
    best_start, best_key = 0, None
    last = max(0, horizon - duration)
    s = 0
    while s <= last:
        s_ct, delay, _ = score(s)
        key = (s_ct, delay)
        if best_key is None or key < best_key:
            best_key, best_start = key, s
        s += step
    b_str, b_del, b_disp = score(best_start)
    n_str, n_del, n_disp = score(naive_start)

    return {
        "applicable": True,
        "segment": segment_id,
        "duration": duration,
        "horizon": horizon,
        "best_start": best_start, "best_end": best_start + duration,
        "best_delay": b_del, "best_stranded": b_str, "displaced_best": b_disp,
        "naive_start": naive_start, "naive_end": naive_start + duration,
        "naive_delay": n_del, "naive_stranded": n_str, "displaced_naive": n_disp,
        "saved_delay": n_del - b_del,
        "saved_stranded": n_str - b_str,
        "method": _METHOD,
    }
