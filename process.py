"""Background job: video -> SAM 3.1 -> shots -> Muse Spark coaching -> annotated video."""
import asyncio, json, os, pathlib, subprocess, threading, time, traceback
from dotenv import load_dotenv; load_dotenv()
import coach as coach_mod
import render as render_mod
import sam_client
import sam_windows
from pipeline import hoop_box_from, all_shots
from shooter import shooter_metrics

JOBS = pathlib.Path("jobs")
STAGES = [("encode", "Preparing your video"),
          ("sam", "Tracking the ball and hoop (SAM 3.1)"),
          ("shots", "Measuring every shot"),
          ("coach", "Writing your coaching (Muse Spark)"),
          ("render", "Rendering the annotated video")]
LABELS = dict(STAGES)


def _save(job):
    d = JOBS / job["id"]
    d.mkdir(parents=True, exist_ok=True)
    tmp = d / "job.json.tmp"
    tmp.write_text(json.dumps(job))
    os.replace(tmp, d / "job.json")


def load_job(jid):
    p = JOBS / jid / "job.json"
    if not p.exists():
        return None
    for _ in range(3):
        try:
            return json.loads(p.read_text())
        except json.JSONDecodeError:
            time.sleep(0.05)
    return None


def _stage(job, key):
    job.update(stage=key, label=LABELS[key], progress=None)
    _save(job)


def _run(cmd):
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode:
        raise RuntimeError(f"{cmd[0]} failed: {r.stderr[-400:]}")
    return r.stdout


def probe(path):
    out = _run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
                "stream=width,height,avg_frame_rate", "-of", "json", str(path)])
    st = json.loads(out)["streams"][0]
    try:
        n, d = st["avg_frame_rate"].split("/")
        fps = float(n) / float(d)
    except (ValueError, ZeroDivisionError):
        fps = 0.0
    if not 5 <= fps <= 121:      # browser recordings (webm) often report no usable fps
        fps = 30.0
    return fps, st["width"], st["height"]


def build_result(shots, report, coaching, fps, hoop_box, video_url, coaching_error=None):
    rows = [dict(i=i + 1, t=round(s["t"], 1), rim_t=round(s["rim_frame"] / fps, 1), made=s["made"],
                 miss_type=s["miss_type"],
                 entry=round(s["entry_angle"]) if s["fit_ok"] else None,
                 apex_in=round(s["apex_above_rim_in"]) if s["fit_ok"] else None,
                 short_in=round(s["short_in"], 1), fit_ok=s["fit_ok"]) for i, s in enumerate(shots)]
    return dict(fps=fps, hoop_box=list(hoop_box), shots=rows,
                report={k: v for k, v in report.items() if k != "per_shot"},
                coaching=coaching, coaching_error=coaching_error, video=video_url)


def analyze_and_coach(jid, balls, hoops, fps, players=None):
    hoop_box = hoop_box_from(hoops) if hoops else None
    if hoop_box is None:
        raise RuntimeError("Couldn't find the hoop. Keep the whole rim in frame at the start of the clip.")
    shots = all_shots(balls, hoop_box, fps)
    if not shots:
        raise RuntimeError("No shots found. Use a fixed side-on camera with the hoop and the full arc in frame.")
    boxes, summ = {}, None
    if players:
        try:
            boxes, per, summ = shooter_metrics(players, shots, hoop_box, fps)
            for s, m in zip(shots, per):
                s["shooter"] = m
        except Exception:
            traceback.print_exc()
            boxes, summ = {}, None
    report = coach_mod.build_report(shots, summ)
    return hoop_box, shots, report, boxes


def shooter_boxes_for(norm, balls, hoops, fps, width):
    """Shooter tracking only on short windows around each shot (fast); never fatal."""
    try:
        hb = hoop_box_from(hoops)
        shots = all_shots(balls, hb, fps)
        if not shots:
            return None
        n = max(b["f"] for b in balls) + 1
        async def go():
            return await sam_windows.track_windows(sam_client.segment, sam_client.make_client(), str(norm),
                                                   shots, fps, n, min(width, 1920))
        recs, _ = asyncio.run(go())
        return recs or None
    except Exception:
        traceback.print_exc()
        return None


