"""Shooter routine metrics from SAM 'basketball player' boxes (no pose model).

Everything is expressed relative to the shooter's own body height, because the shooter is
usually a different distance from the camera than the hoop, so hoop-scale inches would lie.
"""
import numpy as np


def pick_shooter(person_boxes, anchor_x, tol):
    """frame -> (l, t, r, b): the person box whose centre is nearest anchor_x (merges SAM ids)."""
    best = {}
    for b in person_boxes:
        cx = (b["l"] + b["r"]) / 2
        d = abs(cx - anchor_x)
        if d <= tol and (b["f"] not in best or d < best[b["f"]][0]):
            best[b["f"]] = (d, (b["l"], b["t"], b["r"], b["b"]))
    return {f: v[1] for f, v in best.items()}


def _series(boxes, lo, hi):
    n = hi - lo + 1
    a = np.full((n, 4), np.nan)
    for f in range(lo, hi + 1):
        if f in boxes:
            a[f - lo] = boxes[f]
    return a


def shooter_metrics(person_boxes, shots, hoop_box, fps):
    """Returns (boxes_by_frame, per_shot_list_aligned_with_shots, summary)."""
    if not shots or not person_boxes:
        return {}, [None] * len(shots), None
    hoop_cx = (hoop_box[0] + hoop_box[2]) / 2
    hoop_w = hoop_box[2] - hoop_box[0]
    # where the shooter stands: ball x at the start of each flight
    xs = [s["path"][0][1] for s in shots if s.get("path")]
    if not xs:
        return {}, [None] * len(shots), None
    anchor = float(np.median(xs))
    boxes = pick_shooter(person_boxes, anchor, tol=4 * hoop_w)
    back_is_right = anchor > hoop_cx
    per = []
    for s in shots:
        a = s["apex_frame"]
        lo, hi = max(0, a - int(2.2 * fps)), a + int(0.3 * fps)
        arr = _series(boxes, lo, hi)
        if np.isnan(arr[:, 1]).mean() > 0.4:
            per.append(None); continue
        tops, bots = arr[:, 1], arr[:, 3]
        back = arr[:, 2] if back_is_right else arr[:, 0]
        win = np.arange(len(tops))
        ext_ok = (win >= int(0.9 * fps)) & (win <= int(2.0 * fps))        # window around the lift
        k = int(np.nanargmin(np.where(ext_ok, tops, np.nan)))              # frame of highest reach
        rest = slice(max(0, k - int(1.7 * fps)), max(1, k - int(0.9 * fps)))
        if np.isnan(tops[rest]).all():
            per.append(None); continue
        rest_top = float(np.nanmedian(tops[rest]))
        rest_bot = float(np.nanmedian(bots[rest]))
        h = rest_bot - rest_top
        if h < 2 * hoop_w * 0.5:      # implausibly small box
            per.append(None); continue
        ext = (rest_top - tops[k]) / h
        thr = rest_top - 0.08 * h
        start = next((i for i in range(k, -1, -1) if not np.isnan(tops[i]) and tops[i] >= thr), None)
        tempo = (k - start) / fps if start is not None else None
        stance = float(np.nanmedian(back[rest]))
        per.append(dict(ext_pct=100 * float(ext), tempo_s=None if tempo is None else float(tempo),
                        back_x=float(stance), body_px=float(h)))
    ok = [p for p in per if p]
    if len(ok) < 2:
        return boxes, per, None
    st = lambda key: dict(mean=round(float(np.mean([p[key] for p in ok if p[key] is not None])), 1),
                          std=round(float(np.std([p[key] for p in ok if p[key] is not None])), 1))
    bx = np.array([p["back_x"] for p in ok])
    stance_pct = 100 * (bx - np.median(bx)) / np.median([p["body_px"] for p in ok])
    idx = [i for i, p in enumerate(per) if p]
    gaps = np.diff([shots[i]["apex_frame"] for i in idx]) / fps
    summ = dict(shots_measured=len(ok), reach_pct=st("ext_pct"), tempo_s=st("tempo_s"),
                stance_drift_pct=dict(std=round(float(np.std(stance_pct)), 1),
                                      range=round(float(np.ptp(stance_pct)), 1)),
                between_shots_s=dict(mean=round(float(np.mean(gaps)), 1), std=round(float(np.std(gaps)), 1))
                if len(gaps) else None)
    return boxes, per, summ


VIEW_WARNING = ("This doesn't look like a side-on view, so routine numbers (reach, tempo, stance) are hidden "
                "and arc/rim-offset readings may be off. Make and miss counts are still reliable.")


def sanitize(summ):
    """Drop shooter numbers that are physically implausible. Returns (summary_or_None, warning_or_None)."""
    if not summ:
        return summ, None
    reach = (summ.get("reach_pct") or {}).get("mean")
    tempo = (summ.get("tempo_s") or {}).get("mean")
    if (reach is not None and reach < 5) or (tempo is not None and tempo < 0.1):
        return None, VIEW_WARNING
    sd = summ.get("stance_drift_pct")
    if sd and sd.get("range", 0) > 60:      # a stance can't wander more than ~half a body height
        summ = dict(summ, stance_drift_pct=None)
    return summ, None
