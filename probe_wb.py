"""PERFORMANCE PROBE for the West Bengal network (no UI). Reports size, junction
density, per-train route-enumeration cost, and one worst-case closure recompute.

Run:  python probe_wb.py
Everything is flushed immediately so that if full-DFS enumeration explodes, the
last printed line locates exactly where it hung (run under an external timeout).
"""

import time
from collections import Counter

from data import west_bengal as wb
from engine.anomalies import TrackClosed, apply_anomalies
from engine.collision import find_conflicts
from engine.recompute import recompute_schedule
from engine.routes import all_open_paths

P = lambda *a: print(*a, flush=True)


def main():
    net = wb.build_network()
    trains = wb.build_trains()

    # 1) size
    n_st = len(net.stations)
    n_seg = len(net.segment_ids())
    P(f"[size] stations={n_st}  segments={n_seg}  trains={len(trains)}")

    # 2) density: max segments meeting at one station
    deg = Counter()
    for sid in net.segment_ids():
        a, b = net.segment(sid).endpoints
        deg[a] += 1
        deg[b] += 1
    busiest_station, busiest_deg = deg.most_common(1)[0]
    top = ", ".join(f"{wb.DISPLAY_NAMES[s]}({s})={d}"
                    for s, d in deg.most_common(5))
    P(f"[density] max junction degree = {busiest_deg} at "
      f"{wb.DISPLAY_NAMES[busiest_station]} ({busiest_station})")
    P(f"[density] top-5 junctions: {top}")

    # 3) pick the busiest segment incident to the densest junction
    incident = [sid for sid in net.segment_ids()
                if busiest_station in net.segment(sid).endpoints]
    usage = Counter()
    for t in trains:
        for sid in t.path:
            if sid in incident:
                usage[sid] += 1
    target = max(incident, key=lambda s: (usage[s], s))
    P(f"[closure] incident segments at {busiest_station}: "
      + ", ".join(f"{s}(used by {usage[s]})" for s in sorted(incident)))
    P(f"[closure] closing busiest incident segment: {target} "
      f"(used by {usage[target]} trains)")

    # 3a) DIAGNOSTIC: per-train route-enumeration cost AFTER the closure. This is
    # the real scaling signal — recompute calls all_open_paths once per train.
    eff = apply_anomalies(net, [TrackClosed(target)])
    P("[enum] per-train all_open_paths (path_count, ms) on the closed network:")
    grand = 0.0
    for t in trains:
        t0 = time.perf_counter()
        paths = all_open_paths(eff, t.origin, t.destination)
        ms = (time.perf_counter() - t0) * 1000
        grand += ms
        P(f"   {t.id:>4} {t.origin}->{t.destination:<5} "
          f"paths={len(paths):>8}  {ms:8.1f} ms")
    P(f"[enum] total enumeration across all trains: {grand:.1f} ms")

    # 4) one full recompute / reroute at the densest junction
    P("[recompute] starting full recompute with the closure ...")
    t0 = time.perf_counter()
    result = recompute_schedule(net, trains, [TrackClosed(target)])
    ms = (time.perf_counter() - t0) * 1000
    conflicts = find_conflicts(list(result.occupancy_table))
    rerouted = sum(1 for a in result.actions.values() if a.action == "reroute")
    stranded = sum(1 for a in result.actions.values() if a.action == "stranded")
    P(f"[recompute] DONE in {ms:.1f} ms  "
      f"(rerouted={rerouted} stranded={stranded} conflicts={len(conflicts)})")
    P(f"[verdict] {'UNDER 500ms — OK to proceed' if ms < 500 else 'OVER 500ms — STOP'}")


if __name__ == "__main__":
    main()
