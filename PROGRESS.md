# PROGRESS.md

## Engine optimization (branch real-railway) — placement/hold search: ~2.6–3.6s → ~0.37–0.48s, behavior-identical
Built 2026-06-13. master untouched at cd37586. Suite: **190 passed** (189 + 1 byte-identical golden gate). Determinism preserved (5 identical recompute runs). **No behavior change** — proven below.

### What changed (`engine/recompute.py` only; routing/anomalies/model untouched)
The WB probe showed the cost was NOT the DFS route enumeration (~340 ms) but the placement/hold search: `_choose × min_hold_schedule` re-ran `find_conflicts` over the whole growing table ~29k times. Two correctness-preserving fixes:
1. **Incremental conflict index** (`index_table` + `_occs_conflict`/`_occs_blockers`). The committed table is indexed once per train placement (segment → intervals); a candidate is tested only against the segments it uses. This is provably equivalent to `find_conflicts(table+occs)` being non-empty — the committed table is already conflict-free and a simple path's occupancies are on distinct segments, so the only conflicts that function could ever report are candidate-vs-committed cross pairs. Removed the ~29k full-table O(N²) rescans.
2. **Analytic min-hold** (`min_hold_schedule`). Each committed window on a segment the train uses forbids a closed interval of holds `[committed.start − occ.end, committed.end − occ.start]`; the answer is the smallest `h ≥ 0` in no forbidden interval, found by a sort+sweep instead of scanning holds minute-by-minute up to ~900. Returns the identical minimal hold the old loop returned.
3. **(Not needed.)** Branch-and-bound/top-K in `_choose` was reserved for "still over 500 ms" — we're under, so it was not applied.
The helper functions accept either a prebuilt index (recompute's fast path) or a raw table (direct callers/`test_slots.py`), via `_as_index`, so the existing unit tests pass unchanged.

### Behavior-identical — gated
`tests/_golden_gen.py` froze recompute outputs from the PRE-optimization engine across **20 fixed scenarios** (baseline + real corridor + West Bengal: closures, reduced-speed, delay, cancel, restriction, strand, add-train) into `tests/recompute_golden.json`. `tests/test_recompute_golden.py` asserts the optimized engine reproduces every one **byte-for-byte** (actions/path/depart/arrivals/added_delay/reason + totals + occupancy table). All 189 prior tests stay green; the collision-free re-check at the end of `recompute_schedule` is unchanged — safety stays absolute.

### RE-PROBE result (probe_wb.py, WB worst-case closure MYM–BWN at the densest junction)
Before: **~2.6–3.6 s**.  After: **~0.37–0.48 s** (median ~0.4 s; 4 reroutes, 0 stranded, 0 conflicts). ~6–8× faster.
Of the ~400 ms remaining, **~340 ms is now the DFS route enumeration** (`all_open_paths`, called once per train — untouched); the placement/hold search itself is now ~25–130 ms.

### VERDICT: feasible — UNDER 500 ms, ready to wire the WB UI.
Note: headroom is thin and the DFS enumeration is now the dominant remaining cost (one run touched 476 ms). If we want more margin later, the next lever is capping route enumeration (k-shortest / A* with pruning) — the user's original guess, which only becomes the bottleneck now that the placement search is fixed. Not required to proceed.

### STOPPED at the boundary — optimization done + gated, new timing reported; WB UI not started, awaiting go-ahead.

---

## West Bengal PERFORMANCE PROBE (branch real-railway) — data layer only, NO UI: result = STOP
Built 2026-06-13. Data layer only; `engine/` and the UI are UNCHANGED; master untouched at cd37586. Suite: **189 passed** (185 + 4 WB data gates). NO WB UI was built — the probe verdict is STOP (see below).

### Dataset (`data/west_bengal.py`, gated in `tests/test_west_bengal_data.py`)
A faithful-but-approximate WB state network assembled from public IR route knowledge (en.wikipedia Howrah/Asansol/Kharagpur Jn + Sealdah-section articles): Howrah–Bardhaman MAIN (via Bandel) + CHORD (via Dankuni); Sealdah main/north + Naihati–Bandel chord; Bardhaman–Asansol + Andal–Sainthia link; Katwa–Azimganj–Nalhati–New Farakka loops; Sahibganj/Rampurhat loop; Howrah–Kharagpur; Kharagpur/Adra/Purulia/Bankura; northern Malda–NJP–Alipurduar–New Cooch Behar + Dooars loop. Same engine model, same minutes==km convention as the real corridor — no engine change.

### 2) Size + density
**50 stations, 58 segments, 12 representative trains. Densest junction = Barddhaman Jn (BWN), degree 5** (Bandel, Panskura, Ranaghat, Azimganj next at degree 4). ~11 independent cycles (chords/loops) — a genuinely meshy state graph.

### 3) Worst-case closure recompute (probe_wb.py)
Closed the busiest BWN-incident segment **MYM–BWN** (used by 3 trains) and timed one full `recompute_schedule`. Stable across runs: **~2.6–3.6 s** (4 reroutes, 0 stranded, 0 conflicts).

### 4) VERDICT: OVER the ~500 ms ceiling by 5–7× → **STOP. Do not wire WB into the UI yet.**

### Where the time goes (cProfile — NOT the DFS)
The user's guess (A*/pruning to replace full DFS) is **not** the bottleneck: route enumeration (`all_open_paths`/DFS) is only ~0.8 s and path counts are modest (≤106 per OD). The cost is the **placement/hold search**: `_choose` evaluates every candidate path, and `min_hold_schedule` scans holds minute-by-minute, each step re-running `find_conflicts` over the ENTIRE growing occupancy table — **~29,000 full-table conflict scans** (`find_conflicts` 2.6 s tottime, `compute_train_schedule` 2.4 s). Quadratic-to-cubic blow-up that scales with route length (WB routes reach minute ~900) × candidate count × train count.

### Proposed engine change (for a separate, authorized step — NOT done here)
1. **Incremental conflict index instead of full rescans.** Index the committed table once per placement (segment_id → sorted intervals); test only the candidate's own segments against it. Removes the 29k O(N²) `find_conflicts` rebuilds — the single biggest win.
2. **Analytic min-hold, not a minute-by-minute loop.** For a path, compute the earliest conflict-free departure directly (max over its segments of "latest overlapping committed end + 1"); jump there instead of looping +1 min up to ~900.
3. **Branch-and-bound / top-K candidates in `_choose`.** Candidates are already sorted fastest-first; stop once a candidate's no-hold arrival can't beat the best found, and cap to the K shortest (a 12th-fastest 900-min detour can never win).
(1)+(2) alone should bring this comfortably under 500 ms; collision-free stays a hard constraint throughout. Determinism preserved (tie-breaks unchanged). This would be an `engine/` change on real-railway only — master stays at cd37586.

### STOPPED at the probe boundary — number reported, fix proposed; WB UI not started, awaiting go-ahead.

---

## Live actions (branch real-railway) — per-train restriction + add-train + one-action-per-row controls: DONE, awaiting visual pass
Built 2026-06-13. Full suite: **185 passed** (165 prior + 9 engine gates + 11 app/UI gates). Determinism re-checked (5 identical recompute runs); browser-verified end-to-end with the preview tool (add-train and restrict: preview → apply, ghost reroute, board "added" tag, humanized anomaly line, schematic map intact: 21 trunk + 6 loop dots).

### THIS ROUND TOUCHES THE ENGINE (intentional — a relaxation of the prior "engine zero-diff" rule)
master is untouched and **still at cd37586**; the real-railway branch now diverges from master in `engine/` ON PURPOSE because features 2 and 3 are genuinely engine features. `git diff master -- engine/`: 4 files, +62/-11.
- **`engine/routes.py`** — `all_open_paths(net, o, d, forbidden=frozenset())`: optional per-train forbidden segment set, skipped exactly like a closure but only for that call. Default empty ⇒ every existing caller is unchanged.
- **`engine/anomalies.py`** — new `TrainRestricted(train_id, segment_id)` (does NOT change global segment status — `apply_anomalies` leaves it open for everyone else); `restricted_segments()`; validation branch.
- **`engine/recompute.py`** — per-train `forbidden = restricted.get(id)`, passed to `all_open_paths`; `original_open` also fails on a forbidden planned segment; reroute reason "this train is barred from segment(s) …"; strand note when a restriction cuts all routes. Plus: `recompute_schedule` now skips `validate_anomalies` ONLY when the anomaly list is empty (the add-train path), reproducing the conflict-free baseline. `validate_anomalies` itself still rejects an empty list (its direct test stays green).
- **`engine/decision_log.py`** — `describe_anomaly` for `TrainRestricted`.
Determinism preserved: forbidden is membership-checked, reason lists follow `train.path` order, `_next_train_id` uses `max()` (order-independent). The whole-table collision re-check is unchanged — collision-free stays absolute.

### Feature 2 — per-train path restriction (gated, `tests/test_restrictions_and_addtrain.py`)
Restricted train avoids the segment and reroutes via an allowed path; an unrestricted train still uses that segment; restricted train strands when no allowed path remains; restriction is per-train, never a global closure; real-corridor case reroutes T101 onto the Bina–Itarsi loop while T102 keeps the trunk. All conflict-free.

### Feature 3 — add a train live (gated)
Admin gives origin/destination/departure; the engine builds a fastest open path and schedules it collision-free against existing traffic (the new train holds/reroutes as needed — existing higher-priority trains keep their plans). A train that fits runs unchanged; one that contends adapts; one with no route is **reported (DispatchError "no available route"), not forced** — caught before commit, state untouched. New ids are deterministic `T<n>` (baseline → T6, real → T109). Cleared on reset.

### App + UI (`app/state.py`, `app/server.py`, `app/static/index.html`; gated in `tests/test_live_actions_ui.py`)
- `inject(payloads, new_trains=[])` and `preview(payloads, new_trains=[])` are the single mutation/preview path for anomalies AND added trains (all-or-nothing). `/api/inject` and `/api/preview` accept a `new_trains` channel. Snapshot exposes `added_train_ids`.
- **Controls redesigned (feature 1):** "Report a problem" is now ONE labeled action per row, vertically stacked, generously spaced — Close / Block / Reduce-speed (factor labeled "0.5 = half speed") / Delay / Cancel / **Restrict a train from a track** / **Add a new train** / Reset, each with its own plain-name dropdown(s) and a one-line caption. No raw codes anywhere (segment dropdowns read "Agra Cantt – Dhaulpur"; trains read "T101 · New Delhi → Nagpur").
- Ghost preview, "How this works", legend, plain summary, real names, and the schematic real-corridor map all keep working for the new actions (added trains get an "added" badge on the board; the anomaly line is humanized via the generalized `withNames`).

### STOPPED at the boundary — engine + app + UI built and gated; user does the visual pass.

---

## Phase C (branch real-railway) — real-corridor UI / display skin: DONE, awaiting visual pass
Built 2026-06-13. Full suite: **165 passed** (159 from Phase B + 6 new UI gates). master untouched; `engine/` **zero diffs in history and working tree** — verified again this round (`git diff master -- engine/` empty). Phase C is display-layer ONLY: the only real content changes are `app/static/index.html`, one line in `run_ui.py`, and the new gate `tests/test_real_corridor_ui.py`. No engine, scheduler, anomaly, state, or data change.

### What changed (display layer only)
- **Geo-positioned all 27 real stations** on the India outline (`REAL_COORDS` in the page). Coords come from an affine fit of (lon,lat) onto the existing Delhi/Bhopal/Nagpur anchors, then magnified about the corridor centroid with a 17px minimum spacing so all 27 labels stay legible. Relative geography is preserved: Delhi north, the NDLS–Jhansi–Bina trunk running south to Nagpur, and the Bina–Saugor–Damoh–Katni–Jabalpur–Pipariya loop **bulging east** so the **BINA–ET diamond** reads as two distinct lines (trunk via Bhopal vs the eastern loop).
- **Dense-map (compact) render mode** (`stations.length > 8`): smaller dots (r=5), name-only labels alternating left/right, no per-segment id labels, no in-dot codes. The 6-city map is byte-for-byte unchanged (still r=14 dots, codes in dots, seg labels).
- **Both display attributes on the board**: loco class + driver employee number render as a sub-line under each train id (`WAP-7 · DRV-4102`), straight from the snapshot's `train_attrs`. Absent for the 6-city (no attrs) — sub-line simply omitted.
- **`withNames()` generalized** from `\bS\d+\b` to *any* known station code (keys of `display_names`). The real corridor's prose (reasons, decision log, trigger, passenger text) now humanizes `NGP`→Nagpur, `ET`→Itarsi Jn, reroute chains `NDLS-MTJ-BFP-…`→full names, and segment ids `BHS-BPL`→`Vidisha-Bhopal Jn`. 6-city behavior is a strict subset (S1→Delhi unchanged; `SEG-12` and train ids `T101` left alone — not display_names keys).
- `run_ui.py --real` now announces "REAL 27-station Indian Railways corridor".

### Kept working (regression-gated on the real page)
Ghost preview (`/api/preview`, Apply/Cancel), the "How this works" panel, the legend, the India outline + illustrative caption, the plain summary after Apply, the five anomaly controls + Reset — all still served, asserted by `test_six_city_ui_features_still_present_on_real_page`.

### The new gate (`tests/test_real_corridor_ui.py`, 6 tests)
Serves `AppState(dataset="real")` over the real HTTP path and asserts: all 27 stations have a baked-in map coordinate; the loop/diamond stations are placed; `loco_class` + `driver_employee_no` are wired into the page; the `/api/state` snapshot exposes 27 stations + 8 trains' attrs (DRV-/WAP-WAG-WDM); every station code maps to a unique real name (so no raw codes leak through `withNames`); and the 6-city features survive.

### Phase C cleanup (after the first visual pass) — DONE, awaiting second visual pass
Two problems from the visual pass, both display-layer only. Suite still **165 passed**; `engine/` zero-diff vs master re-verified. Browser-verified with the preview tool (real + baseline servers, geometry queried in-page).

**Problem 1 — real map cluttered, Bina–Katni diamond not legible.** Replaced the India-outline geographic layout (for >8-station networks) with a clean **schematic** metro-map: the trunk is one straight vertical line (New Delhi top → Nagpur bottom, even 29px spacing); between the junctions Bina Jn and Itarsi Jn the trunk runs straight DOWN (main line via Bhopal) while the eastern loop (Saugor–Damoh–Katni–Jabalpur–Narsinghpur–Pipariya) branches to a parallel line and rejoins at Itarsi — so the BINA–ET diamond reads as two obvious branches. The India silhouette is hidden for this view; a sub-caption explains the two routes. Station names sit OUTWARD (trunk-left, loop-right), train markers INWARD. Verified in-page: 27 labels, **0 label overlaps, 0 train↔station-name clashes**, 21 dots at x=200 + 6 at x=395. The 6-city geographic map is byte-for-byte unchanged (verified: outline shown, r=14 dots, in-dot S-codes, seg labels, original caption).

**Problem 2 — "Report a problem" controls confusing.** Rebuilt as an explicit two-step flow: **Step 1** pick what's affected (a track *or* a train, labeled dropdowns), **Step 2** choose what happened (actions grouped "to the selected track" / "to the selected train", each button with a one-line plain caption). The speed input is now labeled "speed factor (e.g. 0.5 = half speed)"; delay input labeled "by (minutes)". The segment dropdown shows **plain names only** ("Agra Cantt – Dhaulpur"), no raw codes; train dropdowns show "T101 · New Delhi → Nagpur". (Dead `fillOnce` removed.)

### STOPPED at Phase C boundary — UI built + gated; user does the visual pass and records.

---

## Phase B (branch real-railway) — real diamond network, reroutes + ghost on real data: DONE, awaiting review
Built 2026-06-13. Full suite: **159 passed**. master untouched (= origin/master = cd37586, verified); `engine/` zero diffs in history and working tree, verified again this round.

### Restore note (option b, user-directed)
A parallel session's Phase A (Mumbai CSMT–Nagpur, commit 82077b6 — its PROGRESS section below is retained as a record but is SUPERSEDED) was parked: module -> `data/real_corridor_user_draft.py`, gates -> `data/real_corridor_user_draft_tests.py`. The GT-corridor Phase A files (689b0c6) were restored (commit 558fee2) and the suite returned to 147 before Phase B began.

### Network (counts for review)
**27 stations, 27 segments, 8 trains.** Trunk: NDLS->NGP, 21 stations, real km (12616 GT Express). NEW loop: the real Bina–Saugor–Damoh–Katni–Jabalpur–Itarsi line, 6 new stations, 7 segments, real km from the 11271 Vindhyachal Express cumulative table (75/77/109/91/84/94/68), three legs independently confirmed by the 18234 Narmada Express (84/94/67-68). BINA<->ET is now a REAL diamond: trunk 230 min vs loop 598 min. Trains: T101..T108 (renamed from R-series — the drift guard's id grammar is T/S/SEG; R6's digit leaked as an "invented number" in passenger text, caught by smoke check; renaming beats touching the engine tokenizer). New: T106 NDLS->JBP via loop dep 320, T107 ET->BINA via loop dep 100, T108 JBP->ET dep 700 — all pairwise hand-verified collision-free in baseline.

### Does reroute + ghost preview work on real data? YES — gated.
- `track_closed(BPL-RKMP)`: T101 REROUTES via the loop (NGP@1458, +368), T103 reroutes (NGP@1063, +644) — the Phase A outcome for the same closure was "stranded".
- Ghost preview == apply on the real network (trains, totals, deltas identical; T101 1090->1458 in the delta table; segment_changes exactly {BPL-RKMP: closed}); passenger view consistent (eta 1458, guard-clean).
- All 5 anomaly types gated with hand-verified values: blocked==closed; reduced_speed(NRKR-NGP, 0.5) shifts T101/T104 +86 in place; harmless delay (T108+10) shifts only T108; cancellation excludes cleanly; double closure (BPL-RKMP + PPI-ET) strands honestly (both routes cut).

### Anomalies that "misbehave" (the honest part — engine right, intuition wrong)
1. In the closure scenario, opposing loop train T107 is held until dep **1162** (+1062 min): with T103 and then rerouted T101 streaming through the single-track loop from the other side, every earlier slot collides somewhere (the JBP crossing squeeze), and the engine's holds are origin-only — it cannot park a train at an intermediate station to let traffic pass. Safe and correct, but a costly real-world plan; mid-route station holds would be the Phase C improvement if wanted.
2. In the reduced-speed scenario, slowing ONE segment (NRKR-NGP) produced a knock-on conflict two segments away: T104's +86 tail shift moved its AMLA-PAR window into T103's path, forcing T103 to hold 53 min (+139). The whole-table re-check caught what my first hand pass missed — both my scenario expectations were corrected to engine truth on attempt 2 of 5 after root-causing each number.

### Performance
Closure recompute (the heaviest case: 2 reroutes + a 1062-min hold search over a ~100-window table): **36 ms**. Full suite 4.6 s. No scaling concern at this size.

### Display
`AppState(dataset="real")` + `python run_ui.py --real` serve the real network (27 stations, city names, ellipse layout for new stations); snapshot carries `train_attrs` (driver_employee_no + loco_class, e.g. WAP-7) — display-only, absent from engine objects (gated). NOTE (resolved in Phase C, above): at Phase B the UI did not yet render the two attrs or geo positions for the 27 stations — Phase C added `REAL_COORDS`, the compact map mode, and the board attr sub-line.

### STOPPED at Phase B boundary.

---

## Phase A (branch real-railway) — real corridor data: DONE, awaiting review
Built 2026-06-13. Full suite: **149 passed** (all 140 master tests green + 9 corridor gates). Branch: real-railway only; master untouched at cd37586. `engine/` has ZERO diffs on this branch.

### Data source
Public Indian Railways "Train_details" timetable dataset — `aaryanrr/Railway-Management` (`Assets/Train_details.csv`, 186k rows, a per-station cumulative-distance schedule mirrored from data.gov.in). Downloaded, parsed, and a single corridor extracted into a self-contained module; the raw CSV is gitignored, not committed. Corridor chosen (selection delegated to me by the brief): **train 12011 Mumbai CSMT -> Nagpur** (Central Railway) — 18 stations CSMT, DR, TNA, KYN, IGP, NK, MMR, JL, BSL, MKU, SEG, AK, MZR, BD, DMN, PLO, WR, NGP; real cumulative km 0..841.

### Decisions confirmed with user this session
- **Travel time source:** real timetable running minutes (this-station arrival − previous-station departure) — the authentic "real driving times", e.g. Kalyan→Igatpuri 125 min (real Kasara ghat). Not distance÷assumed-speed.
- **Second display-only train field:** locomotive number (alongside driver employee number).
- Replaced a stale earlier draft of `data/real_corridor.py`/`test_real_corridor.py` (a Delhi→Nagpur GT-route attempt using distance==minutes, driver field only) — superseded by the above; reversible in git.

### What was built
`data/real_corridor.py` — 18 stations, 17 segments. Segment distance = consecutive cumulative-km differences (all positive, sum 841). Segment `travel_time` = real running minutes (16..125). 5 trains, provably collision-free same-direction set (R1 CSMT→NGP dep 0; R2 CSMT→NGP dep 130; R3 CSMT→BSL dep 300; R4 KYN→NGP dep 700; R5 CSMT→NGP dep 900 — every pair spaced > the binding 125-min ghat segment, so zero conflicts). Display-only `DISPLAY_NAMES` (code→city), `STATION_KM`, `SEGMENT_KM`, and `TRAIN_DISPLAY` (`driver_emp` + `loco_no`, e.g. WAP-7 #37018) — none read by the engine; the engine `Train` carries neither field.

### Gates (`test_real_corridor.py`, 9 — all value-asserting)
Shape (18/17/5); loads with zero conflicts (73-window occupancy table); travel_times == real RUN_MINUTES and all > 0; distances positive + hand-checked (8, 25, 79; NGP anchor 841; differences tile to 841); one connected component (all 18 reachable from CSMT); arrivals hand-verified (full R1 walk CSMT@0..NGP@790; R2 NGP@920, R3 BSL@713, R4 NGP@1424, R5 NGP@1690); tightest clean headway on the 125-min ghat is 5 minutes (R1 exits 191, R2 enters 196) with full window list asserted; display fields present but NOT on engine objects + name bijection (18 unique); perf measured.

### Performance at this size (the question Phase A had to answer)
load+schedule ~0.2 ms; full `find_conflicts` over the 73-window table **0.045 ms**; `all_open_paths` CSMT→NGP **0.100 ms** (1 path). The collision checker is NOT the bottleneck — comfortable headroom. The real scaling risk is route enumeration (DFS over simple paths), which is trivial here only because the corridor is linear; dense hub regions in this dataset (22 nodes / 40–55 edges) would explode it, so any future alternate routes must be added sparingly as genuine parallel lines, not express skip-stops.

### Honest limits to flag at review
- The corridor is LINEAR (one real line, no parallel route): a track closure strands everything beyond it — reroute can never trigger. For reroute demos on real data we should add ONE genuine parallel line (the dataset has real candidates, e.g. the Ernakulam–Kayankulam Kottayam-vs-Alleppey loop on a southern corridor), chosen to stay sparse so route enumeration stays cheap.
- Baseline is same-direction only: no clean opposite-direction full-corridor slot exists while 5 trains saturate the single track (confirmed by search) — true single-track behaviour; crossing/sequencing is a later-phase concern.

### STOPPED at Phase A boundary
Per instruction: not proceeding to more trains or anomalies until performance and mapping are confirmed. App is NOT yet rewired to this corridor (still on the 6-city baseline) — that wiring is the next step on your go-ahead.

---

## Freeze round — Indian map skin + plain-language layer (display only): DONE
Built 2026-06-12. Full suite: **140 passed** (all 132 prior tests green). ZERO engine/scheduler/anomaly changes — `engine/` untouched this round (verifiable in the two commit diffs).

### What was built (commit per unit)
1. **display unit** (`app/display.py`) — city-name mapping with internal ids unchanged everywhere in engine and tests: S1=Delhi, S2=Bhopal, S3=Nagpur, S4=Howrah, S5=Mumbai, S6=Chennai (adjusted from the suggested order so the S1-S2-S3 chain matches the real Delhi–Bhopal–Nagpur trunk and S1-S5 / S5-S6 the Delhi–Mumbai / Mumbai–Chennai corridors — fewer crossing lines); unmapped ids fall back to the raw id (a 7th station can never break the UI). Plus `safe_summary`: a one-line plain-language result ("3 trains rerouted — largest extra delay 5 min.") computed ONLY from engine actions (counts + max positive added delay) and verified by the same drift guard as all phrased text. Served via snapshot as `display_names` and `summary_text`.
2. **skin unit** (`app/static/index.html`, Sonnet subagent per the model steer; integration + gates in main session) — portrait map with a single-path stylized India outline (light grey), stations at rough geographic positions labeled with city names; ALL rendered station ids (board, reasons, log, passenger, deltas, segment picker "SEG-34 (Nagpur–Howrah)") display as city names via one client-side transform; caption "Illustrative network inspired by Indian Railways"; collapsible "How this works" panel (5 plain sentences); map legend (green=open, red dashed=closed, faded dashed=predicted, dot=train); anomaly section retitled "Report a problem"; `#plain-summary` band shows the post-Apply summary.

### Gates
- `test_display.py` (7): mapping is a bijection covering exactly the network's stations, round-trips id→name→id, falls back safely; summary hand-verified per scenario (closure → "3 trains rerouted — largest extra delay 5 min."; T2+2 → "1 train held, 1 departing late — largest extra delay 2 min."; double closure → "3 trains stranded — no extra delay."; no-impact → "No changes needed…"; baseline → empty); summary passes the drift guard and a tampered "7 min" is caught as an invented number; display_names served in snapshot.
- `test_ui_page.py` (+1): served page contains india-outline, the exact caption, How this works, Report a problem, plain-summary, display_names, Howrah, Chennai — alongside every previous marker (all still asserted).
- Boot smoke over HTTP: display_names served (Delhi/Howrah), baseline summary empty, post-apply summary exactly "3 trains rerouted — largest extra delay 5 min."

### Decisions
- City mapping adjusted (permitted by the instruction) for geometric fit; logged above.
- Summary counts derive deterministically from engine actions in the display layer; its allow-list is {its own counts, max delay}, so the guard genuinely binds it.

FEATURE FREEZE: no further build rounds; next step is the user's demo recording.

---

## Phase 6 — Map view + ghost preview (stretch): DONE
Built 2026-06-12, LIGHT profile. Full suite after Phase 6: **132 passed** (all 124 prior tests still green).

### What was built (commit per unit)
1. **docs** — README (overview, run command, 5-line architecture summary); .gitignore already covered `__pycache__`/`*.pyc` since Phase 1.
2. **fix unit** — encoding bug root-caused: the server read index.html with the platform-default encoding, which is cp1252 on Windows → "â€¢"/"Î”" mojibake; now `read_text(encoding="utf-8")`. Anomaly list deduped on inject (exact-duplicate anomalies ignored; frozen dataclasses compare by value).
3. **preview unit** (`app/state.py: preview`, `POST /api/preview`) — GHOST PREVIEW runs the SAME `recompute_schedule` as inject on (active + pending) anomalies but mutates nothing; returns predicted trains/log/segment-status changes plus a delta table (per train: old→new action, old→new arrival, delay change, changed flag) computed against the CURRENT state. Apply = the existing `/api/inject` path; Cancel = client-side discard. Also added `station_times` (ordered station/minute pairs) to every train view for the map.
4. **map unit** (`app/static/index.html`) — full-width SVG "Network map" above the tables: fixed coordinates for S1–S6 with automatic ellipse placement for any appended station; segments color-coded by live status (closed = dashed/faded red); trains as labeled dots interpolated piecewise-linearly along their station_times; Play/Pause + time slider (0..max arrival, ~6 sim-min/s); ghost overlays render predicted segment changes and changed train routes as faded dashed shapes, with the Predicted-changes delta panel + Apply/Cancel beneath.

### Delegation note (model-usage steer)
The map/ghost UI page (routine, well-specified front-end work) was written by a **Sonnet subagent** against a fixed API contract and hard marker list; integration, all engine/state/server code, and all gates were done in the main session. Subagent output was size- and tail-verified before install, then run through the full suite.

### What each gate checks (hand-verified values)
- `test_ui_page.py` (+2): served bytes decode as UTF-8 with real "Δ delay" and "•" glyphs and NO "â€" mojibake signature; map/preview controls present (Network map, time-slider, /api/preview, Apply, Cancel, station_times).
- `test_app_state.py` (+1): injecting track_closed(SEG-34) three times + once in a combo yields ONE closure in the active list.
- `test_preview.py` (4): **preview == apply** — predicted trains, totals and phrased log lines are identical to the snapshot after injecting the same payload (same engine recompute, gate-proven); delta table hand-verified (T1 30→22, −8, changed; T3 32→32 unchanged; segment_changes exactly {SEG-34: closed}); preview stacks on active anomalies (post-closure T4 39→44, +5, no new segment change) without touching state; station_times exact for T1.
- `test_http_end_to_end.py` (+1): preview over real HTTP applies nothing, then inject returns byte-identical train views and total.
- Boot smoke: served page 200; live /api/preview returned {SEG-34: closed} and T1→22.

### GitHub status (Task 1)
Repo verified public at https://github.com/Kabir-Agarwal/train-dispatch. default_branch is "main", NOT "master" — fix: Settings → General → Default branch → switch to master → Update. The remote currently shows only the auto-generated README commit on main, so the earlier master push likely did not land; one `git push -u origin master` from this folder ships full history + README + .gitignore + Phase 6.

### Environment note
Unchanged: stale `.git\index.lock` + `tmp_obj_*` under `.git\objects` need manual cleanup on your machine before local git use.

### Next
Stopped after Phase 6 as instructed.

---

## Phase 5 — Admin view + passenger view (the demo moment): DONE
Built 2026-06-12, LIGHT profile. Full suite after Phase 5: **124 passed**.

### How to run the demo
`python3 run_ui.py` — starts the local server on port 8000 and opens the browser (options: `--port`, `--no-browser`). No frameworks, no API key, stdlib only.

### What was built (commit per unit)
1. **facts unit** — `fact_entries_for_all_trains`: fact packs (with drift-guard allow-lists) for EVERY train, changed or not, so the passenger view always has an engine-sourced ETA.
2. **state unit** (`app/state.py`) — `AppState`, the single source of truth for both views: baseline shaped as a `RecomputeResult`; `inject()` parses admin JSON anomalies (the only anomaly source), accumulates them, recomputes, rebuilds the log and fact packs atomically — on any error the previous state is kept; `snapshot()` (admin board: segment statuses with effective times, per-train action/departure/arrivals/delay/reason, phrased decision log, total added delay) and `passenger(tid)` (ETA minute from the SAME result + short guard-checked reason only).
3. **server unit** (`app/server.py`) — stdlib `ThreadingHTTPServer`, four JSON routes + the page; engine errors → HTTP 400 with the message, never a crash; `serve_in_thread()` for tests on an ephemeral port.
4. **ui unit** (`app/static/index.html`, `run_ui.py`) — one static page, vanilla JS: admin column (anomaly buttons for all 5 types with segment/train pickers + factor/minutes inputs, reset, color-coded segment status table, schedule board with action pills and reasons, decision log with trigger line) and passenger column (train picker, big ETA, one-line reason). One-command launcher opens the browser.

### What each gate checks (hand-verified values)
- `test_decision_log.py` (+1): unchanged T4 fact pack still carries S6@39 with allow-lists.
- `test_app_state.py` (7): baseline board (T1 S4@30, T3 S6@32 before any anomaly); closure inject → board (T1 reroute S4@22), segment SEG-34 shown closed, log = [T1,T2,T5], total −11, passenger T2 = "minute 34" guard-clean; **the consistency gate**: across 8 scenarios × every train, passenger ETA == the admin board's destination arrival (and None==None for cancelled/stranded — nothing fabricated); second anomaly accumulates (T4 dep 28 → S6@44, the Phase 2 value); reset restores baseline; bad injections (unknown type, factor 2) raise and leave state byte-identical.
- `test_http_end_to_end.py` (3): THE DEMO SEQUENCE over real HTTP — baseline (T2@29) → admin injects track_closed(SEG-34) → board shows T1 rerouted S4@22 → decision log visible, T2's line names T1 and 34 → passenger T2 updates to 34 == board value → second anomaly accumulates (T4 S6@44) → reset → T2@29 again. Bad input over HTTP → 400 with the offending id in the message, server stays alive; unknown route → 404.
- `test_ui_page.py` (2): served page contains all five anomaly controls + reset, the three admin sections, the passenger pane, and the exact API endpoints the end-to-end gate proved.
- Manual smoke: `python3 run_ui.py --no-browser` booted; `/api/state` returned the 6 stations and 5 trains; `/` returned 200.

### Phase 5 done-conditions → status
1. Admin view shows network, schedule, anomaly, decision log, updating on injection — PASS (state + HTTP gates; UI renders those exact API fields)
2. Passenger view shows only the chosen train's ETA + short reason — PASS
3. Passenger ETA equals engine's computed arrival — PASS (consistency gate across all scenarios and trains)
4. Full sequence inject → recompute → reasoning shown → passenger update runs cleanly end to end — PASS (automated over real HTTP, plus manual boot smoke)

### Decisions (mechanical, logged not asked)
- Anomalies ACCUMULATE across injections (recompute always = baseline + all active anomalies); explicit Reset button. This gives the stretch "second simultaneous anomaly" demo step for free.
- Stdlib `http.server` (ThreadingHTTPServer) + one static HTML file with vanilla JS — no framework, no build step, no dependency beyond pytest for tests.
- Failed injections are transactional: parse+recompute happen before any state mutation.
- Passenger ETA rendered as "min N" (abstract minutes — the whole model is minute-based, honest to SPEC).

### Environment note
Unchanged: stale `.git\index.lock` + `tmp_obj_*` under `.git\objects` need manual cleanup on your machine.

### Next
STOPPED at phase boundary. Phases 1–5 complete: the demo is runnable end to end. Phase 6 (stretch: live 7th station, map animation, confidence layer, second anomaly already works) only on your go.

---

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
4. **collision unit** (`engine/collision.py`) — occupancy windows are closed intervals; inclusive overlap (`a.start <= b.end and b.start <= a.end`),