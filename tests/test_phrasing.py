"""Gate: phrasing unit. Deterministic templates, pluggable LLM, drift guard
enforced on BOTH — the guard is a real test (SPEC F4 adversarial 1)."""

from data.baseline import build_network, build_trains
from engine.anomalies import (
    ReducedSpeed,
    TrackClosed,
    TrainCancelled,
    TrainDelayed,
)
from engine.decision_log import build_decision_log
from engine.phrasing import (
    LLMPhraser,
    TemplatePhraser,
    get_phraser,
    safe_phrase_log_entry,
    safe_phrase_passenger_eta,
    safe_phrase_trigger,
)
from engine.recompute import recompute_schedule


def make_log(anomalies):
    net, trains = build_network(), build_trains()
    return build_decision_log(net, trains, anomalies, recompute_schedule(net, trains, anomalies))


def entry_for(log, train_id):
    return next(e for e in log.entries if e.train_id == train_id)


# --- deterministic template, hand-verified exact strings ---

def test_template_dispatcher_line_exact():
    log = make_log([TrainDelayed("T2", 2)])
    t4 = entry_for(log, "T4")
    assert TemplatePhraser().phrase_log_entry(t4) == (
        "[hold] T4: held at S4 until minute 25 so T2 clear(s) the line; "
        "arrives S6 at minute 41 (+2 min)."
    )


def test_template_passenger_lines_exact():
    log = make_log([TrainDelayed("T2", 2)])
    phr = TemplatePhraser()
    assert phr.phrase_passenger_eta(entry_for(log, "T4")) == (
        "Train T4: expected arrival at S6 is minute 41 (2 min later than planned)."
    )
    closure = make_log([TrackClosed("SEG-34")])
    assert phr.phrase_passenger_eta(entry_for(closure, "T5")) == (
        "Train T5: expected arrival at S1 is minute 62 (8 min earlier than planned)."
    )
    cancelled = make_log([TrainCancelled("T3")])
    assert phr.phrase_passenger_eta(entry_for(cancelled, "T3")) == (
        "Train T3 is cancelled. We are sorry for the disruption."
    )
    stranded = make_log([TrackClosed("SEG-34"), TrackClosed("SEG-45")])
    text = phr.phrase_passenger_eta(entry_for(stranded, "T1"))
    assert "cannot currently reach S4" in text
    assert "No arrival time" in text  # nothing fabricated


def test_template_trigger_exact():
    log = make_log([ReducedSpeed("SEG-56", 0.5)])
    assert TemplatePhraser().phrase_trigger(log) == (
        "Anomaly injected: reduced_speed(SEG-56, factor 0.5)."
    )


# --- the guard is a REAL test: faithful LLM accepted, drifting LLM rejected ---

def test_faithful_llm_text_is_accepted():
    log = make_log([TrackClosed("SEG-34")])
    t2 = entry_for(log, "T2")
    faithful = LLMPhraser(
        lambda prompt: "Heads up: T2 now reaches S6 at minute 34, 5 minutes behind plan."
    )
    text, violations = safe_phrase_log_entry(faithful, t2)
    assert violations == []
    assert text == "Heads up: T2 now reaches S6 at minute 34, 5 minutes behind plan."


def test_llm_inventing_a_number_falls_back_to_template():
    log = make_log([TrackClosed("SEG-34")])
    t2 = entry_for(log, "T2")
    drifting = LLMPhraser(lambda prompt: "T2 now reaches S6 at minute 35.")
    text, violations = safe_phrase_log_entry(drifting, t2)
    assert violations == ["invented number: 35"]
    assert text == TemplatePhraser().phrase_log_entry(t2)  # safe fallback


def test_llm_inventing_a_train_falls_back():
    log = make_log([TrackClosed("SEG-34")])
    t2 = entry_for(log, "T2")
    drifting = LLMPhraser(
        lambda prompt: "T2 reaches S6 at minute 34, overtaking T8 on the way."
    )
    text, violations = safe_phrase_passenger_eta(drifting, t2)
    assert violations == ["invented id: T8"]
    assert text == TemplatePhraser().phrase_passenger_eta(t2)


def test_llm_drifting_on_trigger_falls_back():
    log = make_log([TrainDelayed("T1", 12)])
    drifting = LLMPhraser(lambda prompt: "T1 is running roughly 15 minutes late.")
    text, violations = safe_phrase_trigger(drifting, log)
    assert violations == ["invented number: 15"]
    assert text == "Anomaly injected: train_delayed(T1, 12 min)."


# --- interface: no key -> template; callable -> LLM. No code changes. ---

def test_get_phraser_defaults_to_template():
    assert isinstance(get_phraser(), TemplatePhraser)
    assert isinstance(get_phraser(lambda p: "x"), LLMPhraser)


# --- meta gate: ALL template output passes the guard on every scenario ---

def test_every_template_phrase_passes_the_guard():
    scenarios = [
        [TrackClosed("SEG-34")],
        [TrackClosed("SEG-15")],
        [TrainDelayed("T2", 2)],
        [TrainDelayed("T1", 12)],
        [ReducedSpeed("SEG-56", 0.5)],
        [TrackClosed("SEG-34"), TrackClosed("SEG-45")],
        [TrainCancelled("T3")],
        [TrackClosed("SEG-34"), TrainDelayed("T4", 5)],
    ]
    phr = TemplatePhraser()
    checked = 0
    for anomalies in scenarios:
        log = make_log(anomalies)
        _, violations = safe_phrase_trigger(phr, log)
        assert violations == [], (anomalies, "trigger")
        for entry in log.entries:
            _, v1 = safe_phrase_log_entry(phr, entry)
            _, v2 = safe_phrase_passenger_eta(phr, entry)
            assert v1 == [], (anomalies, entry.train_id, "dispatcher")
            assert v2 == [], (anomalies, entry.train_id, "passenger")
            checked += 1
    assert checked >= 15  # the loop really exercised a broad set of entries
