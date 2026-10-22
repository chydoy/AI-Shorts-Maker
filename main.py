import os
import re
import uuid

from pathlib import Path
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel, HttpUrl

from database import SessionLocal, ShortFragment, Transcript, VideoTask, init_db
from worker import process_video, render_fragment_video

app = FastAPI(title="AI Shorts Maker API")

# The browser frontend runs on localhost:3000 while FastAPI runs on localhost:8000.
# Keep the allowed origin configurable for deployment.
FRONTEND_ORIGIN = os.getenv("FRONTEND_ORIGIN", "http://localhost:3000")
allowed_origins = list({FRONTEND_ORIGIN, "http://localhost:3000", "http://127.0.0.1:3000"})
app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class ProcessRequest(BaseModel):
    youtube_url: HttpUrl


class AdjustFragmentRequest(BaseModel):
    adjusted_start_time: float
    adjusted_end_time: float


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
                    "adjusted_start_time": f.adjusted_start_time,
                    "adjusted_end_time": f.adjusted_end_time,
                    "duration": f.duration,
                    "virality_score": f.virality_score,
                    "hook_reason": f.hook_reason,
                    "internal_criticism": f.internal_criticism,
                    "first_words": f.first_words,
                    "last_words": f.last_words,
                    "reasoning": f.reasoning,
                    "summary": f.summary,
                    "video_path": f.video_path,
                    "status": f.status,
                }
                for f in fragments
            ],
        }
    finally:
        db.close()


@app.patch("/api/v1/fragments/{fragment_id}/adjust")
def adjust_fragment_timecodes(fragment_id: int, data: AdjustFragmentRequest):
    """Adjust fragment start/end timecodes in milliseconds/seconds (US 7)."""
    db = SessionLocal()
    try:
        fragment = db.get(ShortFragment, fragment_id)
        if fragment is None:
            raise HTTPException(status_code=404, detail="Fragment not found")

        if data.adjusted_start_time < 0.0:
            raise HTTPException(
                status_code=422,
                detail="Время начала фрагмента не может быть отрицательным",
            )

        if data.adjusted_end_time <= data.adjusted_start_time:
            raise HTTPException(
                status_code=422,
                detail="Конец фрагмента должен быть позже начала",
            )

        duration = data.adjusted_end_time - data.adjusted_start_time
        if duration < 5.0:
            raise HTTPException(
                status_code=422,
                detail="Длительность Shorts должна составлять не менее 5 секунд",
            )

        if duration > 65.0:
            raise HTTPException(
                status_code=422,
                detail="Длительность Shorts не может превышать 60 секунд",
            )

        fragment.adjusted_start_time = round(data.adjusted_start_time, 3)
        fragment.adjusted_end_time = round(data.adjusted_end_time, 3)
        fragment.duration = round(duration, 3)
        fragment.status = "retrim_pending"
        db.commit()
        db.refresh(fragment)
        render_fragment_video.delay( fragment_id=fragment.id, start_sec=fragment.adjusted_start_time, end_sec=fragment.adjusted_end_time,)

        return {
            "id": fragment.id,
            "task_id": fragment.task_id,
            "title": fragment.title,
            "start_time": fragment.start_time,
            "end_time": fragment.end_time,
            "adjusted_start_time": fragment.adjusted_start_time,
            "adjusted_end_time": fragment.adjusted_end_time,
            "duration": fragment.duration,
            "status": fragment.status,
            "message": "Таймкоды успешно скорректированы, отправлено на повторную нарезку",
        }
    finally:
        db.close()


@app.get("/api/v1/fragments/{fragment_id}")
def get_fragment_detail(fragment_id: int):
    """Get single fragment details with full LLM analytics and virality score."""
    db = SessionLocal()
    try:
        fragment = db.get(ShortFragment, fragment_id)
        if fragment is None:
            raise HTTPException(status_code=404, detail="Fragment not found")

        return {
            "id": fragment.id,
            "task_id": fragment.task_id,
            "title": fragment.title,
            "start_time": fragment.start_time,
            "end_time": fragment.end_time,
            "adjusted_start_time": fragment.adjusted_start_time,
            "adjusted_end_time": fragment.adjusted_end_time,
            "duration": fragment.duration,
            "virality_score": fragment.virality_score,
            "hook_reason": fragment.hook_reason,
            "internal_criticism": fragment.internal_criticism,
            "first_words": fragment.first_words,
            "last_words": fragment.last_words,
            "summary": fragment.summary,
            "video_path": fragment.video_path,
            "status": fragment.status,
        }
    finally:
        db.close()

MEDIA_DIR = Path(os.getenv("SHARED_MEDIA_DIR", "/shared/media"))

@app.get("/media/clips/{filename}", tags=["Media Delivery"])
def stream_video_clip(filename: str):
    """Стриминг MP4-видеопотока для вертикального плеера 9:16"""
    file_path = MEDIA_DIR / filename
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="Клип еще рендерится или не найден")
    return FileResponse(path=str(file_path), media_type="video/mp4")


@app.get("/api/v1/fragments/{fragment_id}/download", tags=["Media Delivery"])
def download_fragment(fragment_id: int):
    """Прямое скачивание готового MP4 файла клипа"""
    filename = f"fragment_{fragment_id}.mp4"
    file_path = MEDIA_DIR / filename
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="Файл клипа не найден")
    return FileResponse(
        path=str(file_path),
        media_type="video/mp4",
        filename=f"shorts_{fragment_id}.mp4",
    )