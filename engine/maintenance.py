"""Predictive maintenance — a CUMULATIVE-LOAD HEURISTIC (NOT an AI prediction).

For each track segment we accumulate, over the trains whose planned path uses
it, a load score = sum of a per-train load weight (the train's length if known,
else 1) — plus the raw usage count. A segment whose load score crosses a
threshold is FLAGGED "due for inspection". A flagged segment can then be
scheduled as an engine.anomalies.MaintenanceClosure, which the existing reroute
logic handles exactly like any other closure.

Pure functions over (network, trains, weights): deterministic, no scheduling.
"""

DEFAULT_LOAD_WEIGHT = 1.0


def load_weight(train, weights=None):
    """A train's load contribution: an explicit weight (e.g. its length / coach
    count) when supplied, otherwise the default of 1."""
    if weights and train.id in weights:
        return float(weights[train.id])
    return DEFAULT_LOAD_WEIGHT


def segment_load(network, trains, weights=None):
    """Map every segment id to {usage_count, load_score, trains} over the trains'
    PLANNED paths. usage_count = how many trains cross it; load_score = sum of
    their load weights; trains = the ids, in train order. Deterministic."""
    stats = {sid: {"usage_count": 0, "load_score": 0.0, "trains": []}
             for sid in network.segment_ids()}
    for t in trains:
        w = load_weight(t, weights)
        for sid in t.path:
            s = stats.get(sid)
            if s is None:
                continue
            s["usage_count"] += 1
            s["load_score"] += w
            s["trains"].append(t.id)
    for s in stats.values():
        s["load_score"] = round(s["load_score"], 3)  # tame float noise
    return stats


def flagged_segments(stats, threshold):
    """Segment ids with load_score >= threshold, busiest first then by id
    (deterministic ordering)."""
    flagged = [sid for sid, s in stats.items() if s["load_score"] >= threshold]
    flagged.sort(key=lambda sid: (-stats[sid]["load_score"], sid))
    return flagged
