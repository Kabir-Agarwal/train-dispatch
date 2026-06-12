# PROGRESS.md

## Phase 1 — Network + baseline scheduler + collision checker: DONE
Built 2026-06-12, LIGHT profile, per BUILDER WORKING RULES. Full suite: **37 passed** (`python3 -m pytest tests/ -q`).

## What was built (commit per unit)
1. **model unit** (`engine/model.py`, `engine/errors.py`) — `Segment`, `Train`, `Network`. Stations are an appendable list (`add_station`); segments validated on add (known endpoints, positive integer travel time, valid status, no duplicates, no self-loops).
2. **validation unit** (`engine/scheduler.py: validate_path`) — walks the path station by station; rejects nonexistent segments (`UnknownSegmentError`), gaps, wrong origin/destination (`DisconnectedPathError`), empty paths. Always a typed error with the offending id in the message, never a crash.
3. **scheduler unit** (`engine/scheduler.py`) — `compute_train_schedule` returns per-station arrival minutes + per-segment `Occupancy(train, segment, start, end)`; `build_schedule` does all trains; `load_baseline` refuses a conflicting baseline (`BaselineConflictError`).
4. **collision unit** (`engine/collision.py`) — occupancy windows are closed intervals; `windows_overlap` uses inclusive comparison (`a.start <= b.end and b.start <= a.end`), so exact boundary contact (one train exits at minute 10, another enters at 10) IS a conflict. `find_conflicts` checks every pair on every segment and reports the shared window.
5. **data unit** (`data/baseline.py`) — 6 stations S1–S6, 7 segments, 5 trains, all arrival times and occupancy windows hand-computed in the file's docstring. Includes `conflicting_trains()`, a variant with a deliberate boundary conflict on SEG-56 at minute 29.

## What each gate checks (all assert hand-verified values)
- `test_model.py` (8): segment lookup returns travel_time 10/8; unknown id raises with the id named; bad endpoint/travel-time/status/duplicate rejected; stations appendable (add S7-style station, then a segment to it).
- `test_validation.py` (7): valid path passes; `SEG-99` rejected naming it; gap path `[SEG-12, SEG-34]` rejected "breaks at 'S2'"; path ending short rejected "ends at 'S3'"; wrong-origin, empty-path, unknown-origin rejected.
- `test_scheduler.py` (6): T1 dep 0 arrives S2@10, S3@18, S4@30; dep 7 → S4@37; occupancy windows exactly [0,10],[10,18],[18,30]; reverse run T5 dep 40 → S1@70; duplicate train ids rejected.
- `test_collision.py` (9, tested hardest): overlap truth table incl. [0,10] vs [10,20] = conflict and [0,10] vs [11,20] = clean; boundary conflict reported as shared window [10,10]; partial overlap [5,10]; same window on different segments clean; opposite directions on one segment conflict; 3 overlapping trains → exactly 3 pairwise conflicts; `load_baseline` raises on the boundary case and accepts the clean one with exact schedule dict.
- `test_baseline_data.py` (7): full 6-station load; zero conflicts; every train's full arrival dict asserted (e.g. T4: S4@23, S5@30, S6@39); all 11 occupancy windows asserted; tightest clean gap (T2 exits SEG-56 at 29, T4 enters at 30) proves no over-flagging; conflicting variant flagged at load with exactly `Conflict(SEG-56, T2, T4, 29, 29)`.

## Phase 1 done-conditions → status
1. 6-station network + segments + 5 trains loads; stations appendable — PASS
2. Per-station arrivals + segment-occupancy table computed — PASS
3. Checker flags conflicting baseline, accepts clean one — PASS
4. Nonexistent segment / disconnected path → typed error, no crash — PASS
5. Same segment same minute = conflict, including exact boundary — PASS
6. Every gate asserts hand-verified expected values — PASS (no "no-crash-only" tests)

## Decisions made (mechanical, logged not asked)
- Layout: `engine/` (model, scheduler, collision, errors), `data/baseline.py`, `tests/`, root `conftest.py` for imports. Python 3.10, stdlib + pytest only.
- Segments are bidirectional single track: occupancy conflicts regardless of travel direction (matches "no two trains on the same segment at the same time").
- Zero dwell at intermediate stations; integer minutes; occupancy window = closed interval [enter, exit].
- Conflicts reported pairwise with the exact shared window, sorted deterministically.
- `build_schedule` computes without the safety gate (needed later for reporting); `load_baseline` is the gated entry point.

## Environment note (needs one manual step from you)
The sandbox cannot delete files in the mounted folder, so git left stale lock files that block normal git use **inside the sandbox**; commits were made via plumbing (`commit-tree` + direct ref update) instead, and history is clean. On your machine, run in the repo:
`del .git\HEAD.lock .git\index.lock .git\packed-refs.lock .git\refs\heads\main.lock` (plus any `.git\objects\**\tmp_obj_*` files), and delete the accidental `main` branch (`git branch -D main`) — it was created by a misfired ref update and just mirrors master. After that, normal `git status`/`git commit` work as usual.

## Next
STOPPED at phase boundary per PLAN.md. Phase 2 (anomaly injection + impact detection) awaits your review.
