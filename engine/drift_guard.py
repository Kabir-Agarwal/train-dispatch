"""Drift guard (SPEC F4 adversarial 1): phrased text must not contain any
number or any train/station/segment id the engine did not produce.

This is the REAL test between the engine and anything an LLM writes: text in,
violations out. Empty list = faithful.
"""

from .decision_log import ids_in, numbers_in


def verify_text(text, allowed_entities, allowed_numbers):
    """Return a list of violation strings (empty = text is faithful).

    - every T*/S*/SEG-* id mentioned must be in allowed_entities
    - every remaining number must be in allowed_numbers (compared as floats)
    """
    violations = []
    for entity in sorted(ids_in(text)):
        if entity not in allowed_entities:
            violations.append(f"invented id: {entity}")
    allowed = {float(n) for n in allowed_numbers}
    for number in sorted(numbers_in(text)):
        if number not in allowed:
            n = int(number) if float(number).is_integer() else number
            violations.append(f"invented number: {n}")
    return violations


def verify_entry_text(text, entry):
    """Check phrased text against a LogEntry's engine-fact allow-lists."""
    return verify_text(text, entry.entities, entry.numbers)


def verify_trigger_text(text, log):
    """Check a phrased trigger line against the DecisionLog's trigger facts."""
    return verify_text(text, log.trigger_entities, log.trigger_numbers)
