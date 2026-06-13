"""Rule-based dynamic pricing — a clear, inspectable FORMULA, NOT machine
learning. A fare estimate is:

    fare = base(distance) * occupancy_multiplier * time_to_departure_multiplier

  - base(distance) = BASE_FLAT + PER_KM * route_distance   (real km == minutes)
  - occupancy_multiplier = 1 + OCC_FACTOR * occupancy       (fuller -> dearer)
  - time_multiplier      = 1 + TIME_FACTOR * surge          (sooner -> dearer)

Occupancy here is SYNTHETIC demo data (production would use real bookings); it is
generated deterministically from the train id and always labelled synthetic.
Everything is a pure function: deterministic, no scheduling, no ML.
"""

CURRENCY = "₹"   # ₹

BASE_FLAT = 20.0      # fixed booking component
PER_KM = 0.5          # fare per km of route distance
OCC_FACTOR = 0.6      # a full train costs up to +60%
TIME_FACTOR = 0.4     # an imminent departure costs up to +40%
SURGE_WINDOW = 120    # minutes-to-departure over which the time premium ramps


def route_distance(network, path):
    """Route distance = sum of segment travel times along the path (km, since
    1 minute == 1 km in these datasets). 0 for a train that cannot run."""
    return sum(network.segment(s).travel_time for s in (path or ()))


def synthetic_occupancy(train_id):
    """SYNTHETIC demo occupancy in [0.35, 0.95], deterministic from the train id.
    NOT real data — production would use real bookings."""
    h = 0
    for ch in str(train_id):
        h = (h * 31 + ord(ch)) % 100000
    return round(0.35 + (h % 61) / 100.0, 2)


def time_surge(ttd_minutes):
    """Fraction of the time premium to apply: 1.0 at/after departure time, 0 once
    departure is at least SURGE_WINDOW minutes away."""
    if ttd_minutes is None:
        return 0.0
    return max(0.0, min(1.0, (SURGE_WINDOW - ttd_minutes) / SURGE_WINDOW))


def fare_estimate(distance, occupancy, ttd_minutes):
    """The pricing formula. Returns the fare plus its full breakdown (so the UI
    can show exactly how it was derived). Deterministic."""
    base = BASE_FLAT + PER_KM * distance
    occ_mult = 1 + OCC_FACTOR * occupancy
    surge = time_surge(ttd_minutes)
    time_mult = 1 + TIME_FACTOR * surge
    fare = round(base * occ_mult * time_mult)
    return {
        "fare": fare,
        "currency": CURRENCY,
        "distance": distance,
        "base": round(base),
        "occupancy": occupancy,
        "occupancy_mult": round(occ_mult, 2),
        "ttd_minutes": ttd_minutes,
        "surge": round(surge, 2),
        "time_mult": round(time_mult, 2),
    }


def fare_reason(est):
    """One-line plain reason from the breakdown — a deterministic template (NOT
    LLM-phrased), so the numbers always match the formula."""
    occ_pct = round(est["occupancy"] * 100)
    drivers = [f"{occ_pct}% full"]
    if est["surge"] >= 0.5:
        drivers.append("departs soon")
    elif est["surge"] <= 0.15:
        drivers.append("departs later")
    combined = est["occupancy_mult"] * est["time_mult"]
    level = "Higher" if combined >= 1.30 else "Lower" if combined <= 1.12 else "Standard"
    return f"{level} fare — {', '.join(drivers)} (rule-based dynamic pricing)."


# --- Stretch: a REAL moving-average forecast on OPENLY-SYNTHETIC demand --------

def synthetic_demand_series(train_id, days=14):
    """SYNTHETIC past daily demand (% full) for a train — demo data, NOT real
    bookings. Deterministic: a base level + a mild upward trend + a repeatable
    wiggle from the id."""
    base = synthetic_occupancy(train_id) * 100
    h = sum(ord(c) for c in str(train_id))
    series = []
    for d in range(days):
        wiggle = ((h + d * 7) % 17) - 8     # -8..+8, deterministic
        val = base + d * 0.6 + wiggle       # mild upward trend
        series.append(round(max(5.0, min(100.0, val)), 1))
    return series


def moving_average(series, window=3):
    """A REAL simple moving average over the series (trailing window)."""
    window = max(1, window)
    out = []
    for i in range(len(series)):
        chunk = series[max(0, i - window + 1): i + 1]
        out.append(round(sum(chunk) / len(chunk), 1))
    return out


def forecast_next(series, window=3):
    """Next-point demand projection = last trailing moving-average value (real
    arithmetic on the synthetic series)."""
    ma = moving_average(series, window)
    return ma[-1] if ma else 0.0
