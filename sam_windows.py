"""Shooter tracking, fast: run SAM 'basketball player' only on short windows around each shot,
downscaled, in parallel. Same cache format as sam_run.py.

  python sam_windows.py full.mp4 --ball full --hoop spike [--width 960] [--par 6]
"""
import argparse, asyncio, json, os, pathlib, subprocess, tempfile, time
from dotenv import load_dotenv; load_dotenv()
import numpy as np


def windows(shots, fps, n_frames, pre=2.5, post=0.6, gap=0.5):
    """Merged (start_frame, end_frame) windows covering [apex-pre, apex+post] of each shot."""
    spans = sorted((max(0, int((s["apex_frame"] / fps - pre) * fps)),
                    min(n_frames - 1, int((s["apex_frame"] / fps + post) * fps))) for s in shots)
    out = []
    for a, b in spans:
        if out and a - out[-1][1] <= gap * fps:
            out[-1] = (out[-1][0], max(out[-1][1], b))
        else:
            out.append((a, b))
    return out


def cut(video, start_f, end_f, fps, width, dst):
    n = end_f - start_f + 1
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-ss", f"{start_f / fps:.4f}", "-i", str(video),
                    "-frames:v", str(n), "-vf", f"scale='min({width},iw)':-2", "-r", f"{fps:.3f}",
                    "-c:v", "libx264", "-preset", "veryfast", "-crf", "24", "-pix_fmt", "yuv420p", "-an", str(dst)],
                   check=True)


async def track_windows(segment, client, video, shots, fps, n_frames, orig_w, width=960, par=6, prompt="basketball player"):
    wins = windows(shots, fps, n_frames)
    sem = asyncio.Semaphore(par)
    tmp = pathlib.Path(tempfile.mkdtemp())
    out_w = min(width, orig_w)
    k = orig_w / out_w

    async def one(i, a, b):
        dst = tmp / f"w{i}.mp4"
        await asyncio.to_thread(cut, video, a, b, fps, width, dst)
        async with sem:
            recs = await segment(client, str(dst), prompt)
        return [dict(obj=f"{i}:{r['obj']}", f=r["f"] + a, l=r["l"] * k, t=r["t"] * k, r=r["r"] * k, b=r["b"] * k, c=r["c"])
                for r in recs]

    res = await asyncio.gather(*(one(i, a, b) for i, (a, b) in enumerate(wins)), return_exceptions=True)
    ok = [r for r in res if not isinstance(r, Exception)]
    for r in res:
        if isinstance(r, Exception):
            print("window failed:", r)
    return [b for r in ok for b in r], wins


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("video"); ap.add_argument("--ball"); ap.add_argument("--hoop")
    ap.add_argument("--width", type=int, default=960); ap.add_argument("--par", type=int, default=6)
    a = ap.parse_args()
    import sam_client
    from pipeline import load, hoop_box_from, all_shots, FPS
    stem = a.ball or pathlib.Path(a.video).stem
    hoop = a.hoop or stem
    import cv2
    cap = cv2.VideoCapture(a.video)
    fps = cap.get(cv2.CAP_PROP_FPS) or FPS
    n, w = int(cap.get(cv2.CAP_PROP_FRAME_COUNT)), int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)); cap.release()
    balls = load(stem, "basketball")
    shots = all_shots(balls, hoop_box_from(load(hoop, "basketball_hoop")), fps)
    wins = windows(shots, fps, n)
    print(f"{len(shots)} shots -> {len(wins)} windows, {sum(b - a + 1 for a, b in wins) / fps:.0f}s of video (clip is {n / fps:.0f}s)")
    t0 = time.time()
    recs, _ = asyncio.run(track_windows(sam_client.segment, sam_client.make_client(), a.video, shots, fps, n, w, a.width, a.par))
    out = pathlib.Path(f"cache/{stem}__basketball_player.json")
    out.write_text(json.dumps(recs))
    print(f"done in {time.time() - t0:.0f}s, {len(recs)} boxes -> {out}")
