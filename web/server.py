import os
import sys
import uuid
import time
import shutil
import queue as q_module
import threading
import requests

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fastapi import FastAPI, HTTPException, UploadFile, File
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional, List
from io import BytesIO
from PIL import Image

from pipeline import (
    run_pipeline,
    PipelineOptions,
    create_doc,
    TEMP_DIR,
    DOWNLOAD_WORKERS,
    MAX_DOWNLOAD_BYTES,
    MAX_SOURCE_PIXELS,
    PROCESSING_MAX_SIZE,
)

# =========================
# SETUP
# =========================
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
STATIC_DIR = os.path.join(BASE_DIR, "static")
OUTPUTS_DIR = os.path.join(BASE_DIR, "outputs")
UPLOAD_DIR = os.path.join(BASE_DIR, "uploads")
os.makedirs(OUTPUTS_DIR, exist_ok=True)
os.makedirs(UPLOAD_DIR, exist_ok=True)

JOB_TTL = 3600  # seconds before a job's files and record are evicted
SERPAPI_USAGE_CACHE_TTL = 15
serpapi_usage_cache = {"expires_at": 0.0, "payload": None}
serpapi_usage_lock = threading.Lock()
job_execution_lock = threading.Lock()
PROCESS_STARTED_AT = time.time()


def _current_memory_mb():
    """Return current Linux RSS when available (Render), otherwise None."""
    try:
        with open("/proc/self/status", encoding="utf-8") as status_file:
            for line in status_file:
                if line.startswith("VmRSS:"):
                    return round(int(line.split()[1]) / 1024, 1)
    except (OSError, ValueError, IndexError):
        pass
    return None


print(
    f"ImgSheet process started pid={os.getpid()} "
    f"search_workers={os.environ.get('IMGSHEET_SEARCH_WORKERS', '2')} "
    f"download_workers={DOWNLOAD_WORKERS} "
    f"max_source_pixels={MAX_SOURCE_PIXELS}",
    flush=True,
)


def _evict_old_jobs():
    cutoff = time.time() - JOB_TTL
    expired = [jid for jid, j in jobs.items() if j.get("created_at", 0) < cutoff]
    for jid in expired:
        job = jobs.pop(jid)
        result = job.get("result")
        if result and result.output_docx:
            try:
                os.remove(result.output_docx)
            except Exception:
                pass
        td = job.get("temp_dir")
        if td and os.path.isdir(td):
            try:
                shutil.rmtree(td)
            except Exception:
                pass

app = FastAPI(title="ImgSheet Web")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

# =========================
# JOB STORE
# =========================
# job_id -> {queue, result, error, options, cards, pools}
# cards: [{"path": str, "char": str, "char_idx": int}, ...]
# pools: {char_idx: [path, ...]}  remaining unused candidates
jobs = {}


def _init_card_state(job_id, result, options):
    cards = []
    pools = {}
    for i, cr in enumerate(result.characters):
        used = set(cr.image_paths)
        pools[i] = [p for p in cr.candidate_paths if p not in used]
        for path in cr.image_paths:
            cards.append({"path": path, "char": cr.prompt, "char_idx": i})
    jobs[job_id]["cards"] = cards
    jobs[job_id]["pools"] = pools
    jobs[job_id]["options"] = options
    jobs[job_id]["back_cards"] = result.back_image_paths


# =========================
# REQUEST MODELS
# =========================
class GenerateRequest(BaseModel):
    prompts: list[str]
    export_pdf: bool = False
    randomize: bool = False
    search_engine: str = "serpapi"
    send_email_to: str = ""
    rows: int = 5
    cols: int = 5
    paper_size: str = "B4"
    double_sided: bool = False


class ReorderBody(BaseModel):
    order: List[int]


# =========================
# ROUTES
# =========================
@app.get("/")
def index():
    return FileResponse(os.path.join(STATIC_DIR, "index.html"))


@app.api_route("/health", methods=["GET", "HEAD"])
def health():
    return {
        "status": "ok",
        "pid": os.getpid(),
        "uptime_seconds": round(time.time() - PROCESS_STARTED_AT),
        "active_jobs": sum(
            1 for job in list(jobs.values()) if job.get("status") == "running"
        ),
        "memory_mb": _current_memory_mb(),
        "download_workers": DOWNLOAD_WORKERS,
        "max_source_pixels": MAX_SOURCE_PIXELS,
    }


