"""Glue: SAM box records -> per-ball tracks -> shots (merged across SAM object ids)."""
import json, os, pathlib
import numpy as np
from shotmetrics import analyze

FPS = 59.94
# Calibrated on the coach clip: where a dead-centre swish crosses vs the SAM hoop-box centre.
CENTER_IN = float(os.environ.get("CENTER_IN", 0.0))


def load(stem, name):
    return json.loads(pathlib.Path(f"cache/{stem}__{name}.json").read_text())


def hoop_box_from(boxes):
    area = lambda b: (b["r"] - b["l"]) * (b["b"] - b["t"])
    objs = {b["obj"] for b in boxes}
    best = max(objs, key=lambda o: np.mean([area(b) for b in boxes if b["obj"] == o]))
    hb = [b for b in boxes if b["obj"] == best]
    return tuple(float(np.median([b[k] for b in hb])) for k in ("l", "t", "r", "b"))


def tracks(boxes):
    nf = max(b["f"] for b in boxes) + 1
    out = {}
    for b in boxes:
        x, y = out.setdefault(b["obj"], (np.full(nf, np.nan), np.full(nf, np.nan)))
        x[b["f"]] = (b["l"] + b["r"]) / 2
        y[b["f"]] = (b["t"] + b["b"]) / 2
    return out


def all_shots(ball_boxes, hoop_box, fps=FPS, **kw):
    shots = []
    for obj, (x, y) in tracks(ball_boxes).items():
        if np.sum(~np.isnan(y)) < 30:
            continue
        ss, _ = analyze(x, y, hoop_box, fps, center_in=CENTER_IN, **kw)
        for s in ss:
            s["obj"], s["t"] = obj, s["apex_frame"] / fps
            lo = max(0, s["release_frame"] - int(0.15 * fps))
            hi = min(len(x) - 1, s["rim_frame"] + int(0.7 * fps))
            s["path"] = [[int(f), round(float(x[f]), 1), round(float(y[f]), 1)]
                         for f in range(lo, hi + 1) if not np.isnan(x[f])]
            shots.append(s)
    shots.sort(key=lambda s: s["t"])
    out = []
    for s in shots:                       # drop duplicates (two tracks on one ball)
        if out and s["t"] - out[-1]["t"] < 1.5:
            continue
        out.append(s)
    return out
