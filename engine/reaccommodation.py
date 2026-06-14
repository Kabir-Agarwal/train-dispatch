"""Phase K — passenger re-accommodation.

When a train is CANCELLED, its passengers still need to travel. This reroutes the
PEOPLE (not the train): for each affected origin->destination pair along the
cancelled train's route, it finds the earliest-arriving alternative journey over
the remaining trains' timetable — a real next-best route + ETA, with transfers.

Method — CONNECTION-SCAN ALGORITHM (CSA, earliest-arrival): every segment hop of
every remaining train is a "connection" (from, to, dep, arr, train). Connections
are scanned in departure order; a connection is boardable if the passenger has
already reached its `from` station by its `dep` time, and it improves the earliest
arrival at its `to`. The destination's best arrival, reconstructed back to the
origin, is the alternative journey. (Zero transfer time, matching the engine's
zero-dwell model — labelled.) Pure and deterministic; no scheduling, so the
recompute golden is unaffected.
"""

from .scheduler import compute_train_schedule

_METHOD = ("Connection-Scan Algorithm (earliest-arrival) over the remaining "
           "trains' timetable; zero transfer time")


def _connections(network, trains, exclude_id):
    """Every remaining train's segment hops as boardable connections."""
    conns = []
    for t in trains:
        if t.id == exclude_id:
            continue
        arrivals, _ = compute_train_schedule(network, t)
        seq = sorted(arrivals.items(), key=lambda kv: kv[1])
        for (a, ta), (b, tb) in zip(seq, seq[1:]):
            conns.append({"from": a, "to": b, "dep": ta, "arr": tb, "train": t.id})
    return conns


def earliest_journey(connections, origin, destination, ready_time):
    """CSA earliest arrival from `origin` (available at `ready_time`) to
    `destination`. Returns {eta, legs, transfers} or None if unreachable."""
    INF = float("inf")
    best = {origin: ready_time}
    pred = {}
    for c in sorted(connections, key=lambda c: (c["dep"], c["arr"])):
        if c["dep"] >= best.get(c["from"], INF) and c["arr"] < best.get(c["to"], INF):
            best[c["to"]] = c["arr"]
            pred[c["to"]] = c
    if destination not in best or destination == origin:
        return None
    legs, cur, seen = [], destination, set()
    while cur in pred and cur not in seen:
        seen.add(cur)
        c = pred[cur]
        legs.append(c)
        cur = c["from"]
        if cur == origin:
            break
    if cur != origin:
        return None
    legs.reverse()
    transfers = sum(1 for k in range(1, len(legs))
                    if legs[k]["train"] != legs[k - 1]["train"])
    return {"eta": best[destination], "legs": legs, "transfers": transfers}


def reaccommodate(network, trains, cancelled_id):
    """For a cancelled train, the earliest-arrival alternative for each affected
    passenger O->D pair along its route (ready when the cancelled train would have
    been at the origin). Returns a summary dict; {"applicable": False} if the
    train id is unknown."""
    cancelled = next((t for t in trains if t.id == cancelled_id), None)
    if cancelled is None:
        return {"applicable": False}

    arrivals, _ = compute_train_schedule(network, cancelled)
    seq = sorted(arrivals.items(), key=lambda kv: kv[1])     # (station, time) on route
    conns = _connections(network, trains, cancelled_id)

    passengers = []
    for i in range(len(seq)):
        for j in range(i + 1, len(seq)):
            (origin, ready), (dest, _) = seq[i], seq[j]
            jr = earliest_journey(conns, origin, dest, ready)
            passengers.append({
                "from": origin, "to": dest, "ready": ready,
                "eta": jr["eta"] if jr else None,
                "legs": jr["legs"] if jr else [],
                "transfers": jr["transfers"] if jr else None,
                "stranded": jr is None,
            })
    reacc = [p for p in passengers if not p["stranded"]]
    return {
        "applicable": True,
        "cancelled": cancelled_id,
        "origin": cancelled.origin,
        "destination": cancelled.destination,
        "total": len(passengers),
        "reaccommodated": len(reacc),
        "stranded": len(passengers) - len(reacc),
        "passengers": passengers,
        "method": _METHOD,
    }
