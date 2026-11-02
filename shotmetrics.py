import numpy as np
from scipy.signal import find_peaks

RIM_IN = 18.0

def _fill_gaps(v, max_gap=6):
    v = v.astype(float).copy()
    idx = np.arange(len(v))
    ok = ~np.isnan(v)
    if ok.sum() < 2:
        return v
    filled = np.interp(idx, idx[ok], v[ok])
    n, i = len(v), 0
    while i < n:
        if np.isnan(v[i]):
            j = i
            while j < n and np.isnan(v[j]):
                j += 1
            if (j - i) <= max_gap and i > 0 and j < n:
                v[i:j] = filled[i:j]
            i = j
        else:
            i += 1
    return v

def analyze(x, y, hoop_box, fps, make_tol_in=5.5, center_in=0.0, win_s=0.9, tol_frac=0.10):
    x, y = _fill_gaps(np.asarray(x)), _fill_gaps(np.asarray(y))
    hx1, hy1, hx2, hy2 = hoop_box
    hoop_cx, rim_y = (hx1 + hx2) / 2, hy1
    px_in = (hx2 - hx1) / RIM_IN
    tol = tol_frac * (hx2 - hx1)
    ys = np.where(np.isnan(y), np.nanmax(y), y)
    peaks, _ = find_peaks(-ys, prominence=2.0 * (hx2 - hx1), distance=int(0.8 * fps))
    shots = []
    for a in peaks:
        if y[a] >= rim_y:
            continue
        after = np.where((y[a:] >= rim_y) & ~np.isnan(y[a:]))[0]
        if len(after) == 0:
            continue
        c = a + after[0]
        seg = np.arange(a, c + 1)
        seg = seg[~np.isnan(x[seg])]
        if len(seg) < 4:
            continue
        start, miss = a, 0
        for i in range(a - 1, max(a - int(win_s * fps), 0), -1):
            if np.isnan(y[i]):
                continue
            idx = np.arange(i + 1, c + 1)
            idx = idx[~np.isnan(y[idx])]
            py = np.polyfit((idx - a) / fps, y[idx], 2)
            if abs(np.polyval(py, (i - a) / fps) - y[i]) > tol:
                miss += 1
                if miss >= 2:
                    break
            else:
                miss, start = 0, i
        idx = np.arange(start, c + 1)
        idx = idx[~np.isnan(y[idx])]
        t = (idx - a) / fps
        py, pxf = np.polyfit(t, y[idx], 2), np.polyfit(t, x[idx], 1)
        tr, tc = (start - a) / fps, (c - a) / fps
        vx_r, vy_r = pxf[0], 2 * py[0] * tr + py[1]
        vx_c, vy_c = pxf[0], 2 * py[0] * tc + py[1]
        x_c = x[c] if not np.isnan(x[c]) else np.polyval(pxf, tc)
        side = np.sign(np.polyval(pxf, tr) - hoop_cx) or 1.0
        off = (x_c - hoop_cx) / px_in - center_in
        rel = float(np.degrees(np.arctan2(-vy_r, abs(vx_r))))
        ent = float(np.degrees(np.arctan2(vy_c, abs(vx_c))))
        made = abs(off) <= make_tol_in
        shots.append(dict(
            apex_frame=int(a), release_frame=int(start), rim_frame=int(c),
            release_angle=rel, entry_angle=ent,
            fit_ok=bool(15 <= rel <= 80 and 25 <= ent <= 75),
            apex_above_rim_in=float((rim_y - np.polyval(py, 0)) / px_in),
            release_height_above_rim_in=float((rim_y - np.polyval(py, tr)) / px_in),
            hang_time_s=float(tc - tr),
            rim_offset_in=float(off), short_in=float(off * side), made=bool(made),
            miss_type=None if made else ("short" if off * side > 0 else "long"),
        ))
    return shots, summarize(shots)

def summarize(shots):
    if not shots:
        return {"n": 0}
    ok = [s for s in shots if s["fit_ok"]] or shots
    f = lambda k, src=ok: np.array([s[k] for s in src])
    out = {"n": len(shots), "makes": int(sum(s["made"] for s in shots)),
           "bad_fits": len(shots) - len([s for s in shots if s["fit_ok"]])}
    for k in ("release_angle", "entry_angle", "apex_above_rim_in", "release_height_above_rim_in"):
        out[k] = {"mean": float(f(k).mean()), "std": float(f(k).std())}
    out["short_misses"] = sum(s["miss_type"] == "short" for s in shots)
    out["long_misses"] = sum(s["miss_type"] == "long" for s in shots)
    return out
