"""West Bengal state rail network — DATA LAYER ONLY (performance-probe dataset).

Assembled from public Indian Railways route knowledge (Eastern, South Eastern
and Northeast Frontier zones within West Bengal): the Howrah–Bardhaman MAIN line
(via Bandel) and the parallel Howrah–Bardhaman CHORD (via Dankuni); the
Sealdah main/north section with the Naihati–Bandel chord; the Bardhaman–Asansol
line with the Andal–Sainthia link into the Sahibganj (Rampurhat) loop; the
Katwa–Azimganj–Nalhati–New Farakka loops; the Howrah–Kharagpur line; the
Kharagpur/Adra/Purulia/Bankura cluster; and the northern Malda–New Jalpaiguri–
Alipurduar–New Cooch Behar lines (with the Dooars loop). Source overview:
en.wikipedia.org Howrah/Asansol/Kharagpur Junction + Sealdah-section articles,
fetched 2026-06-13.

This is built to mirror data/real_corridor.py exactly (same engine model — no
engine change). Distances are approximate published section km; travel_time
minutes == km (~60 km/h, min 1), the same convention the real corridor uses.

PURPOSE: a deliberately MESHY state graph (many chord/loop lines) to probe how
the engine's full-DFS route enumeration scales before any UI work. It is a
faithful-but-approximate topology for that probe, not a signalling-grade map.
"""

from engine.model import Network, Segment, Train

# code -> display name
_STATIONS = {
    "HWH": "Howrah Jn", "BLY": "Bally", "SRP": "Serampore", "CGR": "Chandan Nagar",
    "BDC": "Bandel Jn", "MYM": "Memari", "BWN": "Barddhaman Jn", "DKAE": "Dankuni",
    "SKG": "Saktigarh", "SRC": "Santragachi", "ULB": "Uluberia", "MCA": "Mecheda",
    "PKU": "Panskura", "KGP": "Kharagpur Jn", "SDAH": "Sealdah", "DDJ": "Dum Dum",
    "BT": "Barrackpore", "NH": "Naihati Jn", "RHA": "Ranaghat Jn",
    "KNJ": "Krishnanagar City", "BNJ": "Bangaon Jn", "STB": "Shantipur",
    "BPC": "Berhampore Court", "LGL": "Lalgola", "AZ": "Azimganj Jn",
    "KWAE": "Katwa Jn", "NHT": "Nalhati Jn", "NFK": "New Farakka Jn",
    "BHP": "Bolpur Shantiniketan", "SNT": "Sainthia Jn", "RPH": "Rampurhat Jn",
    "DGR": "Durgapur", "UDL": "Andal Jn", "ASN": "Asansol Jn", "MLDT": "Malda Town",
    "NJP": "New Jalpaiguri", "SGUJ": "Siliguri Jn", "NMZ": "New Mal Jn",
    "HSA": "Hasimara", "APDJ": "Alipurduar Jn", "NCB": "New Cooch Behar",
    "MDN": "Midnapore", "JGM": "Jhargram", "BQA": "Bankura", "BPRS": "Bishnupur",
    "PRR": "Purulia Jn", "TMZ": "Tamluk", "DGH": "Digha", "HLZ": "Haldia",
}

# (a, b, km) — bidirectional single-track sections.
_SEG = [
    # Howrah–Bardhaman MAIN (via Bandel)
    ("HWH", "BLY", 8), ("BLY", "SRP", 12), ("SRP", "CGR", 12), ("CGR", "BDC", 8),
    ("BDC", "MYM", 28), ("MYM", "BWN", 28),
    # Howrah–Bardhaman CHORD (via Dankuni)  -> loop with the main line
    ("HWH", "DKAE", 18), ("DKAE", "SKG", 50), ("SKG", "BWN", 30),
    # Howrah–Kharagpur
    ("HWH", "SRC", 6), ("SRC", "ULB", 30), ("ULB", "MCA", 30), ("MCA", "PKU", 22),
    ("PKU", "KGP", 35), ("SRC", "DKAE", 12),   # Santragachi–Dankuni link
    # Sealdah main/north
    ("SDAH", "DDJ", 6), ("DDJ", "BT", 18), ("BT", "NH", 14), ("NH", "RHA", 30),
    ("RHA", "KNJ", 32), ("NH", "BDC", 8),       # Naihati–Bandel chord -> loop
    ("RHA", "BNJ", 38), ("RHA", "STB", 13),
    # Lalgola line + cross to Azimganj
    ("KNJ", "BPC", 70), ("BPC", "LGL", 38), ("BPC", "AZ", 12),
    # Katwa–Azimganj–Nalhati–New Farakka loops
    ("BDC", "KWAE", 42), ("BWN", "KWAE", 53), ("KWAE", "AZ", 35),
    ("AZ", "NHT", 30), ("AZ", "NFK", 40),
    # Sahibganj / Rampurhat loop
    ("BWN", "BHP", 41), ("BHP", "SNT", 28), ("SNT", "RPH", 30), ("RPH", "NHT", 17),
    ("NHT", "NFK", 35),
    # Bardhaman–Asansol + Andal–Sainthia link (joins Asansol line to the loop)
    ("BWN", "DGR", 64), ("DGR", "UDL", 12), ("UDL", "ASN", 23), ("UDL", "SNT", 60),
    ("ASN", "ADRA", 100),
    # North Bengal + Dooars loop
    ("NFK", "MLDT", 40), ("MLDT", "NJP", 220), ("NJP", "SGUJ", 8),
    ("NJP", "NCB", 120), ("SGUJ", "NMZ", 50), ("NMZ", "HSA", 60), ("HSA", "APDJ", 30),
    ("APDJ", "NCB", 60),
    # Kharagpur / Adra / Purulia / Bankura cluster
    ("KGP", "MDN", 18), ("MDN", "ADRA", 100), ("KGP", "JGM", 45),
    ("ADRA", "BQA", 42), ("BQA", "BPRS", 35), ("ADRA", "PRR", 40),
    # South branches
    ("PKU", "TMZ", 30), ("TMZ", "DGH", 40), ("PKU", "HLZ", 35),
]

