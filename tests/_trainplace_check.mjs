// Headless check of the SHIPPED train animation helpers (trainPlace, rakeStyle).
//
// It extracts the real functions from app/static/index.html (between the
// <<ANIM_FNS_START>>/<<ANIM_FNS_END>> anchors) and drives them over a full
// timeline, asserting the C1 visibility policy, hop-adjacency, and that the
// interpolated position lies EXACTLY on the current segment. Prints a JSON
// summary to stdout; tests/test_anim_trainplace.py consumes it.
//
// Run:  node tests/_trainplace_check.mjs
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";

const here = dirname(fileURLToPath(import.meta.url));
const html = readFileSync(join(here, "..", "app", "static", "index.html"), "utf-8");

const START = "// <<ANIM_FNS_START>>";
const END = "// <<ANIM_FNS_END>>";
const i = html.indexOf(START);
const j = html.indexOf(END);
if (i < 0 || j < 0 || j < i) {
  console.log(JSON.stringify({ ok: false, failures: ["anchors not found in index.html"] }));
  process.exit(0);
}
const src = html.slice(html.indexOf("\n", i) + 1, j);   // from the line AFTER the anchor
const { trainPlace, rakeStyle } = new Function(src + "\nreturn { trainPlace, rakeStyle };")();

// --- fixture: a small network with exact coords so on-segment math is precise.
const coords = { A: [0, 0], B: [100, 0], C: [100, 100], D: [40, 160] };
const adj = new Set(["A|B", "B|A", "B|C", "C|B", "C|D", "D|C"]);
// Three trains: a held one (departs minute 30), an immediate one, a short hop.
const trains = [
  { id: "H", st: [["A", 30], ["B", 50], ["C", 70], ["D", 90]] },   // hold then run
  { id: "I", st: [["A", 0], ["B", 20], ["C", 40]] },                // departs at t=0
  { id: "S", st: [["C", 15], ["D", 35]] },                          // single hop
];

const failures = [];
const fail = (m) => failures.push(m);
const approx = (a, b, eps = 1e-9) => Math.abs(a - b) <= eps;

let samples = 0, nulls = 0, movingDuring = 0, parkedOutside = 0;
let maxCross = 0;

for (const tr of trains) {
  const st = tr.st;
  const dep = st[0][1], arr = st[st.length - 1][1];
  const origin = st[0][0], dest = st[st.length - 1][0];

  // hops must be between adjacent stations and time-monotonic
  for (let k = 0; k < st.length - 1; k++) {
    const a = st[k][0], b = st[k + 1][0];
    if (!adj.has(a + "|" + b)) fail(`${tr.id}: non-adjacent hop ${a}->${b}`);
    if (st[k + 1][1] < st[k][1]) fail(`${tr.id}: time goes backwards ${a}->${b}`);
  }

  for (let t = -5; t <= arr + 25; t += 1) {
    const p = trainPlace(st, t, coords);
    samples++;
    if (!p) { nulls++; fail(`${tr.id}: null/hidden at t=${t} (would 'pop in')`); continue; }

    if (t <= dep) {                       // before/at departure -> parked at origin
      parkedOutside++;
      if (p.moving) fail(`${tr.id}: moving=true before departure at t=${t}`);
      if (!approx(p.pos[0], coords[origin][0]) || !approx(p.pos[1], coords[origin][1]))
        fail(`${tr.id}: not at origin before departure at t=${t}`);
    } else if (t >= arr) {                // after arrival -> parked at destination
      parkedOutside++;
      if (p.moving) fail(`${tr.id}: moving=true after arrival at t=${t}`);
      if (!approx(p.pos[0], coords[dest][0]) || !approx(p.pos[1], coords[dest][1]))
        fail(`${tr.id}: not at destination after arrival at t=${t}`);
    } else {                             // travelling -> on the current segment
      movingDuring++;
      if (!p.moving) fail(`${tr.id}: moving=false while travelling at t=${t}`);
      // find bracketing stations and verify the point is on that segment
      let A2, B2;
      for (let k = 0; k < st.length - 1; k++) {
        if (t >= st[k][1] && t <= st[k + 1][1]) { A2 = st[k][0]; B2 = st[k + 1][0]; break; }
      }
      const ca = coords[A2], cb = coords[B2];
      const ex = cb[0] - ca[0], ey = cb[1] - ca[1];
      const L = Math.hypot(ex, ey) || 1;
      const cross = Math.abs(((p.pos[0] - ca[0]) * ey - (p.pos[1] - ca[1]) * ex) / L);
      if (cross > maxCross) maxCross = cross;
      if (cross > 1e-6) fail(`${tr.id}: off-segment by ${cross} at t=${t}`);
      // and within the segment's bounding box (not past an endpoint)
      const within = p.pos[0] >= Math.min(ca[0], cb[0]) - 1e-6 && p.pos[0] <= Math.max(ca[0], cb[0]) + 1e-6
        && p.pos[1] >= Math.min(ca[1], cb[1]) - 1e-6 && p.pos[1] <= Math.max(ca[1], cb[1]) + 1e-6;
      if (!within) fail(`${tr.id}: position outside segment bbox at t=${t}`);
    }
  }
}

// --- rakeStyle (C1 dim policy): solid only while moving, hollow+faded when parked.
const solid = rakeStyle(true), parked = rakeStyle(false);
const styleSolidWhenMoving = solid.hollow === false && solid.opacity === 1;
const styleHollowWhenParked = parked.hollow === true && parked.opacity < 1;
if (!styleSolidWhenMoving) fail("rakeStyle(true) is not solid/opaque");
if (!styleHollowWhenParked) fail("rakeStyle(false) is not hollow/dimmed");

console.log(JSON.stringify({
  ok: failures.length === 0,
  summary: {
    samples, nulls, movingDuring, parkedOutside,
    onSegmentMaxCross: maxCross,
    styleSolidWhenMoving, styleHollowWhenParked,
  },
  failures: failures.slice(0, 20),
}, null, 1));
