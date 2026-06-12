"""Display layer only — NO engine logic. City-name skin + plain-language
summary. Internal ids (S1..S6) stay the engine/test vocabulary; these names
exist purely for the UI."""

from engine.drift_guard import verify_text

DISPLAY_NAMES = {
    "S1": "Delhi",
    "S2": "Bhopal",
    "S3": "Nagpur",
    "S4": "Howrah",
    "S5": "Mumbai",
    "S6": "Chennai",
}

ENGINE_IDS = {name: sid for sid, name in DISPLAY_NAMES.items()}


def display_name(station_id):
    """UI label for a station; unmapped ids (e.g. a 7th station) fall back
    to the raw id so nothing ever breaks."""
    return DISPLAY_NAMES.get(station_id, station_id)


def summarize_actions(actions):
    """One plain sentence from ENGINE OUTPUT ONLY, with its drift-guard
    allow-list. Returns (text, allowed_numbers)."""
    counts = {"reroute": 0, "hold": 0, "depart_delayed": 0,
              "late": 0, "cancelled": 0, "stranded": 0}
    max_extra = 0
    for a in actions.values():
        if a.action == "unchanged" and (a.added_delay or 0) > 0:
            counts["late"] += 1
        elif a.action in counts:
            counts[a.action] += 1
        if a.added_delay is not None and a.added_delay > max_extra:
            max_extra = a.added_delay
    labels = [("reroute", "rerouted"), ("hold", "held"),
              ("depart_delayed", "departing late"), ("late", "running late"),
              ("cancelled", "cancelled"), ("stranded", "stranded")]
    parts = []
    for key, label in labels:
        n = counts[key]
        if n:
            noun = "" if parts else (" train" if n == 1 else " trains")
            parts.append(f"{n}{noun} {label}")
    if not parts:
        return ("No changes needed — all trains run as planned.", frozenset())
    tail = (f" — largest extra delay {max_extra} min."
            if max_extra else " — no extra delay.")
    text = ", ".join(parts) + tail
    allowed = frozenset(
        {float(n) for n in counts.values() if n} | {float(max_extra)}
    )
    return text, allowed


def safe_summary(actions):
    """The summary line, drift-guard verified like any phrased text."""
    text, allowed = summarize_actions(actions)
    violations = verify_text(text, frozenset(), allowed)
    if violations:  # cannot happen unless summarize drifts from its own list
        return "Plan updated safely."
    return text