@app.get("/usage/serpapi")
def serpapi_usage():
    """Return quota totals without exposing the SerpApi key or account details."""
    api_key = os.environ.get("SERPAPI_KEY", "").strip()
    if not api_key:
        return {"configured": False, "available": False}

    now = time.time()
    with serpapi_usage_lock:
        cached = serpapi_usage_cache["payload"]
        if cached is not None and serpapi_usage_cache["expires_at"] > now:
            return cached

    try:
        response = requests.get(
            "https://serpapi.com/account.json",
            params={"api_key": api_key},
            timeout=10,
        )
        response.raise_for_status()
        account = response.json()
        if account.get("error"):
            raise ValueError("SerpApi returned an account error")

        monthly_limit = account.get("searches_per_month")
        remaining = account.get("total_searches_left")
        if remaining is None:
            remaining = account.get("plan_searches_left")
        used = account.get("this_month_usage")
        if used is None and monthly_limit is not None and remaining is not None:
            used = max(0, monthly_limit - remaining)

        payload = {
            "configured": True,
            "available": True,
            "monthly_limit": monthly_limit,
            "remaining": remaining,
            "used": used,
            "renewal_date": account.get("plan_renewal_date"),
        }
    except (requests.RequestException, ValueError, TypeError):
        payload = {"configured": True, "available": False}

    with serpapi_usage_lock:
        serpapi_usage_cache["payload"] = payload
        serpapi_usage_cache["expires_at"] = now + SERPAPI_USAGE_CACHE_TTL
    return payload


@app.post("/generate")
def generate(body: GenerateRequest):
    _evict_old_jobs()

    if not job_execution_lock.acquire(blocking=False):
        raise HTTPException(
            status_code=429,
            detail="Another sheet is already generating. Please wait for it to finish.",
        )

    job_id = str(uuid.uuid4())
    job_queue = q_module.Queue()
    job_temp_dir = os.path.join(TEMP_DIR, job_id)

    jobs[job_id] = {
        "queue": job_queue,
        "result": None,
        "error": None,
        "status": "running",
        "options": None,
        "cards": [],
        "pools": {},
        "back_cards": [],
        "created_at": time.time(),
        "temp_dir": job_temp_dir,
    }

    options = PipelineOptions(
        export_pdf=body.export_pdf,
        randomize=body.randomize,
        search_engine=body.search_engine,
        send_email_to=body.send_email_to,
        rows=body.rows,
        cols=body.cols,
        paper_size=body.paper_size,
        double_sided=body.double_sided,
    )

    def run():
        try:
            def on_progress(msg: str):
                job_queue.put(msg)
                print(
                    f"job={job_id} status={msg} memory_mb={_current_memory_mb()}",
                    flush=True,
                )

            result = run_pipeline(body.prompts, options, on_progress, output_dir=OUTPUTS_DIR, temp_dir=job_temp_dir)
            jobs[job_id]["result"] = result
            _init_card_state(job_id, result, options)
            jobs[job_id]["status"] = "done"
            job_queue.put("__done__")
        except Exception as e:
            import traceback
            msg = f"{type(e).__name__}: {e}" if str(e) else type(e).__name__
            traceback.print_exc()
            jobs[job_id]["error"] = msg
            jobs[job_id]["status"] = "error"
            job_queue.put(f"__error__:{msg}")
        finally:
            job_execution_lock.release()

    try:
        t = threading.Thread(target=run, daemon=True)
        t.start()
    except Exception:
        job_execution_lock.release()
        jobs.pop(job_id, None)
        raise

    return {"job_id": job_id}


