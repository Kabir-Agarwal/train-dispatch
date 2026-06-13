"""REAL two-corridor network (27 stations):
1. Trunk: New Delhi -> Nagpur half of the Delhi-Chennai main line (Grand
   Trunk route), 21 stations, real cumulative km (train 12616 timetable).
2. Loop: the real Bina - Saugor - Damoh - Katni - Jabalpur - Itarsi line —
   an actual alternative route between BINA and ET avoiding Bhopal, from
   the 11271 Vindhyachal Express timetable (ET->BPL the long way; cumulative
   km ET=0, PPI=68, NU=162, JBP=246, KMZ=337, DMO=446, SGO=523, BINA=598).
   Three legs independently confirmed by the 18234 Narmada Express table
   (JBP-NU 84, NU-PPI 94, PPI-ET 67-68 km). BINA<->ET is therefore a real
   diamond: closures between them can REROUTE instead of stranding.

Source: official IRCTC timetable of train 12616 Grand Trunk Express as
published on confirmtkt.com/train-schedule/12616 (IRCTC partner), fetched
2026-06-13. Distances are the published cumulative km per stop; inter-station
distance = difference of consecutive cumulative km.

Conversion decision (logged in PROGRESS): the GT Express covers these 1090 km
in ~18h, an end-to-end average of ~60 km/h, so travel_time minutes ==
inter-station km (max 1). Engine model is UNCHANGED — same Segment/Train.

Driver employee numbers are SYNTHETIC display-only placeholders (DRV-xxxx) —
not real people. They do not exist on the engine Train object at all.
"""

from engine.model import Network, Segment, Train

# (code, display name, cumulative km from New Delhi)
_STOPS = [
    ("NDLS", "New Delhi", 0),
    ("MTJ", "Mathura Jn", 141),
    ("BFP", "Bilochpura Agra", 190),
    ("AGC", "Agra Cantt", 195),
    ("DHO", "Dhaulpur", 247),
    ("MRA", "Morena", 275),
    ("GWL", "Gwalior", 313),
    ("VGLJ", "V. Lakshmibai Jhansi", 410),
    ("BINA", "Bina Jn", 563),
    ("BAQ", "Ganj Basoda", 609),
    ("BHS", "Vidisha", 648),
    ("BPL", "Bhopal Jn", 701),
    ("RKMP", "Rani Kamalapati", 707),
    ("NDPM", "Narmadapuram", 775),
    ("ET", "Itarsi Jn", 793),
    ("GDYA", "Ghoradongri", 863),
    ("BZU", "Betul", 900),
    ("AMLA", "Amla Jn", 923),
    ("PAR", "Pandhurna", 986),
    ("NRKR", "Narkher", 1004),
    ("NGP", "Nagpur", 1090),
]

_LOOP_STOPS = [
    ("PPI", "Pipariya", 68),
    ("NU", "Narsinghpur", 162),
    ("JBP", "Jabalpur", 246),
    ("KMZ", "Katni Murwara", 337),
    ("DMO", "Damoh", 446),
    ("SGO", "Saugor", 523),
]

STATIONS = [code for code, _, _ in _STOPS] + [c for c, _, _ in _LOOP_STOPS]
DISPLAY_NAMES = {code: name for code, name, _ in _STOPS}
DISPLAY_NAMES.update({code: name for code, name, _ in _LOOP_STOPS})
CUMULATIVE_KM = {code: km for code, _, km in _STOPS}


def _segments():
    segs = []
    for (a, _, km_a), (b, _, km_b) in zip(_STOPS, _STOPS[1:]):
        km = km_b - km_a
        segs.append(Segment(f"{a}-{b}", (a, b), max(1, int(km))))
    return segs


# Loop segments in BINA->ET travel order; lengths = differences of the
# 11271 cumulative km (75, 77, 109, 91, 84, 94, 68).
_LOOP_SEGMENTS = [
    Segment("BINA-SGO", ("BINA", "SGO"), 75),
    Segment("SGO-DMO", ("SGO", "DMO"), 77),
    Segment("DMO-KMZ", ("DMO", "KMZ"), 109),
    Segment("KMZ-JBP", ("KMZ", "JBP"), 91),
    Segment("JBP-NU", ("JBP", "NU"), 84),
    Segment("NU-PPI", ("NU", "PPI"), 94),
    Segment("PPI-ET", ("PPI", "ET"), 68),
]

