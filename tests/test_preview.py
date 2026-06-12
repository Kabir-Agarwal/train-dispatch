"""Gate: preview unit — THE preview==apply guarantee (same engine recompute),
plus hand-verified delta values."""

from app.state import AppState


CLOSURE = [{"type": "track_closed", "segment": "SEG-34"}]


def test_preview_equals_apply_exactly():
    s = AppState()
    predicted = s.preview(CLOSURE)
    # preview mutated nothing
    assert s.snapshot()["anomalies"] == []
    # now actually apply through the existing injection path
    s.inject(CLOSURE)
    applied = s.snapshot()
    # identical engine output: trains, totals, log train-by-train
    assert predicted["trains"] == applied["trains"]
    assert predicted["total_added_delay"] == applied["total_added_delay"]
    assert [e["train_id"] for e in predicted["decision_log"]] == \
        [e["train_id"] for e in applied["decision_log"]]
    assert [e["text"] for e in predicted["decision_log"]] == \
        [e["text"] for e in applied["decision_log"]]


def test_preview_delta_table_hand_verified():
    s = AppState()
    predicted = s.preview(CLOSURE)
    deltas = {d["id"]: d for d in predicted["deltas"]}
    # T1: unchanged S4@30 -> reroute S4@22, delta -8
    assert deltas["T1"]["old_action"] == "unchanged"
    assert deltas["T1"]["new_action"] == "reroute"
    assert (deltas["T1"]["old_arrival"], deltas["T1"]["new_arrival"]) == (30, 22)
    assert deltas["T1"]["delay_change"] == -8
    assert deltas["T1"]["changed"] is True
    # T3 untouched
    assert deltas["T3"]["changed"] is False
    assert (deltas["T3"]["old_arrival"], deltas["T3"]["new_arrival"]) == (32, 32)
    # the predicted segment status overlay
    assert predicted["segment_changes"] == {"SEG-34": "closed"}


def test_preview_stacks_on_active_anomalies():
    s = AppState()
    s.inject(CLOSURE)
    predicted = s.preview([{"type": "train_delayed", "train": "T4", "minutes": 5}])
    # delta is vs the CURRENT (post-closure) state: T4 39 -> 44
    deltas = {d["id"]: d for d in predicted["deltas"]}
    assert (deltas["T4"]["old_arrival"], deltas["T4"]["new_arrival"]) == (39, 44)
    assert deltas["T4"]["delay_change"] == 5
    # already-closed SEG-34 is not a NEW change in this preview
    assert predicted["segment_changes"] == {}
    # and the active state is still just the closure
    assert s.snapshot()["anomalies"] == ["track_closed(SEG-34)"]


def test_station_times_present_for_map():
    s = AppState()
    snap = s.snapshot()
    t1 = next(t for t in snap["trains"] if t["id"] == "T1")
    assert t1["station_times"] == [["S1", 0], ["S2", 10], ["S3", 18], ["S4", 30]]
