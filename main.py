import os
import re
import uuid

from pathlib import Path
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel, HttpUrl

from database import SessionLocal, ShortFragment, Transcript, VideoTask, init_db
from media import SHARED_MEDIA_DIR, cut_vertical_clip, source_video_for_task
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


MEDIA_DIR = SHARED_MEDIA_DIR

STEP_LABELS = {
    "pending": "Задача ожидает в очереди",
    "downloading": "Загрузка видео",
    "transcribing": "Распознавание речи",
    "analyzing": "Поиск моментов и скоринг",
    "cutting": "Нарезка клипов (9:16)",
    "completed": "Обработка успешно завершена",
    "error": "Ошибка обработки видео",
}


def _format_time(seconds: float) -> str:
    """Форматирование секунд в формат MM:SS для читаемости таймкодов."""
    total = max(0, int(seconds))
    mins = total // 60
    secs = total % 60
    return f"{mins:02d}:{secs:02d}"


def _build_youtube_preview_url(source_url: str | None, start_time: float) -> str | None:
    """Генерация ссылки предпросмотра YouTube на нужном таймкоде с поддержкой shorts и youtu.be."""
    if not source_url:
        return None
    try:
        t_sec = int(max(0, start_time))
        # youtu.be/<id>
        m_short = re.search(r"youtu\.be/([a-zA-Z0-9_-]+)", source_url)
        if m_short:
            return f"https://www.youtube.com/watch?v={m_short.group(1)}&t={t_sec}s"
        # youtube.com/shorts/<id>
        m_shorts = re.search(r"youtube\.com/shorts/([a-zA-Z0-9_-]+)", source_url)
        if m_shorts:
            return f"https://www.youtube.com/watch?v={m_shorts.group(1)}&t={t_sec}s"
        # youtube.com/watch?v=<id>
        m_watch = re.search(r"[?&]v=([a-zA-Z0-9_-]+)", source_url)
        if m_watch:
            return f"https://www.youtube.com/watch?v={m_watch.group(1)}&t={t_sec}s"
        # Запасной вариант для нестандартных ссылок
        sep = "&" if "?" in source_url else "?"
        return f"{source_url}{sep}t={t_sec}s"
    except Exception:
        return source_url


def _get_stage_info(task: VideoTask) -> tuple[int, str, str, list[dict]]:
    """Расчет прогресса выполнения (0–100%), текущего шага и детализации каждого этапа."""
    status = task.status
    current_step = getattr(task, "current_step", None) or status

    progress = getattr(task, "progress", 0) or 0
    if progress == 0:
        if status == "completed":
            progress = 100
        elif status == "cutting":
            progress = 85
        elif status == "analyzing":
            progress = 65
        elif status == "transcribing":
            progress = 40
        elif status == "downloading":
            progress = 15
        elif status == "pending":
            progress = 5
        elif status == "error":
            progress = 0

    stage_order = ["downloading", "transcribing", "analyzing", "cutting"]
    stage_titles = {
        "downloading": "Загрузка видео",
        "transcribing": "Распознавание речи",
        "analyzing": "Поиск моментов",
        "cutting": "Нарезка клипов",
    }

    try:
        active_idx = stage_order.index(current_step)
    except ValueError:
        if status == "completed":
            active_idx = len(stage_order)
        elif status == "error":
            if progress >= 80:
                active_idx = 3
            elif progress >= 60:
                active_idx = 2
            elif progress >= 35:
                active_idx = 1
            else:
                active_idx = 0
        else:
            active_idx = -1

    stages = []
    for idx, stage_key in enumerate(stage_order):
        if status == "completed":
            s_status = "completed"
        elif status == "error":
            if idx < active_idx:
                s_status = "completed"
            elif idx == active_idx:
                s_status = "failed"
            else:
                s_status = "pending"
        else:
            if idx < active_idx:
                s_status = "completed"
            elif idx == active_idx:
                s_status = "in_progress"
            else:
                s_status = "pending"

        stages.append({
            "key": stage_key,
            "title": stage_titles[stage_key],
            "status": s_status,
        })

    if status == "error":
        if current_step in stage_titles:
            step_label = f"Сбой на этапе: {stage_titles[current_step]}"
        else:
            step_label = STEP_LABELS.get("error", "Ошибка обработки видео")
    else:
        step_label = STEP_LABELS.get(current_step, current_step)

    return progress, current_step, step_label, stages


