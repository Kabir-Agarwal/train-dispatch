"""Phase H — eco-driving speed profiles.

For a train that must cover a route of `distance_km` in `scheduled_min`, the
energy-aware way to drive is the classic CRUISE -> COAST -> BRAKE structure: hold
the scheduled average speed, then cut power and coast/brake into the stop —
instead of running FLAT-OUT to the line speed limit and braking the surplus
kinetic energy away at the end. (NOTE: this module does NOT solve the optimal-
control problem; the energy saving comes entirely from the lower average speed —
the coast/brake phases are illustrative, not separately optimised.)

Energy model (simplified, honest): traction must overcome running resistance,
whose dominant term grows with v**2 (aerodynamic/quadratic Davis term), so the
specific traction energy over a fixed distance scales with the square of the
speed held. Therefore:

    energy(distance, v)  ~  v**2 * distance
    energy_saved_fraction = 1 - (v_avg / v_max)**2

where v_avg = distance / time is the speed the eco profile holds to arrive exactly
on schedule, and v_max is the line speed a flat-out run would use. This is an
ILLUSTRATIVE model (a constant resistance coefficient, no gradient/regen/traction-
curve detail), NOT a traction simulation — labelled as such in the UI.

Pure and deterministic. Uses only the route distance/time the rest of the app
already has; touches no scheduling, so the recompute golden is unaffected.
"""

# Illustrative line speed cap (km/h). The datasets schedule ~60 km/h (1 min == 1
# km), so a flat-out run to this cap then braking wastes energy vs cruising to
# schedule. Constant, clearly a demo assumption.
VMAX_KMPH = 110.0

# Schematic cruise/coast/brake split of the route distance (display only — the
# energy figure does NOT depend on it; it conveys the profile's shape).
_PHASE_SPLIT = (("cruise", 0.70, "on"), ("coast", 0.22, "off"), ("brake", 0.08, "off"))


def eco_profile(distance_km, scheduled_min, vmax_kmph=VMAX_KMPH):
    """Energy-minimizing cruise-coast-brake profile for one run.

    Returns a dict. `feasible` is False (and `meets_arrival` False) if the
    schedule demands a speed above the line limit — then no profile can both meet
    the time and stay within v_max."""
    if distance_km <= 0 or scheduled_min <= 0:
        return {"applicable": False}

    v_avg = distance_km / (scheduled_min / 60.0)        # km/h needed to arrive on time
    feasible = v_avg <= vmax_kmph + 1e-9
    if not feasible:
        return {
            "applicable": True, "feasible": False, "meets_arrival": False,
            "distance_km": distance_km, "scheduled_min": scheduled_min,
            "cruise_speed_kmph": round(v_avg, 1), "vmax_kmph": vmax_kmph,
            "energy_saved_pct": 0,
            "method": _METHOD,
        }

    phases = [
        {"phase": name, "km": round(frac * distance_km, 2), "power": power,
         "speed_kmph": round(v_avg, 1) if name == "cruise" else None}
        for name, frac, power in _PHASE_SPLIT
    ]
    energy_flatout = vmax_kmph ** 2 * distance_km        # ~ v_max^2 * d
    energy_eco = v_avg ** 2 * distance_km                # ~ v_avg^2 * d
    saved = energy_flatout - energy_eco
    return {
        "applicable": True,
        "feasible": True,
        "meets_arrival": True,                           # holds v_avg over scheduled_min
        "distance_km": distance_km,
        "scheduled_min": scheduled_min,
        "cruise_speed_kmph": round(v_avg, 1),
        "vmax_kmph": vmax_kmph,
        "phases": phases,
        "energy_flatout_units": round(energy_flatout),
        "energy_eco_units": round(energy_eco),
        "energy_saved_units": round(saved),
        "energy_saved_pct": round((1 - (v_avg / vmax_kmph) ** 2) * 100),
        "method": _METHOD,
    }


_METHOD = ("eco-driving (cruise–coast–brake) energy model (simplified ∝v², "
           "illustrative; not a traction simulation)")
