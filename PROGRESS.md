# PROGRESS.md

## Phase 4 — Decision log + LLM phrasing (drift guard): DONE
Built 2026-06-12, LIGHT profile. Full suite after Phase 4: **111 passed**.

### What was built (commit per unit)
1. **log unit** (`engine/decision_log.py`) — `build_decision_log(network, trains, anomalies, result)` produces a structured `DecisionLog`: a trigger string (e.g. `track_closed(SEG-34) + train_delayed(T4, 5 min)`) and one `LogEntry` per train the engine changed — change, engine reason verbatim, destination, arrival, added delay. Crucially, each entry carries fact ALLOW-LISTS (`numbers`, `entities`) enumerating every numeric value and every T*/S*/SEG-* id the engine actually produced for that change; the trigger carries its own. These allow-lists are the contract the phrasing layer is checked against.
2. **guard unit** (`engine/drift_guard.py`) — `verify_text(text, entities, numbers)`: every id mentioned must be engine-produced; ids are stripped first so SEG-12/T2/S6 never leak digits into the number check; every remaining number (incl. decimals like 0.5, signed/suffixed forms like "+5 min") must be an engine value. Returns a violations list; empty = faithful.
3. **phrasing unit** (`engine/phrasing.py`) — per the review note, an interface with two implementations: `TemplatePhraser` (deterministic, zero dependencies — the system is fully functional without any API key) and `LLMPhraser`, which wraps ANY `complete(prompt) -> str` callable via constructor injection, so a real Anthropic client plugs in later with no code changes (`get_phraser(complete)`). `safe_phrase_trigger / _log_entry / _passenger_eta` run EVERY phrased string — from either phraser — through the drift guard; on any violation the text is discarded for the deterministic template and the violations are reported. The LLM can only re-word; it can never introduce a number, and it never computes.

### What each gate checks (hand-verified values)
- `test_decision_log.py` (5): SEG-34 closure logs exactly T1, T2, T5 (T3/T4 untouched), trigger string exact, total −11; T2 entry: reroute, S6@34, +5, allow-lists contain {34, 5} and {T2, T1, S6, SEG-12, SEG-23, SEG-36}; hold scenario logs T2+T4 with {25, 41, 2} and the blocker T2 citable; stranded entries have arrival None (nothing fabricated); trigger allow-lists exact ({T1}, {12}).
- `test_drift_guard.py` (8): faithful text passes; invented number 99 / train T9 / segment SEG-99 / station S8 each caught by name; allowed ids' embedded digits (12, 2, 6) cause no false positives; decimals checked (0.5 ok, 0.7 caught); multiple violations all reported; "+5 min" passes while "+6 min" is caught.
- `test_phrasing.py` (9): exact template strings hand-verified (dispatcher hold line for T4; passenger lines for delayed T4 "41 (2 min later)", early T5 "62 (8 min earlier)", cancelled T3, stranded T1 with "No arrival time"); faithful fake-LLM text accepted verbatim; fake LLM inventing minute 35 / train T8 / "15 minutes" each → violation reported AND output replaced by the exact template fallback; `get_phraser()` → template, `get_phraser(callable)` → LLM; meta gate: across 8 scenarios, every trigger, dispatcher and passenger template line passes the guard (15+ entries exercised).

### Phase 4 done-conditions → status
1. Every engine change produces a log entry (trigger, change, reason, numbers) — PASS
2. LLM-phrased text verified against engine values; no number/claim the engine didn't produce; the guard is a real test — PASS (guard rejects and safely replaces drifting text from a live phraser object, and the same check runs in production via `safe_*`)

### Decisions (mechanical, logged not asked)
- Allow-lists are built from the action's structured fields PLUS ids/numbers appearing in the engine's own reason string (the reason is engine output, so citing it is faithful).
- "Changed" for logging purposes = any action other than a zero-delay `unchanged` (slowed-in-place trains are changes; their times moved).
- Drift guard semantics: ids checked as exact tokens (T\d+ / S\d+ / SEG-\d+), then ids stripped, then all remaining numerals (with decimals) must be engine values. abs(added_delay) is included so "8 min earlier" phrasing of −8 passes.
- On violation `safe_*` falls back to the template rather than raising — the demo must keep running; violations are returned for display/logging.
- `LogEntry`/`_entry` is generic over any action, so Phase 5's passenger view can build fact packs for UNCHANGED trains too (passenger ETA must exist for every train, not just changed ones).

### Environment note
Unchanged: stale `.git\index.lock` + `tmp_obj_*` under `.git\objects` need manual cleanup on your machine.

### Next
STOPPED at phase boundary. Phase 5 (admin view + passenger view, the demo moment) awaits your review.

---

## Phase 3 — Recompute engine: DONE
Built 2026-06-12, LIGHT profile. Full suite after Phase 3: **89 passed**.

