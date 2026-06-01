import os
import sys
import uuid
import queue as q_module
import threading

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fastapi import FastAPI, HTTPException, UploadFile, File
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional, List
from io import BytesIO
from PIL import Image

from pipeline import run_pipeline, PipelineOptions, create_doc

# =========================
# SETUP
# =========================
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
STATIC_DIR = os.path.join(BASE_DIR, "static")
OUTPUTS_DIR = os.path.join(BASE_DIR, "outputs")
UPLOAD_DIR = os.path.join(BASE_DIR, "uploads")
os.makedirs(OUTPUTS_DIR, exist_ok=True)
os.makedirs(UPLOAD_DIR, exist_ok=True)

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
    use_claude: bool = False
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


@app.post("/generate")
def generate(body: GenerateRequest):
    job_id = str(uuid.uuid4())
    job_queue = q_module.Queue()

    jobs[job_id] = {
        "queue": job_queue,
        "result": None,
        "error": None,
        "options": None,
        "cards": [],
        "pools": {},
        "back_cards": [],
    }

    options = PipelineOptions(
        use_claude=body.use_claude,
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

            result = run_pipeline(body.prompts, options, on_progress, output_dir=OUTPUTS_DIR)
            jobs[job_id]["result"] = result
            _init_card_state(job_id, result, options)
            job_queue.put("__done__")
        except Exception as e:
            jobs[job_id]["error"] = str(e)
            job_queue.put(f"__error__:{e}")

    t = threading.Thread(target=run, daemon=True)
    t.start()

    return {"job_id": job_id}


@app.get("/progress/{job_id}")
def progress(job_id: str):
    if job_id not in jobs:
        def not_found():
            yield "event: error\ndata: Job not found\n\n"
        return StreamingResponse(
            not_found(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    def event_stream():
        job_queue = jobs[job_id]["queue"]
        while True:
            try:
                msg = job_queue.get(timeout=60)
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
    return FileResponse(job["cards"][idx]["path"], media_type="image/jpeg")


@app.get("/back_image/{job_id}/{idx}")
def get_back_image(job_id: str, idx: int):
    job = jobs.get(job_id)
    back = job.get("back_cards", []) if job else []
    if idx < 0 or idx >= len(back):
        raise HTTPException(status_code=404, detail="Image not found")
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
    content = await file.read()
    try:
        img = Image.open(BytesIO(content)).convert("RGB")
        fname = f"upload_{job_id}_{card_idx}_{uuid.uuid4().hex[:6]}.jpg"
        path = os.path.join(UPLOAD_DIR, fname)
        img.save(path, "JPEG", quality=92)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Invalid image: {e}")
    cards = job["cards"]
    entry = {"path": path, "char": "upload", "char_idx": -1}
    if card_idx < len(cards):
        cards[card_idx] = entry
    else:
        cards.append(entry)
    return {"ok": True}


@app.get("/download/{job_id}")
def download(job_id: str):
    job = jobs.get(job_id)
    if not job or not job["result"]:
        raise HTTPException(status_code=404, detail="Job not found or not complete")

    cards = job["cards"]
    opts = job["options"]
    paths = [c["path"] for c in cards]

    missing = [p for p in paths if not os.path.exists(p)]
    if missing:
        raise HTTPException(status_code=410, detail=f"Image files no longer on disk ({len(missing)} missing). Please regenerate the sheet.")

    output_path = job["result"].output_docx

    back_paths = None
    if opts.double_sided and job.get("back_cards"):
        from pipeline import _mirror_rows
        back_paths = _mirror_rows(job["back_cards"], opts.rows, opts.cols)

    try:
        create_doc(paths, output_path, opts.rows, opts.cols, opts.paper_size, back_paths=back_paths)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to build document: {e}")

    filename = os.path.basename(output_path)
    return FileResponse(
        path=output_path,
        filename=filename,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run("server:app", host="0.0.0.0", port=port)
