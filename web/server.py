import os
import sys
import uuid
import queue as q_module
import threading

# Allow importing from parent directory (imgsheet/)
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional

from pipeline import run_pipeline, PipelineOptions, PipelineResult

# =========================
# SETUP
# =========================
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
STATIC_DIR = os.path.join(BASE_DIR, "static")
OUTPUTS_DIR = os.path.join(BASE_DIR, "outputs")
os.makedirs(OUTPUTS_DIR, exist_ok=True)

app = FastAPI(title="ImgSheet Web")

# CORS for local dev
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount static files
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

# =========================
# JOB STORE
# =========================
jobs = {}  # job_id -> {queue: Queue, result: PipelineResult|None, error: str|None}


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
    }

    options = PipelineOptions(
        use_claude=body.use_claude,
        export_pdf=body.export_pdf,
        randomize=body.randomize,
        search_engine=body.search_engine,
        send_email_to=body.send_email_to,
    )

    def run():
        try:
            def on_progress(msg: str):
                job_queue.put(msg)

            result = run_pipeline(body.prompts, options, on_progress, output_dir=OUTPUTS_DIR)
            jobs[job_id]["result"] = result
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
                # Timeout — send a keepalive comment and continue
                yield ": keepalive\n\n"
                continue

            if msg == "__done__":
                yield f"event: done\ndata: {job_id}\n\n"
                break
            elif msg.startswith("__error__:"):
                error_msg = msg[len("__error__:"):]
                yield f"event: error\ndata: {error_msg}\n\n"
                break
            else:
                yield f"data: {msg}\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.get("/download/{job_id}")
def download(job_id: str):
    job = jobs.get(job_id)
    if not job or not job["result"]:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="Job not found or not complete")

    file_path = job["result"].output_docx
    filename = os.path.basename(file_path)

    return FileResponse(
        path=file_path,
        filename=filename,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run("server:app", host="0.0.0.0", port=port)
