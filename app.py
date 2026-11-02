"""uvicorn app:app --port 8000"""
import os, pathlib, re, shutil, uuid
from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
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
    if j and j["status"] in ("running", "done"):
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