def _serialize_fragment_dto(fragment: ShortFragment, youtube_url: str | None = None) -> dict:
    """Формирование полного контракта DTO карточки клипа для интерфейса Олега."""
    eff_start = fragment.adjusted_start_time if fragment.adjusted_start_time is not None else fragment.start_time
    eff_end = fragment.adjusted_end_time if fragment.adjusted_end_time is not None else fragment.end_time
    duration = fragment.duration if fragment.duration is not None else max(0.0, eff_end - eff_start)

    formatted_timecode = f"{_format_time(eff_start)}\u2013{_format_time(eff_end)}"

    clip_filename = f"fragment_{fragment.id}.mp4"
    clip_path = MEDIA_DIR / clip_filename
    has_video = (clip_path.exists() and clip_path.stat().st_size > 0) or (fragment.video_path is not None and fragment.status == "ready")

    preview_url = _build_youtube_preview_url(youtube_url, eff_start)

    return {
        "id": fragment.id,
        "task_id": fragment.task_id,
        "title": fragment.title,
        "start_time": fragment.start_time,
        "end_time": fragment.end_time,
        "adjusted_start_time": fragment.adjusted_start_time,
        "adjusted_end_time": fragment.adjusted_end_time,
        "effective_start_time": round(eff_start, 3),
        "effective_end_time": round(eff_end, 3),
        "duration": round(duration, 3),
        "formatted_timecode": formatted_timecode,
        "virality_score": fragment.virality_score if fragment.virality_score is not None else 0,
        "hook_score": getattr(fragment, "hook_score", None) or round((fragment.virality_score or 0) * 0.30),
        "autonomy_score": getattr(fragment, "autonomy_score", None) or round((fragment.virality_score or 0) * 0.30),
        "punchline_score": getattr(fragment, "punchline_score", None) or round((fragment.virality_score or 0) * 0.25),
        "viral_multiplier": max(0, (fragment.virality_score or 0) - (
            (getattr(fragment, "hook_score", None) or round((fragment.virality_score or 0) * 0.30)) +
            (getattr(fragment, "autonomy_score", None) or round((fragment.virality_score or 0) * 0.30)) +
            (getattr(fragment, "punchline_score", None) or round((fragment.virality_score or 0) * 0.25))
        )),
        "hook_reason": fragment.hook_reason or fragment.reasoning or "",
        "internal_criticism": fragment.internal_criticism or "",
        "first_words": fragment.first_words or "",
        "last_words": fragment.last_words or "",
        "reasoning": fragment.reasoning or "",
        "summary": fragment.summary or "",
        "status": fragment.status,
        "video_path": fragment.video_path,
        "has_video": has_video,
        "download_url": f"/api/v1/fragments/{fragment.id}/download",
        "stream_url": f"/media/clips/{clip_filename}",
        "youtube_preview_url": preview_url,
    }


@app.get("/api/v1/tasks/{task_id}", tags=["Tasks & Polling"])
def get_task(task_id: int):
    """Получение агрегированного статуса задачи, этапов пайплайна и клипов (Карточки 6 и 9)."""
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

        fragments = (
            db.query(ShortFragment)
            .filter(ShortFragment.task_id == task_id)
            .order_by(ShortFragment.start_time.asc())
            .all()
        )

        progress, current_step, step_label, stages = _get_stage_info(task)

        clips_dto = [_serialize_fragment_dto(f, task.youtube_url) for f in fragments]
        ready_count = sum(1 for c in clips_dto if c["status"] == "ready")
        error_count = sum(1 for c in clips_dto if c["status"] == "error")
        pending_count = len(clips_dto) - ready_count - error_count

        return {
            "id": task.id,
            "status": task.status,
            "youtube_url": task.youtube_url,
            "fragments_count": len(fragments),
            "progress": progress,
            "transcription_progress": int(
                getattr(task, "transcription_progress", 0) or 0
                ),
            "current_step": current_step,
            "step_label": step_label,
            "error_message": task.error_message,
            "stages": stages,
            "clips_summary": {
                "total": len(fragments),
                "ready": ready_count,
                "pending": pending_count,
                "error": error_count,
            },
            "clips": clips_dto,
            "created_at": task.created_at.isoformat() if getattr(task, "created_at", None) else None,
            "updated_at": task.updated_at.isoformat() if getattr(task, "updated_at", None) else None,
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


@app.get("/api/v1/tasks/{task_id}/status", tags=["Tasks & Polling"])
def get_task_status(task_id: int):
    """Легковесный эндпоинт опроса статусов этапов пайплайна для фронтенда (Карточка 9)."""
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

        progress, current_step, step_label, stages = _get_stage_info(task)

        clips_dto = [_serialize_fragment_dto(f, task.youtube_url) for f in fragments]
        ready_count = sum(1 for c in clips_dto if c["status"] == "ready")
        error_count = sum(1 for c in clips_dto if c["status"] == "error")
        pending_count = len(clips_dto) - ready_count - error_count

        return {
            "task_id": task.id,
            "status": task.status,
            "youtube_url": task.youtube_url,
            "progress": progress,
            "transcription_progress": int(
                getattr(task, "transcription_progress", 0) or 0
            ),
            "current_step": current_step,
            "step_label": step_label,
            "is_completed": task.status == "completed",
            "is_failed": task.status == "error",
            "error_message": task.error_message,
            "stages": stages,
            "clips_summary": {
                "total": len(fragments),
                "ready": ready_count,
                "pending": pending_count,
                "error": error_count,
            },
            "clips": clips_dto,
            "created_at": task.created_at.isoformat() if getattr(task, "created_at", None) else None,
            "updated_at": task.updated_at.isoformat() if getattr(task, "updated_at", None) else None,
        }
    finally:
        db.close()


@app.get("/api/v1/tasks/{task_id}/fragments", tags=["Clips"])
def get_task_fragments(task_id: int):
    """Выдача списка карточек клипов с баллами вирусности и ссылками для фронтенда Олега (Карточка 6)."""
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
            "fragments": [_serialize_fragment_dto(f, task.youtube_url) for f in fragments],
        }
    finally:
        db.close()


