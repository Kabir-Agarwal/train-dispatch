"""Real Indian Railways corridor: Mumbai CSMT -> Nagpur (Central Railway).

PHASE A — real-data experiment (branch real-railway). Maps real station,
distance and travel-time data into the EXISTING engine model (engine.model
Network/Segment/Train) WITHOUT changing any engine logic.

SOURCE
  Train 12011 (Mumbai CSMT - Nagpur), from the public Indian Railways
  "Train_details" timetable dataset
  (github.com/aaryanrr/Railway-Management, Assets/Train_details.csv — a
   per-station cumulative-distance schedule mirrored from data.gov.in).
  - Stations + cumulative kilometres: taken directly from that train's row.
  - Per-segment distance: consecutive cumulative-km differences (all positive).
  - Per-segment travel_time: the train's REAL scheduled running minutes between
    consecutive stations (this station's arrival minus previous station's
    departure) -> pure run time, matching the engine's zero-dwell assumption.
    e.g. Kalyan->Igatpuri = 125 min: the real Kasara ghat climb.

MODEL MAPPING
  - Engine station id  = real station code (CSMT, DR, TNA, ...).
  - Engine segment id  = "SEG-<from>-<to>" along the corridor.
  - travel_time (int minutes) = real running minutes above (all > 0).
  - Display-only data (city names, km, crew/loco) lives in the dicts below and
    is NEVER read by the engine — scheduling uses only the Segment/Train fields.

BASELINE (5 trains, same direction, provably collision-free)
  Single-track bidirectional segments. Same-direction trains keep constant time
  separation, so two of them share a segment only if their effective departure
  gap is <= that segment's run time; the binding segment is the longest one any
  pair shares (Kalyan->Igatpuri, 125 min). Every pair here is spaced > 125 min
  (or starts far enough down-line), so the baseline has ZERO conflicts. Arrivals
  below are tool-verified against the engine scheduler (see test_real_corridor).
    R1 CSMT->NGP dep   0 : NGP @ 790
    R2 CSMT->NGP dep 130 : NGP @ 920
    R3 CSMT->BSL dep 300 : BSL @ 713
    R4 KYN ->NGP dep 700 : NGP @ 1424
    R5 CSMT->NGP dep 900 : NGP @ 1690
  An opposite-direction full-corridor train has NO conflict-free slot while
  these five saturate the single track (confirmed by search) — true single-track
  behaviour; crossing/sequencing logic belongs to the later phases, not Phase A.
"""

from engine.model import Network, Segment, Train

# (station code, display city name, cumulative km from Mumbai CSMT)
STATIONS = [
    ("CSMT", "Mumbai CSMT", 0),
    ("DR", "Dadar", 8),
    ("TNA", "Thane", 33),
    ("KYN", "Kalyan", 53),
    ("IGP", "Igatpuri", 136),
    ("NK", "Nasik Road", 187),
    ("MMR", "Manmad", 260),
    ("JL", "Jalgaon", 419),
    ("BSL", "Bhusaval", 444),
    ("MKU", "Malkapur", 499),
    ("SEG", "Shegaon", 551),
    ("AK", "Akola", 588),
    ("MZR", "Murtajapur", 626),
    ("BD", "Badnera", 667),
    ("DMN", "Dhamangaon", 713),
    ("PLO", "Pulgaon", 733),
    ("WR", "Wardha", 762),
    ("NGP", "Nagpur", 841),
]

# real scheduled running minutes between consecutive stations (train 12011)
RUN_MINUTES = [17, 27, 22, 125, 42, 57, 98, 25, 33, 38, 25, 34, 57, 36, 16, 33, 105]

CODES = [c for c, _, _ in STATIONS]

# --- display-only lookups (engine never reads these) -----------------------
DISPLAY_NAMES = {c: name for c, name, _ in STATIONS}
STATION_KM = {c: km for c, _, km in STATIONS}


def _seg_id(a, b):
    return f"SEG-{a}-{b}"


SEGMENTS = []
SEGMENT_KM = {}
for _i in range(len(CODES) - 1):
    _a, _b = CODES[_i], CODES[_i + 1]
    SEGMENTS.append(Segment(_seg_id(_a, _