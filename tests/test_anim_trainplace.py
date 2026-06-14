"""JS coverage for the train ANIMATION layer (the audit's key gap).

The reported "pop-in" bug (C1) lived entirely in the browser-side trainPlace/
rakeStyle helpers, which had ZERO test coverage. These gates drive the SHIPPED
functions (extracted from app/static/index.html) over a full timeline via Node
and assert:
  * C1 visibility policy: a train is rendered at every time it has coords (never
    hidden -> never "pops in"); it is moving=true ONLY strictly between departure
    and arrival, parked otherwise; rakeStyle is solid while moving and dim/hollow
    while parked.
  * every station_times hop is between ADJACENT stations (no teleport across a
    straight chord), and time never goes backwards.
  * the interpolated position lies EXACTLY on the current segment.

If Node is unavailable the suite skips these (they are JS gates), but Node ships
with the repo's tooling and CI.
"""

import json
import os
import shutil
import subprocess

import pytest

HERE = os.path.dirname(__file__)
CHECK = os.path.join(HERE, "_trainplace_check.mjs")


@pytest.fixture(scope="module")
def result():
    node = shutil.which("node")
    if node is None:
        pytest.skip("node not available — JS animation gate skipped")
    proc = subprocess.run(
        [node, CHECK], capture_output=True, text=True, timeout=60,
    )
    assert proc.returncode == 0, f"node check crashed:\n{proc.stderr}"
    return json.loads(proc.stdout)


def test_trainplace_helpers_extracted_and_ran(result):
    # proves the anchors still bracket the real functions and they executed
    assert result["summary"]["samples"] > 100
    assert result["ok"], f"animation gate failures: {result['failures']}"


def test_train_is_never_hidden_so_it_cannot_pop_in(result):
    # every sampled time produced a position -> the rake is always drawn
    assert result["summary"]["nulls"] == 0


def test_c1_visibility_policy_moving_only_while_travelling(result):
    s = result["summary"]
    assert s["movingDuring"] > 0 and s["parkedOutside"] > 0
    # rakeStyle: solid only while moving, dim+hollow while parked (the C1 fix)
    assert s["styleSolidWhenMoving"] is True
    assert s["styleHollowWhenParked"] is True


def test_position_lies_exactly_on_the_segment(result):
    # convex blend of the two endpoints -> cross-product is ~0 (here exactly 0)
    assert result["summary"]["onSegmentMaxCross"] < 1e-6


def test_no_pop_in_and_no_teleport_overall(result):
    # composite: zero failures means no hidden frame, no off-segment point, no
    # non-adjacent/backwards hop across the whole driven timeline
    assert result["failures"] == []
