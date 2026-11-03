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


def hoop_track_from(records):
    """Per-window hoop boxes (SAM ids are prefixed 'window:obj') -> (frames, cx, top, ref_box).

    In each window the largest-area object is the real hoop. Boxes are median-smoothed in time.
    """
    from scipy.signal import medfilt
    area = lambda b: (b["r"] - b["l"]) * (b["b"] - b["t"])
    wins = {}
    for b in records:
        w, _, o = str(b["obj"]).rpartition(":")
        wins.setdefault(w, {}).setdefault(o, []).append(b)
    frames, boxes = [], []
    for w, objs in wins.items():
        best = max(objs.values(), key=lambda v: np.mean([area(b) for b in v]))
        best = sorted(best, key=lambda b: b["f"])
        arr = np.array([[b["l"], b["t"], b["r"], b["b"]] for b in best])
        k = 9 if len(arr) >= 9 else (len(arr) // 2) * 2 + 1
        sm = np.column_stack([medfilt(arr[:, i], k) for i in range(4)]) if k > 1 else arr
        frames += [b["f"] for b in best]
        boxes += list(sm)
    order = np.argsort(frames)
    frames, boxes = np.array(frames)[order], np.array(boxes)[order]
    ref = tuple(float(np.median(boxes[:, i])) for i in range(4))
    return frames, (boxes[:, 0] + boxes[:, 2]) / 2, boxes[:, 1], ref


def hoop_offsets(track, nf):
    """Per-frame (dx, dy) of the hoop vs its median position, interpolated between windows."""
    frames, cx, top, ref = track
    fr = np.arange(nf)
    dx = np.interp(fr, frames, cx) - (ref[0] + ref[2]) / 2
    dy = np.interp(fr, frames, top) - ref[1]
    return dx, dy


def all_shots(ball_boxes, hoop_box, fps=FPS, hoop_track=None, **kw):
    """hoop_track (from hoop_track_from) makes this robust to a moving camera: the ball is measured
    relative to the hoop on every frame, so camera pans and bumps cancel out."""
    shots = []
    for obj, (x, y) in tracks(ball_boxes).items():
        if np.sum(~np.isnan(y)) < 30:
            continue
        x_raw, y_raw = x, y
        if hoop_track is not None:
            hb_ref = hoop_track[3]
            dx, dy = hoop_offsets(hoop_track, len(x))
            x, y = x - dx, y - dy
            hoop_box = hb_ref
        ss, _ = analyze(x, y, hoop_box, fps, center_in=CENTER_IN, **kw)
        x, y = x_raw, y_raw
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
