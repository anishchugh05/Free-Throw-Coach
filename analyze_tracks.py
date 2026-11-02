import json, sys, pathlib
import numpy as np
import matplotlib; matplotlib.use("Agg")
import matplotlib.pyplot as plt
from shotmetrics import analyze

stem = sys.argv[1]
fps = 59.94
load = lambda n, s=None: json.loads(pathlib.Path(f"cache/{s or stem}__{n}.json").read_text())
balls, hoops = load("basketball"), load("basketball_hoop", sys.argv[2] if len(sys.argv) > 2 else None)
nf = max(b["f"] for b in balls) + 1

def track(boxes, obj):
    x = np.full(nf, np.nan); y = np.full(nf, np.nan)
    for b in boxes:
        if b["obj"] == obj and b["f"] < nf:
            x[b["f"]] = (b["l"] + b["r"]) / 2
            y[b["f"]] = (b["t"] + b["b"]) / 2
    return x, y

area = lambda b: (b["r"] - b["l"]) * (b["b"] - b["t"])
hoop_obj = max({b["obj"] for b in hoops},
               key=lambda o: np.mean([area(b) for b in hoops if b["obj"] == o]))
hb = [b for b in hoops if b["obj"] == hoop_obj]
hoop_box = tuple(float(np.median([b[k] for b in hb])) for k in ("l", "t", "r", "b"))
cx = [(b["l"] + b["r"]) / 2 for b in hb]
print(f"hoop obj {hoop_obj}: box {tuple(round(v) for v in hoop_box)}, centre wobble {np.std(cx):.1f}px")

plt.figure(figsize=(12, 4))
for o in sorted({b["obj"] for b in balls}):
    x, y = track(balls, o)
    print(f"\nball obj {o}: height range y {np.nanmin(y):.0f}..{np.nanmax(y):.0f}, "
          f"x range {np.nanmin(x):.0f}..{np.nanmax(x):.0f}")
    shots, summ = analyze(x, y, hoop_box, fps)
    print(f"  shots found: {len(shots)}")
    for s in shots:
        res = "MAKE" if s["made"] else f"miss ({s['miss_type']})"
        print(f"  t={s['apex_frame']/fps:5.1f}s release {s['release_angle']:.0f}deg "
              f"entry {s['entry_angle']:.0f}deg apex {s['apex_above_rim_in']:.0f}in "
              f"offset {s['rim_offset_in']:+.0f}in -> {res}")
    plt.plot(np.arange(nf) / fps, y, label=f"ball obj {o}")
plt.axhline(hoop_box[1], color="red", ls="--", label="rim")
plt.gca().invert_yaxis(); plt.xlabel("seconds"); plt.ylabel("y (px, up = higher)")
plt.legend(); plt.tight_layout(); plt.savefig("plot.png", dpi=110)
print("\nsaved plot.png")
