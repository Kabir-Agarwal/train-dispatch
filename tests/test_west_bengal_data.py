"""Gate: the West Bengal probe dataset loads cleanly into the engine model
(DATA LAYER ONLY — no UI, not wired into AppState). Structural assertions only;
performance is measured by probe_wb.py, not asserted here (env-sensitive)."""

from collections import Counter

from data.west_bengal import build_network, build_trains
from engine.model import Network
from engine.scheduler import compute_train_schedule


def test_network_loads_with_expected_size():
    net = build_network()
    assert len(net.stations) == 50
    assert len(net.segment_ids()) == 58
    assert len(build_trains()) == 12


def test_densest_junction_is_barddhaman_degree_5():
    net = build_network()
    deg = Counter()
    for sid in net.segment_ids():
        a, b = net.segment(sid).endpoints
        deg[a] += 1
        deg[b] += 1
    station, d = deg.most_common(1)[0]
    assert station == "BWN" and d == 5


def test_network_is_one_connected_component():
    net = build_network()
    adj = {s: set() for s in net.stations}
    for sid in net.segment_ids():
        a, b = net.segment(sid).endpoints
        adj[a].add(b)
        adj[b].add(a)
    seen, stack = {"HWH"}, ["HWH"]
    while stack:
        for nxt in adj[stack.pop()]:
            if nxt not in seen:
                seen.add(nxt)
                stack.append(nxt)
    assert seen == set(net.stations)  # every station reachable from Howrah


def test_every_train_path_is_a_valid_connected_route():
    net = build_network()
    for t in build_trains():
        arrivals, _ = compute_train_schedule(net, t)   # raises if path is broken
        assert arrivals[t.destination] > arrivals[t.origin]


def test_train_origins_are_spread_across_the_network():
    """Demo realism: trains start from many different stations (not all from one
    or two), so the network looks busy across all corners."""
    trains = build_trains()
    origins = {t.origin for t in trains}
    assert len(origins) >= 10                     # 12 trains, >=10 distinct origins
    # spans the corners: north, south/Kolkata, west, east-border
    assert origins & {"NJP", "APDJ", "MLDT", "NCB"}      # north
    assert origins & {"HWH", "SDAH", "DGH", "HLZ"}       # south / Kolkata
    assert origins & {"ASN", "ADRA", "PRR", "KGP"}       # west
    assert origins & {"BNJ", "LGL"}                      # east border


def test_baseline_is_collision_free():
    """The displayed WB baseline (the engine's deconfliction of the nominal
    timetable) is collision-free — no two trains share a segment-minute."""
    from engine.collision import find_conflicts
    from engine.recompute import recompute_schedule
    res = recompute_schedule(build_network(), build_trains(), [])
    assert find_conflicts(list(res.occupancy_table)) == []
