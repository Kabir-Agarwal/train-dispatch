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


# Representative services with VARIED origins/destinations spread across the
# whole state (north: NJP/Malda/Alipurduar; south/Kolkata: Howrah/Sealdah/Digha/
# Haldia; west: Asansol/Adra/Purulia/Kharagpur; east border: Bangaon/Lalgola) —
# 12 different origin stations, so the network looks realistically busy rather
# than all leaving from one place. Departures are staggered. T1 still runs the
# Howrah–Barddhaman MAIN line so the default money-shot (closing MYM-BWN) reroutes
# it onto the Dankuni chord. Routes are validated for adjacency by _route().
TRAINS = [
    # south -> far north (main + Rampurhat loop): the money-shot train
    Train("T1", "HWH", "NJP",
          _route("HWH", "BLY", "SRP", "CGR", "BDC", "MYM", "BWN", "BHP", "SNT",
                 "RPH", "NHT", "NFK", "MLDT", "NJP"), 0),
    # Sealdah -> Malda Town (south-east -> north-central, via the Lalgola line).
    # Terminates at Malda (NOT carried on to NJP/APDJ) so it does NOT share the
    # 220-min Malda-NJP single track with the money-shot pair T1 (HWH->NJP) and
    # T3 (NJP->HWH); that head-on otherwise forces ~600 min of holds and a dead,
    # mostly-parked clip. With T2 off it, simMax drops 1056 -> 835 and T2 runs
    # early instead of waiting. Still a long cross-state Kolkata->Malda service.
    Train("T2", "SDAH", "MLDT",
          _route("SDAH", "DDJ", "BT", "NH", "RHA", "KNJ", "BPC", "AZ", "NFK",
                 "MLDT"), 20),
    # north -> south (opposite direction down the main line)
    Train("T3", "NJP", "HWH",
          _route("NJP", "MLDT", "NFK", "NHT", "RPH", "SNT", "BHP", "BWN", "MYM",
                 "BDC", "CGR", "SRP", "BLY", "HWH"), 35),
    # west: Asansol -> Kharagpur (via Adra / Midnapore)
    Train("T4", "ASN", "KGP", _route("ASN", "ADRA", "MDN", "KGP"), 15),
    # far west: Purulia -> Howrah
    Train("T5", "PRR", "HWH",
          _route("PRR", "ADRA", "MDN", "KGP", "PKU", "MCA", "ULB", "SRC", "HWH"), 25),
    # south coast: Digha -> Barddhaman (via the Dankuni chord)
    Train("T6", "DGH", "BWN",
          _route("DGH", "TMZ", "PKU", "MCA", "ULB", "SRC", "DKAE", "SKG", "BWN"), 40),
    # east border: Bangaon -> Sealdah
    Train("T7", "BNJ", "SDAH",
          _route("BNJ", "RHA", "NH", "BT", "DDJ", "SDAH"), 10),
    # far north Dooars loop: Alipurduar -> New Jalpaiguri
    Train("T8", "APDJ", "NJP", _route("APDJ", "HSA", "NMZ", "SGUJ", "NJP"), 5),
    # north-east border: Lalgola -> Azimganj
    Train("T9", "LGL", "AZ", _route("LGL", "BPC", "AZ"), 35),
    # south-west: Kharagpur -> Bishnupur
    Train("T10", "KGP", "BPRS",
          _route("KGP", "MDN", "ADRA", "BQA", "BPRS"), 45),
    # south port: Haldia -> Howrah
    Train("T11", "HLZ", "HWH",
          _route("HLZ", "PKU", "MCA", "ULB", "SRC", "HWH"), 50),
    # central short hop: Barddhaman -> Katwa
    Train("T12", "BWN", "KWAE", _route("BWN", "KWAE"), 25),
]


# Illustrative train sizes (coach counts) used ONLY as the per-train load weight
# in the cumulative-load maintenance heuristic — long-distance trains stress the
# track more than locals. Not used by the scheduling engine.
LOAD_WEIGHTS = {
    "T1": 22, "T2": 20, "T3": 22, "T4": 24, "T5": 14, "T6": 18,
    "T7": 12, "T8": 10, "T9": 12, "T10": 16, "T11": 12, "T12": 20,
}


def build_network():
    return Network(STATIONS, SEGMENTS)


def build_trains():
    return list(TRAINS)
