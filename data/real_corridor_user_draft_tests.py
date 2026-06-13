"""Gate: real corridor (Phase A) — Mumbai CSMT -> Nagpur, train 12011.

Every assert is a real expected value: segment travel_times are the train's
real timetable running minutes, segment distances are real cumulative-km
differences, and arrivals/occupancy windows are tool-verified against the
engine scheduler. Nothing here injects an anomaly — Phase A is data + load +
connectivity + performance only.
"""

import time

from data.real_corridor import (
    DISPLAY_NAMES,
    RUN_MINUTES,
    SEGMENT_KM,
    STATION_KM,
    TRAIN_DISPLAY,
    build_network,
    build_trains,
)
from engine.collision import find_conflicts
from engine.impact import destination_reachable
from engine.model import Train
from engine.routes import all_open_paths
from engine.scheduler import load_baseline


def test_corridor_shape():
    net = build_network()
    assert len(net.stations) == 18
    assert len(net.segment_ids()) == 17
    assert len(build_trains()) == 5
    assert net.stations[0] == "CSMT" and net.stations[-1] == "NGP"


def test_corridor_loads_with_zero_conflicts():
    schedule, table = load_baseline(build_network(), build_trains())
    assert find_conflicts(table) == []
    # 17 + 17 + 8 + 14 + 17 segment occupations across R1..R5
    assert len(table) == 73


def test_travel_times_are_real_running_minutes_all_positive():
    net = build_network()
    # spot checks straight from train 12011's timetable (arrival - prev departure)
    assert net.segment("SEG-CSMT-DR").travel_time == 17
    assert net.segment("SEG-KYN-IGP").travel_time == 125   # real Kasara ghat climb
    assert net.segment("SEG-PLO-WR").travel_time == 33
    assert net.segment("SEG-WR-NGP").travel_time == 105
    times = [net.segment(s).travel_time for s in net.segment_ids()]
    assert times == RUN_MINUTES
    for s in net.segment_ids():
        assert net.segment(s).travel_time > 0, s


def test_distances_real_and_positive():
    # per-segment km = consecutive cumulative-km differences, all positive
    assert SEGMENT_KM["SEG-CSMT-DR"] == 8        # 8 - 0
    assert SEGMENT_KM["SEG-JL-BSL"] == 25        # 444 - 419
    assert SEGMENT_KM["SEG-WR-NGP"] == 79        # 841 - 762
    assert all(km > 0 for km in SEGMENT_KM.values())
    assert STATION_KM["NGP"] == 841              # corridor is 841 real km
    assert sum(SEGMENT_KM.values()) == 841       # km differences tile the corridor


def test_network_is_one_connected_component():
    net = build_network()
    for station in net.stations:
        assert destination_reachable(net, "CSMT", station), station


def test_arrivals_hand_verified():
    schedule, _ = load_baseline(build_network(), build_trains())
    assert schedule["R1"]["NGP"] == 790
    assert schedule["R2"]["NGP"] == 920
    assert schedule["R3"]["BSL"] == 713
    assert schedule["R4"]["NGP"] == 1424
    assert schedule["R5"]["NGP"] == 1690
    # full origin->destination walk for the lead train, tool-verified
    assert schedule["R1"] == {
        "CSMT": 0, "DR": 17, "TNA": 44, "KYN": 66, "IGP": 191, "NK": 233,
        "MMR": 290, "JL": 388, "BSL": 413, "MKU": 446, "SEG": 484, "AK": 509,
        "MZR": 543, "BD": 600, "DMN": 636, "PLO": 652, "WR": 685, "NGP": 790,
    }


def test_tightest_clean_headway_on_the_ghat_is_five_minutes():
    # The 125-min Kalyan->Igatpuri ghat is the binding segment. R1 exits at 191,
    # R2 enters at 196 -> 5 clear minutes, proving the checker is not
    # over-flagging near-misses on a real long section.
    _, table = load_baseline(build_network(), build_trains())
    windows = sorted(
        (o.start, o.end) for o in table if o.segment_id == "SEG-KYN-IGP"
    )
    assert windows == [(66, 191), (196, 321), (366, 491), (700, 825), (966, 1091)]


def test_display_fields_present_and_not_on_engine_objects():
    trains = build_trains()
    for t in trains:
        d = TRAIN_DISPLAY[t.id]
        assert d["driver_emp"].startswith("EMP-")
        assert d["loco_no"]                       # locomotive number present
        # displa