"""Gate: routes unit. Hand-verified path sets on the baseline network.

S1->S4 simple paths (travel minutes):
  [SEG-15,SEG-45]=22  [SEG-12,SEG-23,SEG-34]=30  [SEG-12,SEG-23,SEG-36,SEG-56,SEG-45]=45
  [SEG-12,SEG-26,SEG-56,SEG-45]=46  [SEG-15,SEG-56,SEG-36,SEG-34]=47
  [SEG-12,SEG-26,SEG-36,SEG-34]=53  [SEG-15,SEG-56,SEG-26,SEG-23,SEG-34]=64   (7 total)
S4->S6 simple paths:
  [SEG-45,SEG-56]=16  [SEG-34,SEG-36]=23  [SEG-34,SEG-23,SEG-26]=40
  [SEG-45,SEG-15,SEG-12,SEG-23,SEG-36]=51  [SEG-45,SEG-15,SEG-12,SEG-26]=52
  [SEG-34,SEG-23,SEG-12,SEG-15,SEG-56]=54   (6 total)
"""

from data.baseline import build_network
from engine.anomalies import TrackClosed, apply_anomalies
from engine.routes import all_open_paths, path_stations


def test_s1_to_s4_paths_hand_verified():
    paths = all_open_paths(build_network(), "S1", "S4")
    assert len(paths) == 7
    assert paths[0] == ("SEG-15", "SEG-45")              # 22 min, fastest
    assert paths[1] == ("SEG-12", "SEG-23", "SEG-34")    # 30 min, the baseline path


def test_s4_to_s6_paths_hand_verified():
    paths = all_open_paths(build_network(), "S4", "S6")
    assert len(paths) == 6
    assert paths[0] == ("SEG-45", "SEG-56")  # 16 min
    assert paths[1] == ("SEG-34", "SEG-36")  # 23 min


def test_closure_filters_paths():
    eff = apply_anomalies(build_network(), [TrackClosed("SEG-34")])
    paths = all_open_paths(eff, "S1", "S4")
    assert len(paths) == 3  # the 4 paths using SEG-34 are gone
    assert paths[0] == ("SEG-15", "SEG-45")
    assert all("SEG-34" not in p for p in paths)


def test_unreachable_returns_empty():
    eff = apply_anomalies(
        build_network(), [TrackClosed("SEG-34"), TrackClosed("SEG-45")]
    )
    assert all_open_paths(eff, "S1", "S4") == []


def test_path_stations():
    net = build_network()
    assert path_stations(net, "S1", ("SEG-15", "SEG-45")) == ["S1", "S5", "S4"]
    assert path_stations(net, "S4", ("SEG-34", "SEG-36")) == ["S4", "S3", "S6"]