@app.patch("/api/v1/fragments/{fragment_id}/adjust", tags=["Clips"])
def adjust_fragment_timecodes(fragment_id: int, data: AdjustFragmentRequest):
    """Корректировка таймкодов клипа пользователем и перезапуск рендеринга."""
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

        try:
            render_fragment_video.delay(
                fragment_id=fragment.id,
                start_sec=fragment.adjusted_start_time,
                end_sec=fragment.adjusted_end_time,
            )
        except Exception:
            pass

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
            "download_url": f"/api/v1/fragments/{fragment.id}/download",
            "stream_url": f"/media/clips/fragment_{fragment.id}.mp4",
            "message": "Таймкоды успешно скорректированы, отправлено на повторную нарезку",
        }
    finally:
        db.close()


@app.get("/api/v1/fragments/{fragment_id}", tags=["Clips"])
def get_fragment_detail(fragment_id: int):
    """Детальная карточка клипа со всеми метаданными скоринга (Карточка 6)."""
    db = SessionLocal()
    try:
        fragment = db.get(ShortFragment, fragment_id)
        if fragment is None:
            raise HTTPException(status_code=404, detail="Fragment not found")

        task = db.get(VideoTask, fragment.task_id)
        youtube_url = task.youtube_url if task else None

        return _serialize_fragment_dto(fragment, youtube_url)
    finally:
        db.close()


@app.get("/media/clips/{filename}", tags=["Media Delivery"])
def stream_video_clip(filename: str):
    """Стриминг MP4-видеопотока для вертикального плеера 9:16."""
    safe_filename = os.path.basename(filename)
    if safe_filename != filename or not re.match(r"^[a-zA-Z0-9_\-\.]+\.mp4$", safe_filename):
        raise HTTPException(status_code=400, detail="Некорректное имя видеофайла")

    file_path = MEDIA_DIR / safe_filename
    if not file_path.exists():
        match = re.match(r"^fragment_(\d+)\.mp4$", safe_filename)
        if match:
            fragment_id = int(match.group(1))
            db = SessionLocal()
            try:
                fragment = db.get(ShortFragment, fragment_id)
                if fragment:
                    start_sec = fragment.adjusted_start_time if fragment.adjusted_start_time is not None else fragment.start_time
                    end_sec = fragment.adjusted_end_time if fragment.adjusted_end_time is not None else fragment.end_time
                    default_source = source_video_for_task(fragment.task_id)
                    try:
                        cut_vertical_clip(
                            source_path=default_source,
                            output_filename=safe_filename,
                            start_sec=start_sec,
                            end_sec=end_sec,
                        )
                        fragment.video_path = f"/media/clips/{safe_filename}"
                        fragment.status = "ready"
                        db.commit()
                    except Exception:
                        pass
            finally:
                db.close()

    if not file_path.exists():
        raise HTTPException(status_code=404, detail="Клип еще рендерится или не найден")
    return FileResponse(path=str(file_path), media_type="video/mp4")


@app.get("/api/v1/fragments/{fragment_id}/download", tags=["Media Delivery"])
def download_fragment(fragment_id: int):
    """Прямое скачивание готового MP4 файла клипа (Карточка 6)."""
    filename = f"fragment_{fragment_id}.mp4"
    file_path = MEDIA_DIR / filename
    if not file_path.exists():
        db = SessionLocal()
        try:
            fragment = db.get(ShortFragment, fragment_id)
            if fragment is None:
                raise HTTPException(status_code=404, detail="Файл клипа не найден")

            start_sec = fragment.adjusted_start_time if fragment.adjusted_start_time is not None else fragment.start_time
            end_sec = fragment.adjusted_end_time if fragment.adjusted_end_time is not None else fragment.end_time
            default_source = source_video_for_task(fragment.task_id)
            try:
                cut_vertical_clip(
                    source_path=default_source,
                    output_filename=filename,
                    start_sec=start_sec,
                    end_sec=end_sec,
                )
                fragment.video_path = f"/media/clips/{filename}"
                fragment.status = "ready"
                db.commit()
            except Exception as cut_err:
                raise HTTPException(
                    status_code=404,
                    detail=f"Клип еще обрабатывается или недоступен для скачивания: {cut_err}",
                )
        finally:
            db.close()

    if not file_path.exists():
        raise HTTPException(status_code=404, detail="Файл клипа не найден")

    return FileResponse(
        path=str(file_path),
        media_type="video/mp4",
        filename=f"shorts_{fragment_id}.mp4",
        headers={"Content-Disposition": f'attachment; filename="shorts_{fragment_id}.mp4"'},
    )