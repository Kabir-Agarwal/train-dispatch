"""Phase E gate — honesty terminology + factual WB train names (display/docs only).

Value-asserting: the served page and README no longer carry the over-claiming
terms ("predictive maintenance", "dynamic pricing", an "optimal/optimized
schedule" claim), the cumulative-load framing is present, and every WB train now
carries a real West Bengal service name — with NO non-WB train (e.g. the Grand
Trunk Express, which runs Delhi–Chennai) mislabelled onto a WB corridor.
"""

import re
import urllib.request

import data.west_bengal as wb
from app.server import serve_in_thread
from app.state import AppState

ROOT = __import__("os").path.dirname(__import__("os").path.dirname(__file__))


def _page(dataset="wb"):
    server, url = serve_in_thread(AppState(dataset=dataset))
    try:
        with urllib.request.urlopen(url + "/", timeout=5) as r:
            return r.read().decode("utf-8")
    finally:
        server.shutdown()


def test_page_drops_overclaiming_terms_and_uses_cumulative_load_framing():
    html = _page().lower()
    assert "predictive maintenance" not in html
    assert "dynamic pricing" not in html          # reframed in Phase D, kept here
    assert "cumulative-load wear flagging" in html
    # no claim that the schedule is "optimal"/"optimized"
    assert "optimal schedule" not in html and "optimized schedule" not in html


def test_readme_says_greedily_minimizes_not_optimal():
    with open(ROOT + "/README.md", encoding="utf-8") as f:
        readme = f.read().lower()
    assert "greedily minimizes delay" in readme
    assert "delay-minimized schedule" not in readme
    assert "optimal schedule" not in readme


def test_every_wb_train_has_a_real_service_name():
    names = wb.TRAIN_NAMES
    ids = {t.id for t in wb.build_trains()}
    assert set(names) == ids                       # every train named, no extras
    assert all(v.strip() for v in names.values())  # non-empty
    assert len(set(names.values())) == len(names)  # distinct


def test_no_non_wb_train_name_is_used():
    """The Grand Trunk Express (Delhi–Chennai) and other non-WB names must NOT
    appear as WB services."""
    blob = " ".join(wb.TRAIN_NAMES.values()).lower()
    for non_wb in ("grand trunk", "vindhyachal", "narmada", "coromandel",
                   "tamil nadu", "karnataka"):
        assert non_wb not in blob


def test_snapshot_exposes_wb_train_names_and_legend_can_show_them():
    snap = AppState(dataset="wb").snapshot()
    tn = snap["train_names"]
    assert tn.get("T1") == "Saraighat Express"     # Howrah–Guwahati via NJP
    assert tn.get("T2") == "Gour Express"          # Sealdah–Malda Town
    assert len(tn) == 12
    # other datasets simply have no service names (display-only, optional)
    assert AppState(dataset="baseline").snapshot()["train_names"] == {}


def test_grand_trunk_express_stays_only_in_the_real_delhi_nagpur_corridor():
    """It is factually correct THERE (NDLS->NGP is on the Delhi–Chennai route);
    it must not leak into the WB dataset."""
    real_src = open(ROOT + "/data/real_corridor.py", encoding="utf-8").read()
    assert "Grand Trunk Express" in real_src       # accurate source citation kept
    # not used as a WB SERVICE NAME (a doc comment may reference it to note this)
    assert "grand trunk" not in " ".join(wb.TRAIN_NAMES.values()).lower()
