# PROGRESS.md

## Phase 2 — Anomaly injection + impact detection: DONE
Built 2026-06-12, LIGHT profile. Full suite after Phase 2: **69 passed**.

### What was built (commit per unit)
1. **model extension unit** — `Segment.speed_factor` (fraction of full speed, default 1.0, validated in (0,1]); `effective_travel_time() = ceil(travel_time / speed_factor)`; scheduler now travels at effective time (identical results at full speed, so all Phase 1 anchors still hold).
2. **anomalies unit** (`engine/anomalies.py`) — the 5 admin-injected types from SPEC F2: `TrackClosed`, `TrackBlocked` (same routing effect, different label), `ReducedSpeed(segment, factor)`, `TrainCancelled`, `TrainDelayed(train, minutes)`; combinations = a list. `validate_anomalies` rejects unknown segment/train ids, factor outside (0,1), non-positive delay. `apply_anomalies` returns a NEW effective network; the original is untouched. Closed beats reduced on the same segment; multiple delays add; cancellation beats delay.
3. **reachability unit** (`engine/impact.py: destination_reachable`) — BFS over non-closed segments; visits each station once, so it always terminates (the no-infinite-loop guarantee for stranded detection).
4. **impact unit** (`engine/impact.py: assess_impact`) — classifies every train: `unaffected`, `times_shifted` (new arrivals computed on the effective network, reason includes +N min), `needs_reroute` (path hits a closed segment but an alternative exists — route NOT computed, that is Phase 3), `stranded` (no remaining route; nothing fabricated), `cancelled`. Builds the new occupancy table for still-running trains and reports `conflicts` (detected, NOT resolved — Phase 3). `no_impact` is True only when every train is unaffected and there are no conflicts.
5. **scenario unit** — SPEC F2 adversarial cases on the real baseline. Added `SEG-36` (S3–S6, 11 min), used by NO baseline train, to host the no-impact case (also a future reroute option); the Phase 1 shape gate was updated for the 8th segment — no arrival/occupancy value changed.

### What each new gate checks (hand-verified values)
- `test_model.py` (+2): ceil(12/0.5)=24, ceil(20/0.8)=25, ceil(7/0.9)=8 (rounds up, never down); bad factors rejected.
- `test_anomalies.py` (11): all 5 types validate; SEG-99/T9 rejected by name; factor 0/1/1.5/-0.3 and minutes 0/-5 rejected; SEG-34 closed in the effective network while the original stays open; SEG-56 at half speed takes 18 min; closed beats reduced; delays 5+7 sum to 12.
- `test_reachability.py` (4): S1→S4 reachable; still reachable with SEG-34 closed (via S5); closing SEG-34+SEG-45 cuts S4 off in both directions while S1→S6 survives.
- `test_impact.py` (10): T1+5 → arrivals {S1:5,S2:15,S3:23,S4:35}, others untouched, zero conflicts; T1+12 → conflict (SEG-34, T1, T5, 40, 42) detected, not resolved; T3 cancelled; cancellation beats delay; SEG-34 closure → exactly T1,T5 need reroute; blocked ≡ closed; SEG-34+SEG-45 → T1,T4,T5 stranded with no fabricated times; SEG-26 at 0.8 → T3 S6@37 (+5), no conflict; SEG-56 at 0.5 → T2 S6@38, T4 S6@48, conflict (SEG-56, T2, T4, 30, 38); combination closure+delay classified per train with T4 S6@44.
- `test_scenarios.py` (5): SPEC F2-A1 no-impact (closed AND reduced on unused SEG-36) → `no_impact` True, arrivals equal baseline train by train; F2-A2 harmless +5 delay → no reroute/hold, only T1 shifts; F2-A3 unreachable → stranded + terminates; normal closure case identifies T1/T5.

### Phase 2 done-conditions → status
1. Each anomaly type works (incl. combinations) — PASS
2. No-impact anomaly reports "no impact", changes nothing — PASS
3. Harmless small delay → no reroute/hold, only that train shifts — PASS
4. Unreachable destination → "stranded", no infinite loop, nothing fabricated — PASS

### Decisions (mechanical, logged not asked)
- reduced_speed factor = speed fraction in (0,1); time = ceil(time/factor) so times never round in the train's favour.
- needs_reroute/stranded trains contribute NO occupancy in the impact report (their old path is unusable; Phase 3 assigns new occupancy when rerouting).
- Conflicts created by delays/slowdowns are reported in `ImpactReport.conflicts` and deliberately left unresolved (Phase 3's job).
- New-file writes are done via the sandbox shell after host-side file sync proved unreliable (truncated copies + stale bytecode masked by `__pycache__`; bytecode now redirected to /tmp during test runs).

### Environment note
The sandbox still cannot delete files in the project folder, so `.git\index.lock` exists again (created by a stray `git status`) plus `tmp_obj_*` files under `.git\objects`. Same cleanup as last time before using git on your machine: delete `.git\index.lock` and the `tmp_obj_*` files.

### Next
STOPPED at phase boundary. Phase 3 (recompute engine) awaits your review.

---

## Phase 1 — Network + baseline scheduler + collision checker: DONE (reviewed & approved)
Built 2026-06-12, LIGHT profile. Suite at phase end: 37 passed (now 69 with Phase 2).

### What was built (commit per unit)
1. **model unit** (`engine/model.py`, `engine/errors.py`) — `Segment`, `Train`, `Network`. Stations are an appendable list (`add_station`); segments validated on add (known endpoints, positive integer travel time, valid status, no duplicates, no self-loops).
2. **validation unit** (`engine/scheduler.py: validate_path`) — walks the path station by station; rejects nonexistent segments (`UnknownSegmentError`), gaps, wrong origin/destination (`DisconnectedPathError`), empty paths. Always a typed error naming the offender, never a crash.
3. **scheduler unit** — `compute_train_schedule` returns per-station arrival minutes + `Occupancy(train, segment, start, end)` per segment; `build_schedule` for all trains; `load_baseline` refuses a conflicting baseline (`BaselineConflictError`).
4. **collision unit** (`engine/collision.py`) — occupancy windows are closed intervals; inclusive overlap (`a.start <= b.end and b.start <= a.end`), so exact boundary contact IS a conflict. `find_conflicts` checks every pair on every segment.
5. **data unit** (`data/baseline.py`) — 6 stations S1–S6, segments + 5 trains, all arrival times and occupancy windows hand-computed in the docstring; `conflicting_trains()` variant with a deliberate boundary conflict on SEG-56 at minute 29.

### Phase 1 done-conditions: all 6 PASS (details in git history of this file; key anchors: T1 dep 0 → S4@30, dep 7 → S4@37; boundary case Conflict(SEG-56, T2, T4, 29, 29) flagged; clean 1-minute gap accepted).

### Decisions
- Layout: `engine/` + `data/baseline.py` + `tests/`, root `conftest.py`; Python 3.10, stdlib + pytest only.
- Bidirectional single-track segments; zero dwell; integer minutes; closed-interval occupancy; deterministic conflict ordering.
- `build_schedule` computes without the safety gate (needed for reporting); `load_baseline` is the gated entry point.
