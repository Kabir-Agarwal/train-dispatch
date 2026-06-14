# System boundaries — what this demo deliberately simplifies

This project is an honest demo of safe, automatic, explainable rescheduling under
admin-injected anomalies on a small network. To stay legible and verifiable it
makes deliberate simplifications. None of them is hidden: each is a known limit
with a note on what a production system would require. (See also `SPEC.md` for
scope and `DEPLOY.md` for running it.)

## 1. Segment exclusivity vs real signalling (block / moving-block)
**In this demo:** safety is modelled as *one train per track segment at a time*
(a whole station-to-station section is occupied for the train's whole traversal,
in either direction). Conflicts are exact overlaps of those closed-interval
windows.
**Why it's acceptable here:** it is a strictly conservative rule — it can only
ever be *safer* than real signalling — and it makes "collision-free" provable and
easy to inspect.
**Production would require:** real **fixed-block** signalling (multiple sub-blocks
per section with aspect/headway rules) or **moving-block** (ETCS L2/L3-style
continuous separation), plus interlocking, points/route locking, and braking
curves — not a single section-level lock.

## 2. Single-track assumption (no separate up/down lines)
**In this demo:** every link is a single shared track; both directions use the
same segment, so two opposing trains are sequenced (one waits at a station). No
station pair has parallel up/down lines.
**Why it's acceptable here:** much of the modelled region genuinely is single- or
limited-line, and it makes the opposing-move logic explicit and testable.
**Production would require:** modelling **double / multiple track**, direction-
specific running lines, loops and refuge sidings, and platform-line allocation —
so capacity is per-line, not per-section.

## 3. No crew or rake (rolling-stock) scheduling
**In this demo:** trains are abstract movers. There is no driver/guard duty,
no link to a physical rake, no turn-around, cleaning, or maintenance-of-stock
time, and no depot balancing.
**Why it's acceptable here:** the demo's question is *track* deconfliction and
delay, which is well-posed without crew/rake state.
**Production would require:** **crew rostering** (duty hours, relief points,
hours-of-service law) and **rake links** (a train is a specific physical set that
must arrive before its next service), which often dominate real recovery decisions.

## 4. Deterministic, not stochastic
**In this demo:** travel times are fixed integers and every recompute is fully
deterministic — the same inputs always give the same plan (a gate proves it).
There is no uncertainty, no dwell variability, no probabilistic delay.
**Why it's acceptable here:** determinism makes the output explainable and
testable, which is the point of the demo.
**Production would require:** **stochastic** running/dwell times, delay
distributions, and robust/expected-value or simulation-based optimisation, plus
confidence on predicted knock-on delay.

## 5. Regional scale (≈50 stations), not national
**In this demo:** the largest network is the ~50-station West Bengal mesh; route
finding is full-DFS path enumeration, which is fine at this size.
**Why it's acceptable here:** it comfortably covers a region and keeps recompute
well under a second.
**Production would require:** **national scale** (thousands of stations, tens of
thousands of services) with indexed/heuristic routing, time-windowed search, and
partitioning — full DFS would not scale.

## 6. Passenger re-accommodation is basic
**In this demo:** recovery acts on *trains* (reroute / hold / sequence) AND, when a
train is cancelled, now computes earliest-arrival **alternative journeys** for its
passengers over the remaining trains (Connection-Scan, Phase K) — it reroutes the
people, not just the train. But that is the whole of it: the fare panel is
illustrative load visibility, not a booking system.
**Why it's acceptable here:** it gives each affected origin→destination a real
next-best route + ETA, which is the core of passenger re-accommodation.
**Production would require:** seat/berth **inventory** and rebooking/ticketing,
fare adjustment and refunds, onward-**connection protection** across services and
operators, and passenger notification — none of which this models. So this is
genuine but partial **passenger re-accommodation**, not a reservation system.

---

These boundaries are intentional. The demo claims exactly what it shows: safe,
automatic, explainable train rescheduling on a small regional network, with
consistent passenger ETAs — and it is honest about everything above that it does
not attempt.