SEGMENTS = _segments() + _LOOP_SEGMENTS


def _path(origin, destination):
    """Ordered segment ids along the (linear) corridor between two stations."""
    i, j = STATIONS.index(origin), STATIONS.index(destination)
    if i < j:
        return tuple(f"{STATIONS[k]}-{STATIONS[k + 1]}" for k in range(i, j))
    return tuple(f"{STATIONS[k]}-{STATIONS[k + 1]}" for k in range(i - 1, j - 1, -1))


# 5 trains, hand-verified collision-free (see tests for the tight cases):
# T101 full southbound; T102 southbound to Bhopal with 160-min headway (longest
# segment is 153 min, so the closest approach is 7 min and never a shared
# minute); T103 short southbound Bhopal->Nagpur ahead of T101; T104 short
# northbound Nagpur->Betul long before southbound traffic arrives there;
# T105 northbound Bhopal->New Delhi departing after T102 has cleared into Bhopal.
# T106 NDLS->JBP via the loop, dep 320 (same 7-min closest approach behind T102
# on VGLJ-BINA; leaves the trunk at BINA before T105's northbound crossing
# point at km ~625). T107 ET->BINA via the loop, dep 100 (Vindhyachal
# pattern). T108 JBP->ET, dep 700. Pairwise hand-verified in the gates.
TRAINS = [
    Train("T101", "NDLS", "NGP", _path("NDLS", "NGP"), 0),
    Train("T102", "NDLS", "BPL", _path("NDLS", "BPL"), 160),
    Train("T103", "BPL", "NGP", _path("BPL", "NGP"), 30),
    Train("T104", "NGP", "BZU", _path("NGP", "BZU"), 5),
    Train("T105", "BPL", "NDLS", _path("BPL", "NDLS"), 870),
    Train("T106", "NDLS", "JBP",
          _path("NDLS", "BINA") + ("BINA-SGO", "SGO-DMO", "DMO-KMZ", "KMZ-JBP"),
          320),
    Train("T107", "ET", "BINA",
          ("PPI-ET", "NU-PPI", "JBP-NU", "KMZ-JBP", "DMO-KMZ", "SGO-DMO", "BINA-SGO"),
          100),
    Train("T108", "JBP", "ET", ("JBP-NU", "NU-PPI", "PPI-ET"), 700),
]

# DISPLAY-ONLY train attributes (never on the engine Train object; scheduling
# is unaffected). Second attribute slot pending user confirmation.
# loco_class values are real Indian Railways classes (GT Express runs behind
# a WAP-7; loop services typically WAP-4/WDM-3A). Display-only flavor.
TRAIN_ATTRS = {
    "T101": {"driver_employee_no": "DRV-4102", "loco_class": "WAP-7"},
    "T102": {"driver_employee_no": "DRV-2218", "loco_class": "WAP-7"},
    "T103": {"driver_employee_no": "DRV-3870", "loco_class": "WAP-4"},
    "T104": {"driver_employee_no": "DRV-1956", "loco_class": "WAG-9"},
    "T105": {"driver_employee_no": "DRV-2741", "loco_class": "WAP-4"},
    "T106": {"driver_employee_no": "DRV-5519", "loco_class": "WAP-4"},
    "T107": {"driver_employee_no": "DRV-6034", "loco_class": "WAP-4"},
    "T108": {"driver_employee_no": "DRV-7178", "loco_class": "WDM-3A"},
}


# Illustrative train sizes (coach counts) — per-train load weight for the
# cumulative-load maintenance heuristic only; the scheduling engine ignores it.
LOAD_WEIGHTS = {
    "T101": 24, "T102": 22, "T103": 18, "T104": 16,
    "T105": 22, "T106": 18, "T107": 16, "T108": 14,
}


def build_network():
    return Network(STATIONS, SEGMENTS)


def build_trains():
    return list(TRAINS)
