"""Phrasing layer (SPEC F4/F6): turns engine facts into plain language.

Architecture (per review note):
- `Phraser` is an interface. `TemplatePhraser` is deterministic and needs no
  API key — the system is fully functional with it.
- `LLMPhraser` wraps any `complete(prompt) -> str` callable (an Anthropic
  client, a local model, anything). Plugging one in is constructor injection —
  no code changes.
- EVERY phrased string, from either phraser, goes through the drift guard in
  `safe_*`. If the text contains a number or id the engine did not produce,
  it is discarded and the deterministic template is used instead, with the
  violations reported. The LLM never computes; at worst it rephrases.
"""

from .drift_guard import verify_entry_text, verify_trigger_text


class TemplatePhraser:
    """Deterministic phrasing from engine facts only. Always available."""

    def phrase_trigger(self, log):
        return f"Anomaly injected: {log.trigger}."

    def phrase_log_entry(self, entry):
        return f"[{entry.change}] {entry.train_id}: {entry.reason}."

    def phrase_passenger_eta(self, entry):
        tid, dest = entry.train_id, entry.destination
        if entry.change == "cancelled":
            return f"Train {tid} is cancelled. We are sorry for the disruption."
        if entry.change == "stranded":
            return (
                f"Train {tid} cannot currently reach {dest}; "
                f"service is interrupted. No arrival time can be given."
            )
        arr, added = entry.arrival, entry.added_delay or 0
        if added > 0:
            return (
                f"Train {tid}: expected arrival at {dest} is minute {arr} "
                f"({added} min later than planned)."
            )
        if added < 0:
            return (
                f"Train {tid}: expected arrival at {dest} is minute {arr} "
                f"({abs(added)} min earlier than planned)."
            )
        return f"Train {tid}: expected arrival at {dest} is minute {arr}, on time."


class LLMPhraser:
    """Wraps any complete(prompt)->str callable. The prompt hands the model
    ONLY engine facts; the drift guard still checks whatever comes back."""

    def __init__(self, complete):
        self.complete = complete

    def phrase_trigger(self, log):
        return self.complete(
            "Rephrase this railway anomaly notice in one plain sentence. "
            "Use only the facts given, do not add numbers or names.\n"
            f"Facts: {log.trigger}"
        )

    def phrase_log_entry(self, entry):
        return self.complete(
            "Rephrase this dispatcher decision in one plain sentence. "
            "Use only the facts given, do not add numbers or names.\n"
            f"Facts: train {entry.train_id}, change {entry.change}, "
            f"detail: {entry.reason}"
        )

    def phrase_passenger_eta(self, entry):
        return self.complete(
            "Write one short, friendly arrival update for a passenger. "
            "Use only the facts given, do not add numbers or names.\n"
            f"Facts: train {entry.train_id}, destination {entry.destination}, "
            f"arrival minute {entry.arrival}, delay {entry.added_delay} min, "
            f"status {entry.change}"
        )


def get_phraser(complete=None):
    """Template by default; LLM-backed iff a completion callable is supplied."""
    return TemplatePhraser() if complete is None else LLMPhraser(complete)


_TEMPLATE = TemplatePhraser()


def _safe(text, violations_fn, fallback_text):
    violations = violations_fn(text)
    if violations:
        return fallback_text, violations
    return text, []


def safe_phrase_trigger(phraser, log):
    """Returns (text, violations). On violations, text is the safe template."""
    return _safe(
        phraser.phrase_trigger(log),
        lambda t: verify_trigger_text(t, log),
        _TEMPLATE.phrase_trigger(log),
    )


def safe_phrase_log_entry(phraser, entry):
    return _safe(
        phraser.phrase_log_entry(entry),
        lambda t: verify_entry_text(t, entry),
        _TEMPLATE.phrase_log_entry(entry),
    )


def safe_phrase_passenger_eta(phraser, entry):
    return _safe(
        phraser.phrase_passenger_eta(entry),
        lambda t: verify_entry_text(t, entry),
        _TEMPLATE.phrase_passenger_eta(entry),
    )
