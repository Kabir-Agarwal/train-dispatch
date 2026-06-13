"""Route enumeration: all simple paths between two stations over open segments.

The network is tiny (<= 8 stations), so full enumeration is cheap and exact.
Paths are sorted by (total effective travel time, segment count, ids) so the
first candidate is always the fastest currently-available route.
"""

from .model import CLOSED, Network


def all_open_paths(network, origin, destination, forbidden=frozenset()):
    """Return every simple path origin->destination as a tuple of segment ids,
    skipping closed segments, sorted fastest-first. Empty list = unreachable.

    `forbidden` is an optional set of segment ids this particular train may not
    use (a per-train path restriction); those segments are skipped exactly like
    closed ones, but ONLY for this call — other trains route over them normally.
    """
    paths = []

    def dfs(at, visited, acc):
        if at == destination:
            paths.append(tuple(acc))
            return
        for seg_id in network.segment_ids():
            seg = network.segment(seg_id)
            if seg.status == CLOSED or seg_id in forbidden or at not in seg.endpoints:
                continue
            nxt = Network.other_end(seg, at)
            if nxt in visited:
                continue
            acc.append(seg_id)
            dfs(nxt, visited | {nxt}, acc)
            acc.pop()

    dfs(origin, {origin}, [])

    def travel(path):
        return sum(network.segment(s).effective_travel_time() for s in path)

    paths.sort(key=lambda p: (travel(p), len(p), p))
    return paths


def path_stations(network, origin, path):
    """The station sequence a path visits, starting at origin."""
    stations = [origin]
    for seg_id in path:
        stations.append(Network.other_end(network.segment(seg_id), stations[-1]))
    return stations
