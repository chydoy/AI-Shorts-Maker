import os
import re
import uuid

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, HttpUrl

from database import SessionLocal, ShortFragment, Transcript, VideoTask, init_db
from worker import process_video

app = FastAPI(title="AI Shorts Maker API")

# The browser frontend runs on localhost:3000 while FastAPI runs on localhost:8000.
# Keep the allowed origin configurable for deployment.
FRONTEND_ORIGIN = os.getenv("FRONTEND_ORIGIN", "http://localhost:3000")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[FRONTEND_ORIGIN],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class ProcessRequest(BaseModel):
    youtube_url: HttpUrl


@app.on_event("startup")
def startup_event():
    init_db()


@app.get("/")
def read_root():
    return {"message": "AI Shorts Maker API is running and Database is ready!"}


@app.post("/api/v1/process", status_code=202)
def start_processing(data: ProcessRequest):
    """Create a processing task and enqueue the full Celery pipeline."""
    youtube_url = str(data.youtube_url)

    # Accept the common YouTube URL forms used by the frontend.
    youtube_pattern = re.compile(
        r"^(https?://)?(www\.)?(youtube\.com/(watch\?v=|shorts/|embed/)|youtu\.be/)[^&\s]+"
    )
    if not youtube_pattern.match(youtube_url):
        raise HTTPException(
            status_code=422,
            detail="Поддерживаются только ссылки YouTube.",
        )

    db = SessionLocal()
    try:
        task = VideoTask(
            session_id=str(uuid.uuid4()),
            youtube_url=youtube_url,
            status="pending",
        )
        db.add(task)
        db.commit()
        db.refresh(task)

        celery_task = process_video.delay(task.id, task.youtube_url)

        return {
            "task_id": task.id,
            "celery_task_id": celery_task.id,
            "status": task.status,
        }
    finally:
        db.close()


@app.get("/api/v1/tasks/{task_id}")
def get_task(task_id: int):
    db = SessionLocal()
    try:
        task = db.get(VideoTask, task_id)
        if task is None:
            raise HTTPException(status_code=404, detail="Task not found")

        transcript = (
            db.query(Transcript)
            .filter(Transcript.task_id == task_id)
            .order_by(Transcript.id.desc())
            .first()
        )

        fragments_count = (
            db.query(ShortFragment)
            .filter(ShortFragment.task_id == task_id)
            .count()
        )

        return {
            "id": task.id,
            "status": task.status,
            "youtube_url": task.youtube_url,
            "fragments_count": fragments_count,
            "transcript": {
                "text": transcript.text,
                "language": transcript.language,
                "audio_path": transcript.audio_path,
            }
            if transcript
            else None,
        }
    finally:
        db.close()


@app.get("/api/v1/tasks/{task_id}/fragments")
def get_task_fragments(task_id: int):
    """Return viral short moments and fragments selected by LLM for given task."""
    db = SessionLocal()
    try:
        task = db.get(VideoTask, task_id)
        if task is None:
            raise HTTPException(status_code=404, detail="Task not found")

        fragments = (
            db.query(ShortFragment)
            .filter(ShortFragment.task_id == task_id)
            .order_by(ShortFragment.start_time.asc())
            .all()
        )

        return {
            "task_id": task.id,
            "status": task.status,
            "youtube_url": task.youtube_url,
            "count": len(fragments),
            "fragments": [
                {
                    "id": f.id,
                    "title": f.title,
                    "start_time": f.start_time,
                    "end_time": f.end_time,
                    "duration": f.duration,
                    "reasoning": f.reasoning,
                    "summary": f.summary,
                }
                for f in fragments
            ],
        }
    finally:
        db.close()

