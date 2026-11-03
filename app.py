"""uvicorn app:app --port 8000"""
import os, pathlib, re, shutil, uuid
from fastapi import Body, FastAPI, File, HTTPException, UploadFile
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
import coach as coach_mod
import process

app = FastAPI()
ROOT = pathlib.Path(__file__).parent
MAX_MB = 400
DEMO_VIDEO = pathlib.Path(os.environ.get("DEMO_VIDEO", "full.mp4"))


@app.post("/api/upload")
async def upload(file: UploadFile = File(...)):
    jid = uuid.uuid4().hex[:10]
    ext = pathlib.Path(file.filename or "v.mp4").suffix.lower()
    if ext not in {".mp4", ".mov", ".m4v", ".webm", ".mkv", ".avi", ".3gp"}:
        raise HTTPException(400, "Upload a video file (.mp4 or .mov).")
    d = process.JOBS / jid
    d.mkdir(parents=True, exist_ok=True)
    src, size = d / f"upload{ext}", 0
    with open(src, "wb") as f:
        while chunk := await file.read(1 << 20):
            size += len(chunk)
            if size > MAX_MB << 20:
                f.close(); shutil.rmtree(d, ignore_errors=True)
                raise HTTPException(413, f"Max {MAX_MB} MB. Trim the clip to the shots.")
            f.write(chunk)
    process.start_job(jid, src)
    return {"id": jid}


@app.post("/api/demo")
def demo():
    if not DEMO_VIDEO.exists():
        raise HTTPException(404, f"Demo video {DEMO_VIDEO} not found.")
    jid = "demo"
    j = process.load_job(jid)
    if j and j["status"] in ("running", "done") and j.get("sig") == process.code_sig():
        return {"id": jid}
    (process.JOBS / jid).mkdir(parents=True, exist_ok=True)
    process.start_demo(jid, DEMO_VIDEO)
    return {"id": jid}


@app.get("/api/jobs/{jid}")
def job(jid: str):
    if not re.fullmatch(r"[0-9a-f]{10}|demo", jid):
        raise HTTPException(404)
    j = process.load_job(jid)
    if not j:
        raise HTTPException(404, "No such job")
    return j


ASK_LIMIT = 25
_asks = {}


@app.post("/api/jobs/{jid}/ask")
def ask(jid: str, payload: dict = Body(...)):
    if not re.fullmatch(r"[0-9a-f]{10}|demo", jid):
        raise HTTPException(404)
    j = process.load_job(jid)
    if not j or j["status"] != "done" or not j.get("result"):
        raise HTTPException(409, "The session isn't ready yet.")
    q = payload.get("question")
    if not isinstance(q, str) or not q.strip():
        raise HTTPException(400, "Type a question first.")
    if _asks.get(jid, 0) >= ASK_LIMIT:
        raise HTTPException(429, "That's the question limit for this session.")
    _asks[jid] = _asks.get(jid, 0) + 1
    r = j["result"]
    data = dict(shots=r["shots"], report=r["report"], coaching=r.get("coaching"))
    hist = payload.get("history") if isinstance(payload.get("history"), list) else []
    hist = [h for h in hist if isinstance(h, dict)]
    try:
        return {"answer": coach_mod.ask(data, q.strip(), hist)}
    except Exception:
        _asks[jid] -= 1
        raise HTTPException(502, "The coach couldn't answer just now. Try again.")


@app.get("/api/jobs/{jid}/video")
def video(jid: str):
    if not re.fullmatch(r"[0-9a-f]{10}|demo", jid):
        raise HTTPException(404)
    p = process.JOBS / jid / "annotated.mp4"
    if not p.exists():
        raise HTTPException(404)
    return FileResponse(p, media_type="video/mp4")


# Frontend: served last so /api/* wins. Works for both ./css/... and ./static/css/... paths.
app.mount("/static", StaticFiles(directory=ROOT / "static"), name="static-alias")
app.mount("/", StaticFiles(directory=ROOT / "static", html=True), name="site")
