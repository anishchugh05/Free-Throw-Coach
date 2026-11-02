import re, sys
from pipeline import load, hoop_box_from, all_shots

stem, hoop_stem, logfile = sys.argv[1], sys.argv[2], sys.argv[3]
hoop_box = hoop_box_from(load(hoop_stem, "basketball_hoop"))
shots = all_shots(load(stem, "basketball"), hoop_box)

log = []
for line in open(logfile):
    m = re.search(r"(make|miss)\D+(\d+)[.:](\d+)", line, re.I)
    if m:
        log.append((m.group(1).lower(), int(m.group(2)) * 60 + int(m.group(3))))

used, rows = set(), []
for truth, tl in log:
    cand = [(abs(tl - s["t"] - 0.7), i) for i, s in enumerate(shots)
            if i not in used and -0.5 <= tl - s["t"] <= 3.5]
    if not cand:
        rows.append((tl, truth, None))
        continue
    _, i = min(cand)
    used.add(i)
    rows.append((tl, truth, shots[i]))

found = sum(r[2] is not None for r in rows)
right = 0
print(f"{'log':>6} {'truth':>5}  {'apex':>6} {'offset':>7} {'rel':>4} {'ent':>4}  detected")
for tl, truth, s in rows:
    if s is None:
        print(f"{tl:>5}s {truth:>5}  NOT FOUND")
        continue
    det = "make" if s["made"] else "miss"
    ok = det == truth
    right += ok
    flag = "" if s["fit_ok"] else "  (bad fit)"
    print(f"{tl:>5}s {truth:>5}  {s['t']:5.1f}s {s['rim_offset_in']:+6.1f}in "
          f"{s['release_angle']:4.0f} {s['entry_angle']:4.0f}  {det:4} {'OK' if ok else 'WRONG'}{flag}")
print(f"\nshots found: {found}/{len(log)}  (extra detections: {len(shots) - len(used)})")
print(f"make/miss correct: {right}/{found}")
print(f"bad arc fits: {sum(not s['fit_ok'] for s in shots)}")
