"""Gate: log unit. Hand-verified entries from known scenarios."""

from data.baseline import build_network, build_trains
from engine.anomalies import TrackClosed, TrainDelayed
from engine.decision_log import build_decision_log, describe_anomaly
from engine.recompute import recompute_schedule


def make_log(anomalies):
    net, trains = build_network(), build_trains()
    return build_decision_log(net, trains, anomalies, recompute_schedule(net, trains, anomalies))


def test_describe_anomaly_strings():
    assert describe_anomaly(TrackClosed("SEG-34")) == "track_closed(SEG-34)"
    assert describe_anomaly(TrainDelayed("T1", 12)) == "train_delayed(T1, 12 min)"


def test_closure_log_has_exactly_the_changed_trains():
    # SEG-34 closed: T1, T2, T5 change; T3, T4 do not (Phase 3 verified values).
    log = make_log([TrackClosed("SEG-34")])
    assert log.trigger == "track_closed(SEG-34)"
    assert [e.train_id for e in log.entries] == ["T1", "T2", "T5"]
    assert log.total_added_delay == -11

    t2 = log.entries[1]
    assert t2.change == "reroute"
    assert t2.destination == "S6"
    assert t2.arrival == 34
    assert t2.added_delay == 5
    # the allow-lists carry the engine numbers and ids phrasing may use
    assert {34.0, 5.0} <= t2.numbers
    assert {"T2", "T1", "S6", "SEG-12", "SEG-23", "SEG-36"} <= t2.entities


def test_hold_log_entry_numbers():
    # T2+2: changed = T2 (depart_delayed) and T4 (hold until 25, S6@41, +2).
    log = make_log([TrainDelayed("T2", 2)])
    assert [e.train_id for e in log.entries] == ["T2", "T4"]
    t4 = log.entries[1]
    assert t4.change == "hold"
    assert t4.arrival == 41
    assert t4.added_delay == 2
    assert {25.0, 41.0, 2.0} <= t4.numbers
    assert "T2" in t4.entities  # the blocker is citable
    assert log.total_added_delay == 4


def test_stranded_entry_has_no_arrival():
    log = make_log([TrackClosed("SEG-34"), TrackClosed("SEG-45")])
    stranded = {e.train_id: e for e in log.entries}
    assert set(stranded) == {"T1", "T4", "T5"}
    assert stranded["T1"].change == "stranded"
    assert stranded["T1"].arrival is None
    assert stranded["T1"].added_delay is None


def test_trigger_allowlists():
    log = make_log([TrainDelayed("T1", 12)])
    assert log.trigger_entities == frozenset({"T1"})
    assert log.trigger_numbers == frozenset({12.0})


def test_fact_entries_cover_unchanged_trains_too():
    from engine.decision_log import fact_entries_for_all_trains
    from engine.recompute import recompute_schedule

    net, trains = build_network(), build_trains()
    anomalies = [TrackClosed("SEG-34")]
    result = recompute_schedule(net, trains, anomalies)
    packs = fact_entries_for_all_trains(net, trains, anomalies, result)
    assert set(packs) == {"T1", "T2", "T3", "T4", "T5"}
    # unchanged T4 still has full engine facts: S6@39, zero added delay
    t4 = packs["T4"]
    assert t4.change == "unchanged"
    assert t4.arrival == 39
    assert t4.added_delay == 0
    assert 39.0 in t4.numbers and "S6" in t4.entities
