"""Phase D gate — pricing ethics.

(1) Emergency freeze: while an active anomaly disrupts a train (reroute / hold /
    admin delay / reduced speed), that train's fare is HELD at the normal level —
    the incident never surges the passenger's fare.
(2) Load-visibility reframe: pricing is presented as demand/load visibility, not
    revenue surge (and never as ML).

Value-asserting: pins the frozen fare to the nominal-route/-departure fare and
proves it across every disruption type, that undisrupted trains are unaffected,
and that the engine fare estimate is honestly framed.
"""

import data.west_bengal as wb
from app.state import AppState
from engine import pricing


def _nominal_fare(net, train, occ):
    dist = pricing.route_distance(net, train.path)
    return pricing.fare_estimate(dist, occ, train.departure)["fare"]


def test_reroute_freezes_fare_to_nominal_no_surge():
    """WB money-shot: T1 is rerouted by the MYM-BWN closure, but its fare is the
    UNDISRUPTED fare (nominal route + departure), not a reroute-surged one."""
    s = AppState(dataset="wb")                       # default closes MYM-BWN
    assert s.result.actions["T1"].action == "reroute"
    p = s.passenger("T1")
    assert p["fare_frozen"] is True
    assert "no surge" in p["fare_reason"]
    orig = next(t for t in wb.build_trains() if t.id == "T1")
    occ = pricing.synthetic_occupancy("T1")
    assert p["fare"]["fare"] == _nominal_fare(s.network, orig, occ)


def test_admin_delay_does_not_surge_fare():
    """A held/delayed train keeps its pre-incident fare (delay must not change
    what the passenger pays)."""
    s = AppState()                                   # 6-city baseline, no anomaly
    before = s.passenger("T1")["fare"]["fare"]
    s.inject([{"type": "train_delayed", "train": "T1", "minutes": 12}])
    after = s.passenger("T1")
    assert after["fare_frozen"] is True
    assert after["fare"]["fare"] == before           # unchanged by the disruption


def test_reduced_speed_freezes_fare():
    """Reduced speed lengthens T1's run (added delay) without rerouting; the fare
    is still frozen to the normal level."""
    s = AppState()
    before = s.passenger("T1")["fare"]["fare"]
    s.inject([{"type": "reduced_speed", "segment": "SEG-12", "factor": 0.5}])
    after = s.passenger("T1")
    assert after["fare_frozen"] is True
    assert after["fare"]["fare"] == before


def test_undisrupted_train_is_not_frozen_during_unrelated_anomaly():
    """Closing SEG-34 disrupts T1/T2/T5 but not T4; T4 prices normally (frozen
    only protects the actually-disrupted)."""
    s = AppState()
    s.inject([{"type": "track_closed", "segment": "SEG-34"}])
    assert s.result.actions["T4"].action == "unchanged"
    p4 = s.passenger("T4")
    assert p4["fare_frozen"] is False
    assert "not surge pricing" in p4["fare_reason"]   # load-visibility framing


def test_no_anomaly_means_no_freeze():
    s = AppState(dataset="wb")
    s.reset()                                        # clears the default closure
    p = s.passenger("T1")
    assert p["fare_frozen"] is False
    assert p["fare"]["fare"] > 0


def test_pricing_is_framed_as_load_visibility_not_surge():
    """Honesty reframe: the live fare reason talks about load, labels itself
    rule-based and illustrative, and explicitly disclaims surge pricing."""
    s = AppState(dataset="real")                     # no anomaly -> live reason
    reason = s.passenger("T101")["fare_reason"]
    assert "load" in reason.lower()
    assert "rule-based load visibility" in reason
    assert "not surge pricing" in reason
    assert "dynamic pricing" not in reason.lower()
