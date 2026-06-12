"""Hand-built demo network: 6 stations (appendable), 7 segments, 5 trains.

Hand-verified baseline (all minutes):
  T1 S1->S4 via SEG-12,SEG-23,SEG-34 dep 0 : S2@10 S3@18 S4@30
       occupies SEG-12[0,10] SEG-23[10,18] SEG-34[18,30]
  T2 S1->S6 via SEG-15,SEG-56       dep 5 : S5@20 S6@29
       occupies SEG-15[5,20] SEG-56[20,29]
  T3 S2->S6 via SEG-26              dep 12: S6@32
       occupies SEG-26[12,32]
  T4 S4->S6 via SEG-45,SEG-56       dep 23: S5@30 S6@39
       occupies SEG-45[23,30] SEG-56[30,39]
       (SEG-56: T2 exits at 29, T4 enters at 30 -> clean by exactly 1 minute)
  T5 S4->S1 via SEG-34,SEG-23,SEG-12 dep 40: S3@52 S2@60 S1@70
       occupies SEG-34[40,52] SEG-23[52,60] SEG-12[60,70]
       (no overlap with T1, whose last occupation ends at minute 30)
"""

from engine.model import Network, Segment, Train

STATIONS = ["S1", "S2", "S3", "S4", "S5", "S6"]

SEGMENTS = [
    Segment("SEG-12", ("S1", "S2"), 10),
    Segment("SEG-23", ("S2", "S3"), 8),
    Segment("SEG-34", ("S3", "S4"), 12),
    Segment("SEG-45", ("S4", "S5"), 7),
    Segment("SEG-56", ("S5", "S6"), 9),
    Segment("SEG-15", ("S1", "S5"), 15),
    Segment("SEG-26", ("S2", "S6"), 20),
    Segment("SEG-36", ("S3", "S6"), 11),  # used by NO baseline train (no-impact tests, reroute option)
]

TRAINS = [
    Train("T1", "S1", "S4", ("SEG-12", "SEG-23", "SEG-34"), 0),
    Train("T2", "S1", "S6", ("SEG-15", "SEG-56"), 5),
    Train("T3", "S2", "S6", ("SEG-26",), 12),
    Train("T4", "S4", "S6", ("SEG-45", "SEG-56"), 23),
    Train("T5", "S4", "S1", ("SEG-34", "SEG-23", "SEG-12"), 40),
]


def build_network():
    return Network(STATIONS, SEGMENTS)


def build_trains():
    return list(TRAINS)


def conflicting_trains():
    """Baseline variant with a deliberate boundary conflict on SEG-56:
    T4 departing at 22 occupies SEG-45[22,29] then SEG-56[29,38];
    T2 occupies SEG-56[20,29] -> both on SEG-56 at minute 29."""
    trains = [t for t in TRAINS if t.id != "T4"]
    trains.append(Train("T4", "S4", "S6", ("SEG-45", "SEG-56"), 22))
    return trains
