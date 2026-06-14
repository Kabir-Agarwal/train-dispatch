"""Phase F gate — system-boundaries honesty (doc + UI section).

Value-asserting: SYSTEM_BOUNDARIES.md exists and covers all SIX deliberate
simplifications, each framed with what production would require; and the served
page carries a matching, honest "system boundaries" section that points at the
doc. Display/docs only — no engine behaviour involved.
"""

import os
import urllib.request

from app.server import serve_in_thread
from app.state import AppState

ROOT = os.path.dirname(os.path.dirname(__file__))
DOC = os.path.join(ROOT, "SYSTEM_BOUNDARIES.md")

# (label, substrings that must all appear) — one tuple per deliberate boundary.
BOUNDARIES = [
    ("segment exclusivity vs signalling", ("segment exclusiv", "moving-block", "fixed-block")),
    ("single vs double track", ("single-track", "double")),
    ("no crew / rake scheduling", ("crew", "rake")),
    ("deterministic not stochastic", ("deterministic", "stochastic")),
    ("regional not national scale", ("national", "50")),
    ("passenger re-accommodation (now basic)", ("passenger re-accommodation", "reroute")),
]


def test_doc_exists_and_covers_all_six_boundaries():
    assert os.path.exists(DOC), "SYSTEM_BOUNDARIES.md missing"
    text = open(DOC, encoding="utf-8").read().lower()
    for label, needles in BOUNDARIES:
        for n in needles:
            assert n.lower() in text, f"{label}: missing '{n}' in SYSTEM_BOUNDARIES.md"


def test_each_boundary_says_what_production_would_require():
    """Honest framing: every boundary is paired with a production requirement, so
    nothing reads as a hidden gap."""
    text = open(DOC, encoding="utf-8").read().lower()
    assert text.count("production would require") >= len(BOUNDARIES)  # one per boundary


def test_page_has_only_a_small_pointer_to_the_boundaries_doc():
    """The long boundaries text block was moved out of the page; only a small
    collapsed 'System boundaries ->' pointer to SYSTEM_BOUNDARIES.md remains.
    The full text lives in the doc (asserted by the doc tests above, unchanged)."""
    server, url = serve_in_thread(AppState(dataset="wb"))
    try:
        with urllib.request.urlopen(url + "/", timeout=5) as r:
            html = r.read().decode("utf-8")
    finally:
        server.shutdown()
    # the small pointer is present
    assert 'id="system-boundaries"' in html
    assert "System boundaries" in html
    assert "SYSTEM_BOUNDARIES.md" in html
    # the long on-page block is gone (these lived only in the removed block)
    for gone in ("Segment exclusivity", "Single-track assumption",
                 "Deterministic, not stochastic", "Regional scale (~50",
                 "Passenger re-accommodation is basic"):
        assert gone not in html, f"boundaries block not removed: {gone}"
