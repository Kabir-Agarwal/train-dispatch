# train-dispatch

A railway dispatch and anomaly-recovery demo: a small 6-station network runs a live
schedule; an admin injects an anomaly (track closed/blocked, reduced speed, train
delayed/cancelled) and the system recomputes a safe, delay-minimized schedule —
showing the dispatcher's decisions with reasons, and each passenger's updated
arrival time. Built for the Far Away hackathon (Railways theme).

## Run

```
python run_ui.py
```

Starts a local server (default port 8000) and opens the browser. Stdlib only —
no frameworks, no API key required. Tests: `python -m pytest tests/`.

## Architecture (5 lines)

1. A deterministic engine computes everything: schedules, occupancy windows, reroutes, holds, delays.
2. The LLM layer only phrases engine facts (pluggable; deterministic templates by default).
3. A drift guard blocks any phrased number or id the engine did not produce, with template fallback.
4. Collision-free is enforced by construction: a colliding schedule is unrepresentable in the search, and the whole occupancy table is re-checked after every recompute.
5. Every behavior is pinned by value-asserting tests with hand-verified expected minutes (140 passing at feature freeze).
