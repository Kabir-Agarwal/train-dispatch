"""Phase I — regenerative-braking synchronization (builds on Phase H eco-driving).

When a train brakes regeneratively it pushes energy back into its power section's
overhead line. That energy is only RECOVERED if another train is drawing power
(accelerating) on the SAME power section at the SAME time; otherwise, with no
line-side storage, it is lost. So coordinating accel/decel TIMING — shifting an
acceleration (within the train's schedule slack) to coincide with a nearby
braking — recovers energy that would otherwise be wasted.

Method — WINDOWED SUPPLY/DEMAND MATCHING with slack synchronization:
- A braking event is a regen SUPPLY (section, time, energy ~ eff * v**2, the
  recoverable share of braking kinetic energy — Phase H's v**2 unit).
- An accelerating event is a DEMAND (section, time, energy ~ v**2).
- Energy transfers from a supply to a demand on the SAME section when their times
  fall within `window` minutes; greedy energy matching, deterministic.
- UNSYNCHRONISED recovery uses the natural (scheduled) times. SYNCHRONISED
  recovery first shifts each demand up to `max_shift` minutes toward the nearest
  same-section supply, then matches — capturing pairs that were just-missing.

Pure and deterministic; no scheduling, so the recompute golden is unaffected.
"""

REGEN_EFFICIENCY = 0.85   # share of braking kinetic energy returned to the line


def brake_regen_units(speed_kmph, eff=REGEN_EFFICIENCY):
    """Recoverable regen from braking to a stop ~ eff * v**2 (Phase H energy unit)."""
    return round(eff * speed_kmph ** 2)


def _match(supplies, demands, window):
    """Greedy energy transferred between same-section supply/demand events whose
    times are within `window`. Returns (recovered, pairs)."""
    dem = [dict(d, left=d["energy"]) for d in demands]
    recovered = 0
    pairs = []
    for s in supplies:
        left = s["energy"]
        for d in dem:
            if left <= 0:
                break
            if (d["left"] > 0 and d["section"] == s["section"]
                    and abs(d["time"] - s["time"]) <= window):
                x = min(left, d["left"])
                left -= x
                d["left"] -= x
                recovered += x
                pairs.append({"section": s["section"], "supply_t": s["time"],
                              "demand_t": d["time"], "energy": x})
    return recovered, pairs


def coordinate_regen(supplies, demands, window=1, max_shift=0):
    """Recovered regen energy, unsynchronised vs synchronised (demands shifted up
    to `max_shift` min toward a same-section supply). See module docstring."""
    unsync, _ = _match(supplies, demands, window)

    shifted = []
    for d in demands:
        cands = [s["time"] for s in supplies
                 if s["section"] == d["section"]
                 and abs(s["time"] - d["time"]) <= max_shift + window]
        t = d["time"]
        if cands:
            target = min(cands, key=lambda x: abs(x - d["time"]))
            if abs(target - d["time"]) <= max_shift:
                t = target
        shifted.append(dict(d, time=t))
    sync, pairs = _match(supplies, shifted, window)

    return {
        "recovered_unsync": unsync,
        "recovered_sync": sync,
        "extra_recovered": sync - unsync,
        "available_regen": sum(s["energy"] for s in supplies),
        "pairs": pairs,
        "window_min": window,
        "max_shift_min": max_shift,
        "method": "windowed supply/demand matching with slack synchronization "
                  "(regen ~ %.2f * v²; illustrative, no line-side storage)"
                  % REGEN_EFFICIENCY,
    }
