"""Gate: display unit. Mapping bijection + drift-guarded plain summary."""

from app.display import (
    DISPLAY_NAMES,
    ENGINE_IDS,
    display_name,
    safe_summary,
    summarize_actions,
)
from app.state import AppState
from data.baseline import build_network
from engine.drift_guard import verify_text


def test_display_mapping_is_a_bijection_covering_the_network():
    net = build_network()
    # every engine id resolves to exactly one display name...
    assert sorted(DISPLAY_NAMES) == sorted(net.stations)
    assert len(set(DISPLAY_NAMES.values())) == len(DISPLAY_NAMES)
    # ...and back
    for sid, name in DISPLAY_NAMES.items():
        assert ENGINE_IDS[name] == sid
    assert display_name("S4") == "Howrah"
    assert display_name("S7") == "S7"  # unmapped id falls back, never breaks


def test_summary_closure_scenario_hand_verified():
    s = AppState()
    s.inject([{"type": "track_closed", "segment": "SEG-34"}])
    # engine output: T1, T2, T5 rerouted; largest extra delay = T2's +5
    assert s.snapshot()["summary_text"] == (
        "3 trains rerouted — largest extra delay 5 min."
    )


def test_summary_hold_scenario_hand_verified():
    s = AppState()
    s.inject([{"type": "train_delayed", "train": "T2", "minutes": 2}])
    # T4 held (+2), T2 departing late (+2)
    assert s.snapshot()["summary_text"] == (
        "1 train held, 1 departing late — largest extra delay 2 min."
    )


def test_summary_stranded_scenario():
    s = AppState()
    s.inject([{"type": "track_closed", "segment": "SEG-34"},
              {"type": "track_closed", "segment": "SEG-45"}])
    assert s.snapshot()["summary_text"] == "3 trains stranded — no extra delay."


def test_summary_no_impact_and_baseline():
    s = AppState()
    assert s.snapshot()["summary_text"] == ""  # nothing injected yet
    s.inject([{"type": "track_closed", "segment": "SEG-36"}])
    assert s.snapshot()["summary_text"] == (
        "No changes needed — all trains run as planned."
    )


def test_summary_is_drift_guard_clean_and_tampering_is_caught():
    s = AppState()
    s.inject([{"type": "track_closed", "segment": "SEG-34"}])
    text, allowed = summarize_actions(s.result.actions)
    assert verify_text(text, frozenset(), allowed) == []
    tampered = text.replace("5 min", "7 min")
    assert verify_text(tampered, frozenset(), allowed) == ["invented number: 7"]


def test_display_names_served_in_snapshot():
    snap = AppState().snapshot()
    assert snap["display_names"]["S1"] == "Delhi"
    assert snap["display_names"]["S6"] == "Chennai"