### What was built (commit per unit)
1. **routes unit** (`engine/routes.py`) — exact enumeration of all simple paths between two stations over open segments (network is tiny), sorted fastest-first by effective travel time; `path_stations` for human-readable "via" strings.
2. **slot unit** (`engine/recompute.py`: `try_schedule`, `min_hold_schedule`, `blocking_trains`) — smallest origin-hold that makes a path conflict-free against the growing occupancy table. Inclusive boundary is enforced here too (hold 1 leaving a shared minute is rejected; gate proves hold must be 2). Hold search is bounded by the table's last exit minute, so it always terminates. `blocking_trains` answers "who is in the way" for reasons.
3. **recompute unit** (`engine/recompute.py`: `recompute_schedule`) — greedy, deterministic: trains placed in baseline-departure order against the full table-so-far (so second-order conflicts are structurally impossible to miss). A train whose original path+timing is conflict-free keeps it untouched (no churn, no over-reaction). Otherwise every open path is tried with its minimal hold and the earliest arrival wins (ties: original path, then less hold). Collision-free is a hard constraint of the search — a colliding "optimal" move is unrepresentable, so safety beats delay by construction. Final whole-table re-check raises if a conflict ever survived (it cannot). Output per train: `unchanged` / `depart_delayed` / `hold until minute X` / `reroute via [path]` / `cancelled` / `stranded`, each with arrivals, added delay vs baseline, and an engine-sourced reason naming blockers or closed segments. `total_added_delay` is the net sum over running trains.
4. **scenario unit** (`tests/test_f3_scenarios.py`) — the SPEC F3 normal + all three adversarial cases on the real baseline, every minute hand-computed.

### What each gate checks (hand-verified values)
- `test_routes.py` (5): S1→S4 has exactly 7 simple paths, fastest [SEG-15,SEG-45]=22 min; S4→S6 has 6, fastest 16 min; SEG-34 closure leaves exactly 3; unreachable → empty list.
- `test_slots.py` (4): vs T2 on SEG-56[22,31], T4's minimal hold is exactly 2 (hold 1 → shared minute 31 → rejected); empty table → hold 0; blockers named.
- `test_recompute.py` (5): no-impact closure (SEG-36) → all `unchanged`, schedule identical to baseline, total 0; cancelled T3 excluded from table, others untouched; SEG-34+SEG-45 → T1/T4/T5 `stranded` honestly, T2/T3 run; T1+5 → `depart_delayed`, S4@35, total +5; unknown segment/train → typed errors.
- `test_f3_scenarios.py` (6), each ending in a full-table zero-conflict assert:
  - **F3 normal + adversarial 2** (SEG-34 closed): T1 reroutes S1-S5-S4, S4@22 (−8); that steals SEG-15 from T2 → second-order conflict resolved by T2 rerouting S1-S2-S3-S6, S6@34 (+5), reason names T1; T3/T4 untouched; T5 reroutes S4-S5-S1, S1@62 (−8); net −11; SEG-15 and SEG-45 windows strictly sequenced.
  - **F3 adversarial 1** (SEG-15 closed): SEG-12 is S1's only exit; T1 [0,10] then T2 [11,21] — never both; T2 departs 11, S6@40 (+11); everyone else unchanged.
  - **F3 adversarial 3** (safety beats delay): T2's delay-optimal move (depart 5, S6@34) is PROVEN to collide with T1 on SEG-12 via `try_schedule` → None; engine's chosen schedule is the slower safe one (S6@40).
  - **Pure hold**: T2+2 → T4 holds until 25 on its own path (boundary minute 31 forces hold 2, not 1), S6@41 (+2); T5 stays unchanged at 70 even though a "faster" detour exists — no over-reaction.
  - **Delayed leader**: T1+12 keeps its path (S4@42); follower T5 reroutes (S1@62) because holding would cost 73 vs 62; total +4.
  - **Reduced-speed cascade** (SEG-56 at 0.5): T2 slowed in place S6@38 (+9); T4 reroutes S4-S3-S6 departing 31 after T1 clears SEG-34, S6@54 (+15); T4's new SEG-34 window pushes T5 onto the S4-S5-S1 detour (−8); net +16; SEG-34 windows sequenced [18,30]/[31,43].

### Phase 3 done-conditions → status
1. Closure reroutes affected train via valid alternative; others untouched unless needed — PASS
2. Two trains needing one track are sequenced, never both on it — PASS
3. Second-order conflicts from a reroute are resolved (whole table re-checked) — PASS
4. Delay-optimal-but-colliding move rejected for the slower safe option — PASS (proven collision vs chosen schedule)
5. Clear per-train action + total added delay — PASS
6. Gates assert collision-free AND hand-verified expected actions — PASS

### Decisions (mechanical, logged not asked)
- Priority order = baseline departure (then id); admin delay does not change priority.
- Holds are origin-holds only (no mid-route station holds) — sufficient for the demo model where the schedule is recomputed from departure.
- "Unchanged-if-feasible" rule: a conflict-free original plan is never churned onto a faster detour; optimization happens only for trains that are blocked, delayed, slowed, or closed-out. (This is what SPEC's "others adjusted only if needed" / "don't over-react" requires; it also means added delay can be negative for rerouted trains when the detour is shorter — `total_added_delay` is reported net.)
- `total_added_delay` excludes cancelled/stranded trains (they have no arrival).
- Gate-fix loop note (Loop limits): scenario gate attempt 1 of 5 failed — root cause was my own incomplete hand expectation (forgot T5's later SEG-12 window in one assert), not engine behaviour; fixed in attempt 2, green. No engine code changed after its first gate run.

### Environment note
Unchanged from Phase 2: stale `.git\index.lock` + `tmp_obj_*` files under `.git\objects` need manual deletion on your machine (sandbox cannot delete in the mount).

### Next
STOPPED at phase boundary. Phase 4 (decision log + LLM phrasing with drift guard) awaits your review.

---

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
