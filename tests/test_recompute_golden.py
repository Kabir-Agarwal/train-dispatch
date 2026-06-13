"""Gate: the optimized recompute is a correctness-preserving refactor — it must
produce BYTE-IDENTICAL output to the pre-optimization engine on a fixed set of
scenarios across all three networks (baseline, real corridor, West Bengal).

The reference (tests/recompute_golden.json) was captured from the engine BEFORE
the conflict-index / analytic-min-hold optimization. If this fails, the
optimization changed behavior and must be fixed — not the golden.

The scenario list here mirrors tests/_golden_gen.py exactly.
"""

import json
import os

import data.baseline as baseline
import data.real_corridor as real
import data.west_bengal as wb
from engine.anomalies import (
    ReducedSpeed,
    TrackClosed,
    TrainCancelled,
    TrainDelayed,
    TrainRestricted,
)
from engine.model import Train
from engine.recompute import recompute_schedule
from engine.routes import all_open_paths

GOLDEN = os.path.join(os.path.dirname(__file__), "recompute_golden.json")


def _serialize(result):
    return {
        "actions": {
            tid: {
                "action": a.action,
                "path": list(a.path) if a.path else None,
                "depart_at": a.depart_at,
                "arrivals": a.arrivals,
                "added_delay": a.added_delay,
                "reason": a.reason,
            }
            for tid, a in sorted(result.actions.items())
        },
        "total_added_delay": result.total_added_delay,
        "table": sorted(
            [o.train_id, o.segment_id, o.start, o.end]
            for o in result.occupancy_table
        ),
    }


def _scenarios():
    bnet, btr = baseline.build_network(), baseline.build_trains()
    rnet, rtr = real.build_network(), real.build_trains()
    wnet, wtr = wb.build_network(), wb.build_trains()
    b_extra = Train("T9", "S3", "S6", all_open_paths(bnet, "S3", "S6")[0], 40)
    b_extra2 = Train("T9", "S1", "S2", all_open_paths(bnet, "S1", "S2")[0], 0)
    return [
        ("baseline/empty", bnet, btr, []),
        ("baseline/close-SEG-34", bnet, btr, [TrackClosed("SEG-34")]),
        ("baseline/close-SEG-15", bnet, btr, [TrackClosed("SEG-15")]),
        ("baseline/delay-T1-12", bnet, btr, [TrainDelayed("T1", 12)]),
        ("baseline/reduce-SEG-56", bnet, btr, [ReducedSpeed("SEG-56", 0.5)]),
        ("baseline/double-close", bnet, btr,
         [TrackClosed("SEG-34"), TrackClosed("SEG-45")]),
        ("baseline/cancel-T3", bnet, btr, [TrainCancelled("T3")]),
        ("baseline/restrict-T1-SEG-34", bnet, btr,
         [TrainRestricted("T1", "SEG-34")]),
        ("baseline/restrict-T1-strand", bnet, btr,
         [TrainRestricted("T1", "SEG-34"), TrainRestricted("T1", "SEG-45")]),
        ("baseline/add-fits", bnet, btr + [b_extra], []),
        ("baseline/add-conflicts", bnet, btr + [b_extra2], []),
        ("real/empty", rnet, rtr, []),
        ("real/close-BHS-BPL", rnet, rtr, [TrackClosed("BHS-BPL")]),
        ("real/restrict-T101-BHS-BPL", rnet, rtr,
         [TrainRestricted("T101", "BHS-BPL")]),
        ("real/reduce-NRKR-NGP", rnet, rtr, [ReducedSpeed("NRKR-NGP", 0.5)]),
        ("real/delay-T101-30", rnet, rtr, [TrainDelayed("T101", 30)]),
        ("wb/empty", wnet, wtr, []),
        ("wb/close-MYM-BWN", wnet, wtr, [TrackClosed("MYM-BWN")]),
        ("wb/close-BWN-DGR", wnet, wtr, [TrackClosed("BWN-DGR")]),
        ("wb/delay-T1-60", wnet, wtr, [TrainDelayed("T1", 60)]),
    ]


def test_optimized_recompute_matches_golden_byte_for_byte():
    with open(GOLDEN, encoding="utf-8") as f:
        golden = json.load(f)
    scenarios = _scenarios()
    assert {label for label, *_ in scenarios} == set(golden), "scenario set drift"
    for label, net, trains, anomalies in scenarios:
        got = _serialize(recompute_schedule(net, trains, anomalies))
        # round-trip through json so dict/list/tuple shapes match the golden
        got = json.loads(json.dumps(got))
        assert got == golden[label], f"recompute output changed for {label}"
