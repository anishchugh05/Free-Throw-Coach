"""Annotated video: hoop box, ball path, MAKE/MISS call and a running count."""
import os, subprocess
import cv2
import numpy as np

GREEN, RED, YELLOW, WHITE = (90, 200, 80), (80, 80, 235), (60, 210, 245), (255, 255, 255)


def _text(img, txt, org, scale, color, thick=2):
    cv2.putText(img, txt, org, cv2.FONT_HERSHEY_SIMPLEX, scale, (0, 0, 0), thick + 3, cv2.LINE_AA)
    cv2.putText(img, txt, org, cv2.FONT_HERSHEY_SIMPLEX, scale, color, thick, cv2.LINE_AA)


IDEAL = (255, 225, 140)     # light blue (BGR) for the ghost arc


def ideal_arc(s, hb, hoff, sc, entry_deg=45.0, n=40):
    """Ghost arc from this shot's release point to the rim centre, entering at ~45 degrees.
    In 'u' = horizontal distance travelled, y = y0 + m*u + c*u^2 with entry slope tan(entry) at the rim.
    Returns a list of (x, y) pixel points (already scaled), or None if the geometry is unusable."""
    pts = [(f, x, y) for f, x, y in s["path"] if f <= s["release_frame"] + 1]
    if not pts:
        return None
    _, x0, y0 = pts[-1]
    f = min(s["rim_frame"], len(hoff[0]) - 1) if hoff is not None else 0
    ox, oy = (hoff[0][f], hoff[1][f]) if hoff is not None else (0.0, 0.0)
    tx, ty = (hb[0] + hb[2]) / 2 / sc + ox, hb[1] / sc + oy          # hb is scaled; work in original px
    dx, dy = tx - x0, ty - y0
    u1 = abs(dx)
    if u1 < 30:
        return None
    k = np.tan(np.radians(entry_deg))
    c = (k * u1 - dy) / u1 ** 2
    m = -k + 2 * dy / u1
    if c <= 0 or m >= 0:
        return None
    sgn = 1 if dx > 0 else -1
    us = np.linspace(0, u1, n)
    return [((x0 + sgn * u) * sc, (y0 + m * u + c * u * u) * sc) for u in us]


def render(video_in, out_path, shots, hoop_box, fps, max_w=1280, on_progress=None, shooter_boxes=None, hoop_offsets=None):
    cap = cv2.VideoCapture(video_in)
    w0, h0 = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)), int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT)) or 1
    sc = min(1.0, max_w / w0)
    w, h = int(w0 * sc) // 2 * 2, int(h0 * sc) // 2 * 2
    stride = 2 if fps > 40 else 1
    tmp = out_path + ".tmp.mp4"
    vw = cv2.VideoWriter(tmp, cv2.VideoWriter_fourcc(*"mp4v"), fps / stride, (w, h))
    hb = [int(v * sc) for v in hoop_box]
    fs = w / 1280.0
    paths = [[(f, x * sc, y * sc) for f, x, y in s["path"]] for s in shots]
    hold = int(1.4 * fps)
    ghosts = [ideal_arc(s, hb, hoop_offsets, sc) for s in shots]
    i = -1
    while True:
        ok, frame = cap.read()
        if not ok:
            break
        i += 1
        if i % stride:
            continue
        frame = cv2.resize(frame, (w, h), interpolation=cv2.INTER_AREA)
        ox = oy = 0
        if hoop_offsets is not None and i < len(hoop_offsets[0]):
            ox, oy = int(hoop_offsets[0][i] * sc), int(hoop_offsets[1][i] * sc)
        cv2.rectangle(frame, (hb[0] + ox, hb[1] + oy), (hb[2] + ox, hb[3] + oy), WHITE, 1)
        sb = shooter_boxes.get(i) if shooter_boxes else None
        if sb:
            cv2.rectangle(frame, (int(sb[0] * sc), int(sb[1] * sc)), (int(sb[2] * sc), int(sb[3] * sc)),
                          (255, 170, 110), 1, cv2.LINE_AA)
        done = [s for s in shots if s["rim_frame"] <= i]
        for s, pts, gh in zip(shots, paths, ghosts):
            start = s["release_frame"] - int(0.15 * fps)
            if not (start <= i <= s["rim_frame"] + hold):
                continue
            if gh:
                for a in range(0, len(gh) - 1, 2):                         # dashed
                    cv2.line(frame, (int(gh[a][0]), int(gh[a][1])), (int(gh[a + 1][0]), int(gh[a + 1][1])),
                             IDEAL, max(2, int(3 * fs)), cv2.LINE_AA)
                if i < s["rim_frame"]:
                    top = min(gh, key=lambda p: p[1])
                    _text(frame, "ideal arc", (int(top[0]) - int(40 * fs), int(top[1]) - int(12 * fs)),
                          0.6 * fs, IDEAL, max(1, int(2 * fs)))
            seen = np.array([(x, y) for f, x, y in pts if f <= i], dtype=np.int32)
            if len(seen) == 0:
                continue
            after = i >= s["rim_frame"]
            col = (GREEN if s["made"] else RED) if after else YELLOW
            if len(seen) > 1:
                cv2.polylines(frame, [seen.reshape(-1, 1, 2)], False, col, max(2, int(3 * fs)), cv2.LINE_AA)
            cv2.circle(frame, tuple(int(v) for v in seen[-1]), max(4, int(9 * fs)), col, -1, cv2.LINE_AA)
            if after:
                lab = "MAKE" if s["made"] else "MISS " + (s["miss_type"] or "").replace("_", " ")
                _text(frame, lab, (max(8, hb[0] - int(40 * fs)), max(30, hb[1] - int(24 * fs))),
                      1.1 * fs, col, max(2, int(3 * fs)))
        ov = frame.copy()
        cv2.rectangle(ov, (0, 0), (int(250 * fs), int(64 * fs)), (0, 0, 0), -1)
        frame = cv2.addWeighted(ov, 0.55, frame, 0.45, 0)
        _text(frame, f"{sum(s['made'] for s in done)} / {len(done)} made", (int(14 * fs), int(44 * fs)), 1.0 * fs, WHITE)
        vw.write(frame)
        if on_progress and i % 120 == 0:
            on_progress(min(0.99, i / total))
    cap.release()
    vw.release()
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", tmp, "-c:v", "libx264", "-preset", "veryfast",
                    "-crf", "24", "-pix_fmt", "yuv420p", "-movflags", "+faststart", out_path], check=True)
    os.remove(tmp)
    if on_progress:
        on_progress(1.0)
