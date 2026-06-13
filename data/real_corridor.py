"""REAL corridor: the New Delhi -> Nagpur half of the Delhi-Chennai main line
(Grand Trunk route), 21 stations, real cumulative kilometres.

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

STATIONS = [code for code, _, _ in _STOPS]
DISPLAY_NAMES = {code: name for code, name, _ in _STOPS}
CUMULATIVE_KM = {code: km for code, _, km in _STOPS}


def _segments():
    segs = []
    for (a, _, km_a), (b, _, km_b) in zip(_STOPS, _STOPS[1:]):
        km = km_b - km_a
        segs.append(Segment(f"{a}-{b}", (a, b), max(1, int(km))))
    return segs


SEGMENTS = _segments()


def _path(origin, destination):
    """Ordered segment ids along the (linear) corridor between two stations."""
    i, j = STATIONS.index(origin), STATIONS.index(destination)
    if i < j:
        return tuple(f"{STATIONS[k]}-{STATIONS[k + 1]}" for k in range(i, j))
    return tuple(f"{STATIONS[k]}-{STATIONS[k + 1]}" for k in range(i - 1, j - 1, -1))


# 5 trains, hand-verified collision-free (see tests for the tight cases):
# R1 full southbound; R2 southbound to Bhopal with 160-min headway (longest
# segment is 153 min, so the closest approach is 7 min and never a shared
# minute); R3 short southbound Bhopal->Nagpur ahead of R1; R4 short
# northbound Nagpur->Betul long before southbound traffic arrives there;
# R5 northbound Bhopal->New Delhi departing after R2 has cleared into Bhopal.
TRAINS = [
    Train("R1", "NDLS", "NGP", _path("NDLS", "NGP"), 0),
    Train("R2", "NDLS", "BPL", _path("NDLS", "BPL"), 160),
    Train("R3", "BPL", "NGP", _path("BPL", "NGP"), 30),
    Train("R4", "NGP", "BZU", _path("NGP", "BZU"), 5),
    Train("R5", "BPL", "NDLS", _path("BPL", "NDLS"), 870),
]

# DISPLAY-ONLY train attributes (never on the engine Train object; scheduling
# is unaffected). Second attribute slot pending user confirmation.
TRAIN_ATTRS = {
    "R1": {"driver_employee_no": "DRV-4102"},
    "R2": {"driver_employee_no": "DRV-2218"},
    "R3": {"driver_employee_no": "DRV-3870"},
    "R4": {"driver_employee_no": "DRV-1956"},
    "R5": {"driver_employee_no": "DRV-2741"},
}


def build_network():
    return Network(STATIONS, SEGMENTS)


def build_trains():
    return list(TRAINS)