# ADRA has no display name above (it is an interchange we route through); add it.
_STATIONS["ADRA"] = "Adra Jn"

STATIONS = list(_STATIONS)
DISPLAY_NAMES = dict(_STATIONS)

SEGMENTS = [Segment(f"{a}-{b}", (a, b), max(1, int(km))) for a, b, km in _SEG]

_ADJ = {}
for a, b, _ in _SEG:
    _ADJ[(a, b)] = f"{a}-{b}"
    _ADJ[(b, a)] = f"{a}-{b}"


def _route(*stations):
    """Segment ids for a sequence of adjacent stations (raises if any hop is not
    a real section)."""
    segs = []
    for x, y in zip(stations, stations[1:]):
        if (x, y) not in _ADJ:
            raise ValueError(f"no section between {x} and {y}")
        segs.append(_ADJ[(x, y)])
    return tuple(segs)


# Representative services crossing the network — many run through the densest
# junction (Barddhaman, BWN). Departures spread; the probe does not require a
# collision-free baseline (recompute uses build_schedule only for reference).
TRAINS = [
    Train("T1", "HWH", "NJP",
          _route("HWH", "BLY", "SRP", "CGR", "BDC", "MYM", "BWN", "BHP", "SNT",
                 "RPH", "NHT", "NFK", "MLDT", "NJP"), 0),
    Train("T2", "HWH", "ASN",
          _route("HWH", "BLY", "SRP", "CGR", "BDC", "MYM", "BWN", "DGR", "UDL",
                 "ASN"), 30),
    Train("T3", "SDAH", "NJP",
          _route("SDAH", "DDJ", "BT", "NH", "RHA", "KNJ", "BPC", "AZ", "NFK",
                 "MLDT", "NJP"), 15),
    Train("T4", "HWH", "APDJ",
          _route("HWH", "DKAE", "SKG", "BWN", "BHP", "SNT", "RPH", "NHT", "NFK",
                 "MLDT", "NJP", "NCB", "APDJ"), 45),
    Train("T5", "KGP", "ASN", _route("KGP", "MDN", "ADRA", "ASN"), 20),
    Train("T6", "HWH", "PRR",
          _route("HWH", "SRC", "ULB", "MCA", "PKU", "KGP", "MDN", "ADRA", "PRR"), 60),
    Train("T7", "SDAH", "LGL",
          _route("SDAH", "DDJ", "BT", "NH", "RHA", "KNJ", "BPC", "LGL"), 10),
    Train("T8", "NJP", "APDJ", _route("NJP", "SGUJ", "NMZ", "HSA", "APDJ"), 0),
    Train("T9", "BWN", "KWAE", _route("BWN", "KWAE"), 25),
    Train("T10", "HWH", "BPRS",
          _route("HWH", "SRC", "ULB", "MCA", "PKU", "KGP", "MDN", "ADRA", "BQA",
                 "BPRS"), 35),
    Train("T11", "HWH", "KGP",
          _route("HWH", "SRC", "ULB", "MCA", "PKU", "KGP"), 50),
    Train("T12", "ASN", "HWH",
          _route("ASN", "UDL", "DGR", "BWN", "MYM", "BDC", "CGR", "SRP", "BLY",
                 "HWH"), 70),
]


def build_network():
    return Network(STATIONS, SEGMENTS)


def build_trains():
    return list(TRAINS)
