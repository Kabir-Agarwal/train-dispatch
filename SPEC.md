# SPEC.md — Train Dispatch & Anomaly-Recovery System
Project: Far Away hackathon (theme: Railways). Round 1 deadline June 14, 11:59 PM IST.
One-line: A railway dispatch system that holds a live schedule on a small network, and when an admin injects an anomaly (track down, train cancelled, delay, conflict), recomputes a safe, collision-free, delay-minimized schedule — and shows both the dispatcher's decisions and each passenger's updated arrival time.

## SCOPE — IN (built for the demo)
- A fixed network of 6 stations (data model allows appending a 7th+).
- Tracks (segments) connecting stations, each with a travel time and a status (open / closed / reduced-speed).
- 4–6 trains with a starting schedule (origin, destination, planned times, path).
- A scheduling engine that: holds the baseline schedule; accepts an ADMIN-INJECTED anomaly (the only anomaly source — no automatic or system-generated events); recomputes a new schedule that is collision-free (hard rule) and minimizes total delay; outputs per-train instructions (hold / reroute / depart-delayed / unchanged).
- An admin/dispatcher view: the network, trains, current schedule, the anomaly, and the system's decisions + reasoning log.
- A passenger view: per-train estimated arrival time only (computed by the engine, phrased by the LLM).
- LLM role (narrow): phrase passenger ETA messages and optionally the dispatcher log in plain language. The LLM NEVER computes times, schedules, or routes.

## SCOPE — OUT (explicitly not built now)
- Real-world railway data or timetables (hand-built example network only).
- Live GPS / real-time tracking (event-driven, not sensor-driven).
- Optimal scheduling from scratch via heavy solvers — start from a given baseline and react; simple greedy/priority recompute is enough.
- The logistics/delivery road-vehicle project (queued for after Round 1).
- The student learning system (queued).
- Accounts, payments, persistence beyond the running session.
- Networks larger than ~7–8 stations (claimed as "scales", not demonstrated).

## OBJECTIVE HIERARCHY
1. SAFETY — hard constraint, never violated: no two trains on the same track segment at the same time. A schedule violating this is invalid and rejected. Collisions are not "high cost" — they are forbidden.
2. Within the safe space: minimize total delay across all trains (minutes late vs baseline), favouring on-time arrival.
3. Tie-breakers only when delay is equal: fewer reroutes, fewer trains held.

## NETWORK DATA MODEL
- Stations: list of 6 (S1..S6), appendable.
- Segments: id, two endpoint stations, travel time (minutes), status (open/closed/reduced-speed).
- Trains: id, origin, destination, planned path (ordered segment list), planned departure, computed arrival per segment.
- Segment occupancy table: which train is on which segment during which time window (for collision checking).

## FEATURES

### F1 — Load baseline schedule
Given network + trains, compute each train's planned arrival at each station and the occupancy table. Baseline must itself be collision-free.
- Normal: 5 trains with defined paths/departures → schedule table + occupancy table, zero conflicts.
- Adversarial 1: baseline contains a conflict (two trains overlapping on a segment) → DETECT and report at load, never silently accept.
- Adversarial 2: a train's path uses a nonexistent segment or disconnected endpoints → rejected with a clear error, not a crash.
- Adversarial 3: two trains on the same segment at the exact same minute (boundary) → counts as a conflict (inclusive overlap).

### F2 — Inject anomaly (ADMIN ONLY)
The admin injects an anomaly mid-run through the admin view — the ONLY anomaly source. Types:
- track_closed(segment); track_blocked(segment) (unplanned, same routing effect, different label);
- reduced_speed(segment, factor); train_cancelled(train); train_delayed(train, minutes); combinations (two at once).
- Normal: track_closed(S3-S4) → segment marked closed, affected trains identified.
- Adversarial 1: anomaly on a segment no train uses → "no impact", schedule unchanged (never invent changes).
- Adversarial 2: small delay causing no conflict → NO reroute/hold; only that train's times shift (don't over-react).
- Adversarial 3: anomaly makes a destination unreachable (no alternative path) → report that train as "stranded / cannot complete"; never loop or fabricate a route.

### F3 — Recompute schedule (the core)
After an anomaly: produce a new schedule that is (a) collision-free, (b) delay-minimized, (c) routes every train that still has a valid path. Output per train: reroute via [path] / hold until [time] / depart delayed [minutes] / unchanged.
- Normal: closure on a needed segment → that train rerouted; others adjusted only if the reroute creates a conflict; total added delay reported.
- Adversarial 1: two trains need the single remaining track → SEQUENCE them (one waits); never both on it; output shows who waits and why.
- Adversarial 2: rerouting train A creates a NEW conflict with train B → resolve the second-order conflict too (re-check the whole occupancy table, not just the changed train).
- Adversarial 3: the delay-optimal move would require a collision → take the slower collision-free option. Safety beats delay, always.

### F4 — Decision/reasoning log
Every engine change logs: trigger, change, reason, delay numbers (e.g. "rerouted T2 via S1-S5-S6 because S3-S4 closed; held T4 2 min to avoid conflict with T2 on S5-S6"). LLM may phrase the text, but every fact comes from the engine.
- Adversarial 1: LLM phrasing must not introduce any number or claim absent from engine output — verified by checking phrased text against engine values.

### F5 — Admin view
Network (stations + segment statuses), all trains + current schedule, the injected anomaly, the decision log. Updates when an anomaly is injected. A clear recomputing board is enough; a moving-map animation is optional polish only.

### F6 — Passenger view
For a chosen train: ONLY the estimated arrival time (+ short reason if delayed). Time from the engine; LLM only phrases.
- Adversarial 1: passenger ETA must equal the engine's computed arrival — the two views can never disagree.

## HARD CONSTRAINTS
- Collision-free is absolute.
- LLM never computes times/routes/schedules — all numbers originate in the deterministic engine.
- Re-check the WHOLE occupancy table after any change.
- If no valid path exists, say so honestly; never fabricate.
- State in files/objects; small files, small functions.

## HONEST LIMITS
Simplified model of a hard problem. Greedy recompute, not proven-optimal. Claim exactly what the demo shows: safe, automatic, explainable rescheduling under admin-injected anomalies on a small network, with consistent passenger ETAs.
