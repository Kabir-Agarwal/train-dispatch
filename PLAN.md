# PLAN.md — Train Dispatch & Anomaly-Recovery System
Deadline June 14, 11:59 PM IST.

## BUILD PROFILE: LIGHT (hackathon)
- KEEP: value-asserting gates (every test asserts a real expected value, never "no crash"); my review at each phase boundary; the adversarial examples from SPEC as tests.
- SKIP for this build: local verifier model, mutation testing, spec-coherence pass. (Those are for permanent projects.)
- Test hardest: the collision-free rule, and "LLM never computes numbers".
- A working demoable system on June 14 beats a perfectly-gated half-system.

## PHASE 1 — Network + baseline schedule
Data model (stations, segments, trains) + baseline scheduler + collision checker.
Done when: 6-station network with segments and 4–6 trains loads; per-station arrival times + occupancy table computed; collision checker flags a conflicting baseline and accepts a clean one; bad input (nonexistent segment, disconnected path) rejected cleanly; same-segment same-minute boundary overlap counts as conflict; all gates assert hand-verified expected values.

## PHASE 2 — Anomaly injection + impact detection
All anomaly types injectable (admin-only source); affected trains identified. No rescheduling yet.
Done when: each type works; no-impact anomaly reports "no impact" and changes nothing; harmless small delay causes no reroute/hold; unreachable destination reported as "stranded" with no infinite loop.

## PHASE 3 — Recompute engine (the core)
Done when: closure reroutes affected train via valid alternative, others untouched unless needed; two trains needing one track are sequenced, never both on it; second-order conflicts from a reroute are also resolved (whole table re-checked); when the delay-optimal move would collide, engine takes the safe slower option; output gives each train a clear action + total added delay; gates assert collision-free AND hand-verified expected actions on set scenarios.

## PHASE 4 — Decision log + LLM phrasing (with drift guard)
Done when: every change produces a log entry (trigger, change, reason, numbers); LLM-phrased text is verified against engine values — no number/claim the engine didn't produce. The guard is a real test.

## PHASE 5 — Admin view + Passenger view
Done when: admin view shows network, schedule, anomaly, decision log, updating on injection; passenger view shows only the chosen train's ETA + short reason; passenger ETA equals engine's computed arrival; the full sequence (inject anomaly → recompute → reasoning shown) runs cleanly end to end. THIS IS THE DEMO MOMENT — it must be smooth.

## PHASE 6 — Only if time
Add a 7th station live; map animation; floating confidence layer on ETAs; a second simultaneous anomaly in the demo. Do NOT start until 1–5 are solid.

## THE DEMO (build backward from this)
1. Show network + running schedule (10s). 2. Admin injects anomaly live: "track S3–S4 closed". 3. System recomputes: reroutes one train, holds another, collision-free. 4. Show the reasoning log. 5. Passenger view: updated ETA, consistent with the plan. 6. (Stretch) second anomaly. Steps 2–4 are what wins — make those 60 seconds flawless.

## BUILDER WORKING RULES (apply to every phase)
- Work in small units. Per unit: build smallest code → write a gate asserting a hand-verified expected value → run it for real → fix only this unit until green → commit with a message naming the unit → log to PROGRESS.md.
- Never assume a test passes. Never accept "should work".
- Fix bugs with the smallest change; check git diff; revert anything unrelated.
- Mechanical decisions (file names, structure, libraries): decide yourself, log in PROGRESS.md. Ask me ONLY for conceptual decisions that change product behavior.
- At each phase end: commit, update PROGRESS.md, STOP and wait for my review before the next phase.

### Loop limits (runaway guard)
- Hard cap: 5 fix attempts per gate (unit tests, mutation testing, verifier findings, any retry loop). Count attempts explicitly in output: "Attempt N of 5".
- If 2 consecutive attempts fail with the same root cause, the approach is wrong — stop early; do not retry variations.
- On hitting a cap or stopping early: HALT all work and produce a short escalation report: (a) what was attempted per try, one line each; (b) the persistent failure and best hypothesis why; (c) 2–3 alternative approaches with a recommendation. Then wait for my decision. Never bypass a cap.
- Builder↔verifier cycles: max 3 rounds. If the verifier still flags issues after round 3, escalate instead of continuing.