@app.get("/progress/{job_id}")
def progress(job_id: str):
    if job_id not in jobs:
        def not_found():
            yield "event: error\ndata: The server restarted during generation. Please try again.\n\n"
        return StreamingResponse(
            not_found(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    def event_stream():
        job = jobs[job_id]
        # The client may (re)connect after the job already finished — e.g. the SSE
        # connection dropped near completion and EventSource auto-reconnected.
        # Replay the terminal event instead of blocking forever on a queue that
        # already emitted it (which looked like "nothing was generated").
        if job.get("status") == "done":
            yield f"event: done\ndata: {job_id}\n\n"
            return
        if job.get("status") == "error":
            yield f"event: error\ndata: {job.get('error') or 'Unknown error'}\n\n"
            return
        job_queue = job["queue"]
        while True:
            try:
                msg = job_queue.get(timeout=20)
            except q_module.Empty:
                yield ": keepalive\n\n"
                continue

            if msg == "__done__":
                yield f"event: done\ndata: {job_id}\n\n"
                break
            elif msg.startswith("__error__:"):
                yield f"event: error\ndata: {msg[len('__error__:'):]}\n\n"
                break
            else:
                yield f"data: {msg}\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.get("/images/{job_id}")
def list_images(job_id: str):
    job = jobs.get(job_id)
    if not job or not job["result"]:
        raise HTTPException(status_code=404, detail="Job not found")
    return {"count": len(job["cards"]), "back_count": len(job.get("back_cards", []))}


@app.get("/image/{job_id}/{idx}")
def get_image(job_id: str, idx: int):
    job = jobs.get(job_id)
    if not job or not job["cards"]:
        raise HTTPException(status_code=404, detail="Job not found")
    if idx < 0 or idx >= len(job["cards"]):
        raise HTTPException(status_code=404, detail="Image not found")
    path = job["cards"][idx]["path"]
    if not os.path.exists(path):
        raise HTTPException(status_code=410, detail="Image file no longer on disk. Please regenerate.")
    return FileResponse(path, media_type="image/jpeg")


@app.get("/back_image/{job_id}/{idx}")
def get_back_image(job_id: str, idx: int):
    job = jobs.get(job_id)
    back = job.get("back_cards", []) if job else []
    if idx < 0 or idx >= len(back):
        raise HTTPException(status_code=404, detail="Image not found")
    if not os.path.exists(back[idx]):
        raise HTTPException(status_code=410, detail="Image file no longer on disk. Please regenerate.")
    return FileResponse(back[idx], media_type="image/jpeg")


@app.post("/swap/{job_id}/{card_idx}")
def swap_card(job_id: str, card_idx: int):
    job = jobs.get(job_id)
    if not job or not job["result"]:
        raise HTTPException(status_code=404, detail="Job not found")
    cards = job["cards"]
    if card_idx < 0 or card_idx >= len(cards):
        raise HTTPException(status_code=404, detail="Card not found")
    char_idx = cards[card_idx]["char_idx"]
    pool = job["pools"].get(char_idx, [])
    if not pool:
        raise HTTPException(status_code=400, detail="No more candidates for this card")
    old_path = cards[card_idx]["path"]
    new_path = pool.pop(0)
    pool.append(old_path)  # cycle old back to end
    job["pools"][char_idx] = pool
    cards[card_idx]["path"] = new_path
    return {"ok": True}


@app.delete("/card/{job_id}/{card_idx}")
def remove_card(job_id: str, card_idx: int):
    job = jobs.get(job_id)
    if not job or not job["result"]:
        raise HTTPException(status_code=404, detail="Job not found")
    cards = job["cards"]
    if card_idx < 0 or card_idx >= len(cards):
        raise HTTPException(status_code=404, detail="Card not found")
    removed = cards.pop(card_idx)
    # Return removed image to pool so it can be swapped back in
    char_idx = removed["char_idx"]
    if char_idx >= 0:
        job["pools"].setdefault(char_idx, []).insert(0, removed["path"])
    return {"count": len(cards)}


@app.post("/reorder/{job_id}")
def reorder_cards(job_id: str, body: ReorderBody):
    job = jobs.get(job_id)
    if not job or not job["result"]:
        raise HTTPException(status_code=404, detail="Job not found")
    cards = job["cards"]
    if len(body.order) != len(cards):
        raise HTTPException(status_code=400, detail="Order length mismatch")
    job["cards"] = [cards[i] for i in body.order]
    return {"ok": True}


@app.post("/upload/{job_id}/{card_idx}")
async def upload_card(job_id: str, card_idx: int, file: UploadFile = File(...)):
    job = jobs.get(job_id)
    if not job or not job["result"]:
        raise HTTPException(status_code=404, detail="Job not found")
    content = await file.read(MAX_DOWNLOAD_BYTES + 1)
    if len(content) > MAX_DOWNLOAD_BYTES:
        max_mb = MAX_DOWNLOAD_BYTES // (1024 * 1024)
        raise HTTPException(status_code=413, detail=f"Image file is too large ({max_mb} MB maximum)")
    img = None
    try:
        with Image.open(BytesIO(content)) as raw:
            width, height = raw.size
            if width * height > MAX_SOURCE_PIXELS:
                raise ValueError(
                    f"Image dimensions are too large ({width}x{height}); "
                    f"{MAX_SOURCE_PIXELS / 1_000_000:g} megapixels maximum"
                )
            raw.draft("RGB", PROCESSING_MAX_SIZE)
            raw.thumbnail(PROCESSING_MAX_SIZE, Image.Resampling.LANCZOS)
            img = raw.convert("RGB")
        fname = f"upload_{job_id}_{card_idx}_{uuid.uuid4().hex[:6]}.jpg"
        path = os.path.join(UPLOAD_DIR, fname)
        img.save(path, "JPEG", quality=92)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Invalid image: {e}")
    finally:
        if img is not None:
            img.close()
    cards = job["cards"]
    entry = {"path": path, "char": "upload", "char_idx": -1}
    if card_idx < len(cards):
        cards[card_idx] = entry
    else:
        cards.append(entry)
    return {"ok": True}


@app.get("/download/{job_id}")
def download(job_id: str):
    import traceback
    try:
        job = jobs.get(job_id)
        if not job or not job["result"]:
            raise HTTPException(status_code=404, detail="Job not found or not complete")

        cards = job["cards"]
        opts = job["options"]
        paths = [c["path"] for c in cards]

        missing = [p for p in paths if not os.path.exists(p)]
        if missing:
            raise HTTPException(status_code=410, detail=f"Image files no longer on disk ({len(missing)} missing). Please regenerate.")

        output_path = job["result"].output_docx
        os.makedirs(os.path.dirname(output_path), exist_ok=True)

        back_paths = None
        if opts.double_sided and job.get("back_cards"):
            from pipeline import _mirror_rows
            back_paths = _mirror_rows(job["back_cards"], opts.rows, opts.cols)

        create_doc(paths, output_path, opts.rows, opts.cols, opts.paper_size, back_paths=back_paths)

        filename = os.path.basename(output_path)
        return FileResponse(
            path=output_path,
            media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )
    except HTTPException:
        raise
    except Exception:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail="Failed to build the document. Please try regenerating.")


if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run("server:app", host="0.0.0.0", port=port)