def _pipeline(job, src):
    d = JOBS / job["id"]
    fps, w, h = probe(src)
    job["fps"] = fps
    _stage(job, "encode")
    norm, hoopclip = d / "norm.mp4", d / "hoop.mp4"
    _run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(src), "-vf", "scale='min(1920,iw)':-2",
          "-r", f"{fps:.3f}", "-fps_mode", "cfr", "-c:v", "libx264", "-preset", "veryfast", "-crf", "23",
          "-pix_fmt", "yuv420p", "-an", str(norm)])
    _run(["ffmpeg", "-y", "-loglevel", "error", "-t", "6", "-i", str(norm), "-c", "copy", str(hoopclip)])

    _stage(job, "sam")
    async def both():
        c = sam_client.make_client()
        return await asyncio.gather(sam_client.segment(c, str(norm), "basketball"),
                                    sam_client.segment(c, str(hoopclip), "basketball hoop"),
                                    return_exceptions=True)
    balls, hoops = asyncio.run(both())
    for r in (balls, hoops):
        if isinstance(r, Exception):
            raise r
    players = shooter_boxes_for(norm, balls, hoops, fps, w)
    (d / "balls.json").write_text(json.dumps(balls))
    (d / "hoops.json").write_text(json.dumps(hoops))
    if players:
        (d / "players.json").write_text(json.dumps(players))

    _stage(job, "shots")
    hoop_box, shots, report, sboxes = analyze_and_coach(job["id"], balls, hoops, fps, players)

    _stage(job, "coach")
    coaching, cerr = None, None
    try:
        coaching = coach_mod.coach(report)
    except Exception as e:
        cerr = str(e)[:200]

    _stage(job, "render")
    def prog(p):
        job["progress"] = round(p, 2); _save(job)
    render_mod.render(str(norm), str(d / "annotated.mp4"), shots, hoop_box, fps, on_progress=prog,
                      shooter_boxes=sboxes)
    return build_result(shots, report, coaching, fps, hoop_box, f"/api/jobs/{job['id']}/video", cerr)


def start_job(jid, src):
    job = dict(id=jid, status="running", stage="encode", label=LABELS["encode"], progress=None,
               started=time.time(), error=None, result=None)
    _save(job)

    def work():
        try:
            job["result"] = _pipeline(job, src)
            job["status"] = "done"
        except Exception as e:
            traceback.print_exc()
            job.update(status="error", error=str(e)[:400])
        job["finished"] = time.time()
        _save(job)
    threading.Thread(target=work, daemon=True).start()


def start_demo(jid, video, stem="full", hoop_stem="spike"):
    """Same pipeline minus SAM: uses cached boxes so the demo is instant to start."""
    from pipeline import load
    job = dict(id=jid, status="running", stage="shots", label=LABELS["shots"], progress=None,
               started=time.time(), error=None, result=None)
    _save(job)

    def work():
        try:
            d = JOBS / jid
            fps, _, _ = probe(video)
            balls, hoops = load(stem, "basketball"), load(hoop_stem, "basketball_hoop")
            try:
                players = load(stem, "basketball_player")
            except FileNotFoundError:
                players = None
            hoop_box, shots, report, sboxes = analyze_and_coach(jid, balls, hoops, fps, players)
            _stage(job, "coach")
            coaching, cerr = None, None
            try:
                coaching = coach_mod.coach(report)
            except Exception as e:
                cerr = str(e)[:200]
            _stage(job, "render")
            def prog(p):
                job["progress"] = round(p, 2); _save(job)
            render_mod.render(str(video), str(d / "annotated.mp4"), shots, hoop_box, fps, on_progress=prog,
                              shooter_boxes=sboxes)
            job["result"] = build_result(shots, report, coaching, fps, hoop_box, f"/api/jobs/{jid}/video", cerr)
            job["status"] = "done"
        except Exception as e:
            traceback.print_exc()
            job.update(status="error", error=str(e)[:400])
        job["finished"] = time.time()
        _save(job)
    threading.Thread(target=work, daemon=True).start()
