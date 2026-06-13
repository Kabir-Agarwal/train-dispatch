"""Gate: real corridor (Phase A). Real km from the published GT Express
timetable; every assert hand-verified against the source values."""

import time

from data.real_corridor import (
    CUMULATIVE_KM,
    DISPLAY_NAMES,
    TRAIN_ATTRS,
    build_network,
    build_trains,
)
from engine.anomalies import TrainDelayed
from engine.collision import find_conflicts
from engine.impact import destination_reachable
from engine.model import Train
from engine.recompute import recompute_schedule
from engine.scheduler import load_baseline


def test_corridor_loads_with_zero_conflicts():
    schedule, table = load_baseline(build_network(), build_trains())
    assert find_conflicts(table) == []
    net = build_network()
    assert len(net.stations) == 27  # 21 trunk + 6 loop (Phase B)
    assert len(net.segment_ids()) == 27  # 20 trunk + 7 loop
    assert len(build_trains()) == 8


def test_real_distances_hand_verified_and_positive():
    net = build_network()
    # spot checks straight from the published cumulative km
    assert net.segment("NDLS-MTJ").travel_time == 141   # 141 - 0
    assert net.segment("VGLJ-BINA").travel_time == 153  # 563 - 410 (longest)
    assert net.segment("BPL-RKMP").travel_time == 6     # 707 - 701 (shortest)
    assert net.segment("NRKR-NGP").travel_time == 86    # 1090 - 1004
    for seg_id in net.segment_ids():
        assert net.segment(seg_id).travel_time > 0, seg_id
    # cumulative anchor: the corridor is 1090 real km
    assert CUMULATIVE_KM["NGP"] == 1090


def test_network_is_one_connected_component():
    net = build_network()
    for station in net.stations:
        assert destination_reachable(net, "NDLS", station), station


def test_arrivals_hand_verified():
    schedule, _ = load_baseline(build_network(), build_trains())
    assert schedule["T101"]["BPL"] == 701      # cumulative km == minutes at 60 km/h
    assert schedule["T101"]["NGP"] == 1090
    assert schedule["T102"]["BPL"] == 861      # 160 + 701
    assert schedule["T103"]["NGP"] == 419      # 30 + (1090 - 701)
    assert schedule["T104"]["BZU"] == 195      # 5 + (1090 - 900)
    assert schedule["T105"]["NDLS"] == 1571    # 870 + 701


def test_tightest_headway_is_seven_minutes_not_a_conflict():
    # T101 occupies VGLJ-BINA [410,563]; T102 (dep 160) occupies [570,723].
    _, table = load_baseline(build_network(), build_trains())
    windows = sorted(
        (o.start, o.end) for o in table if o.segment_id == "VGLJ-BINA"
    )
    # T101 [410,563], T102 [570,723] (7 clear min), T106 [730,883] (7 clear min
    # behind T102), T105 northbound [1008,1161] (= 870 + (701-563) entry).
    assert windows == [(410, 563), (570, 723), (730, 883), (1008, 1161)]


def test_display_attrs_present_and_not_on_engine_objects():
    trains = build_trains()
    for t in trains:
        assert TRAIN_ATTRS[t.id]["driver_employee_no"].startswith("DRV-")
        assert not hasattr(t, "driver_employee_no")  # engine model untouched
    assert DISPLAY_NAMES["NDLS"] == "New Delhi"
    assert len(set(DISPLAY_NAMES.values())) == 27  # names unique


def test_collision_checker_and_recompute_are_fast_at_this_size():
    net, trains = build_network(), build_trains()
    t0 = time.perf_counter()
    _, table = load_baseline(net, trains)
    load_s = time.perf_counter() - t0

    t0 = time.perf_counter()
    for _ in range(100):
        find_conflicts(table)
    check_s = (time.perf_counter() - t0) / 100

    # the expensive path: a delay that forces T102 into a hold search
    t0 = time.perf_counter()
    result = recompute_schedule(net, trains, [TrainDelayed("T101", 30)])
    recompute_s = time.perf_counter() - t0
    assert find_conflicts(list(result.occupancy_table)) == []
    # T101 +30 shrinks the VGLJ-BINA gap to -23 -> T102 must hold 24 min
    assert result.actions["T102"].action == "hold"
    assert result.actions["T102"].depart_at == 184

    assert load_s < 0.5, load_s
    assert check_s < 0.05, check_s
    assert recompute_s < 2.0, recompute_s
    print(f"\nperf: load={load_s*1000:.1f}ms  "
          f"collision_check={check_s*1000:.2f}ms  recompute={recompute_s*1000:.0f}ms")


# --- Phase B: the loop corridor ------------------------------------------

def test_loop_distances_hand_verified():
    net = build_network()
    # differences of the 11271 Vindhyachal cumulative km
    assert net.segment("BINA-SGO").travel_time == 75
    assert net.segment("DMO-KMZ").travel_time == 109
    assert net.segment("KMZ-JBP").travel_time == 91
    # cross-confirmed by the 18234 Narmada Express table:
    assert net.segment("JBP-NU").travel_time == 84   # 495-411
    assert net.segment("NU-PPI").travel_time == 94   # 589-495
    assert net.segment("PPI-ET").travel_time == 68   # 656-589 = 67, 11271 says 68


def test_bina_et_is_a_real_diamond():
    from engine.routes import all_open_paths
    net = build_network()
    paths = all_open_paths(net, "BINA", "ET")
    assert len(paths) == 2
    # fastest is the trunk via Bhopal (230 min), the loop is 598
    assert paths[0] == ("BINA-BAQ", "BAQ-BHS", "BHS-BPL", "BPL-RKMP",
                        "RKMP-NDPM", "NDPM-ET")
    assert paths[1] == ("BINA-SGO", "SGO-DMO", "DMO-KMZ", "KMZ-JBP",
                        "JBP-NU", "NU-PPI", "PPI-ET")


def test_new_train_arrivals_hand_verified():
    schedule, _ = load_baseline(build_network(), build_trains())
    assert schedule["T106"]["BINA"] == 883     # 320 + 563
    assert schedule["T106"]["JBP"] == 1235     # 883 + 75+77+109+91
    assert schedule["T107"]["JBP"] == 346      # 100 + 68+94+84
    assert schedule["T107"]["BINA"] == 698     # 100 + 598
    assert schedule["T108"]["ET"] == 946       # 700 + 84+94+68


def test_loop_attrs_and_loco_classes():
    for tid, attrs in TRAIN_ATTRS.items():
        assert attrs["loco_class"].startswith(("WAP", "WAG", "WDM")), tid
        assert attrs["driver_employee_no"].startswith("DRV-"), tid
    assert TRAIN_ATTRS["T101"]["loco_class"] == "WAP-7"
    assert len(TRAIN_ATTRS) == 8
