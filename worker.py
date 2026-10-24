
import json
import os

from database import SessionLocal, ShortFragment, Transcript, VideoTask
from llm import find_shorts_moments, save_fragments_json
from media import (
    download_audio,
    download_source_video,
    source_video_for_task,
    cut_vertical_clip,
)
from transcription import save_transcript_json, transcribe_audio

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")

try:
    from celery import Celery

    celery_app = Celery(
        "worker",
        broker=REDIS_URL,
        backend=REDIS_URL,
    )
except ImportError:
    class MockCeleryApp:
        def task(self, *args, **kwargs):
            def decorator(fn):
                def delay(*a, **kw):
                    class MockAsyncResult:
                        id = "mock-task-id"

                    return MockAsyncResult()

                fn.delay = delay
                return fn

            return decorator

    celery_app = MockCeleryApp()


@celery_app.task(bind=True, name="process_video")
def process_video(self, task_id: int, youtube_url: str):
    db = SessionLocal()
    task = db.get(VideoTask, task_id)

    if task is None:
        db.close()
        raise ValueError(f"Task {task_id} not found")

    try:
        # Этап 1: Загрузка медиапотока
        task.status = "downloading"
        task.current_step = "downloading"
        task.progress = 15
        task.transcription_progress = 0
        task.error_message = None
        db.commit()

        source_video_path = download_source_video(youtube_url, task_id)
        audio_path = download_audio(
            youtube_url,
            task_id,
            source_video_path=source_video_path,
        )

        # Этап 2: Транскрибация речи Faster-Whisper
        task.status = "transcribing"
        task.current_step = "transcribing"
        task.progress = 40
        task.transcription_progress = 0
        db.commit()

        def update_transcription_progress(value: int):
            # Callback вызывается по мере обработки сегментов Whisper.
            task.transcription_progress = max(0, min(100, int(value)))
            db.commit()

        result = transcribe_audio(
            audio_path,
            progress_callback=update_transcription_progress,
        )
        task.transcription_progress = 100
        db.commit()

        save_transcript_json(result, task_id)

        transcript = Transcript(
            task_id=task_id,
            audio_path=audio_path,
            text=result["text"],
            words_json=json.dumps(result["words"], ensure_ascii=False),
            language=result["language"],
        )
        db.add(transcript)
        db.commit()

        # Этап 3: Семантический отбор LLM и расчет вирусности
        task.status = "analyzing"
        task.current_step = "analyzing"
        task.progress = 65
        db.commit()

        fragments_data = find_shorts_moments(
            text=result["text"],
            words=result["words"],
            task_id=task_id,
        )
        save_fragments_json(fragments_data, task_id)

        saved_fragments = []

        for item in fragments_data:
            fragment = ShortFragment(
                task_id=task_id,
                title=item["title"],
                start_time=float(item["start_time"]),
                end_time=float(item["end_time"]),
                duration=float(
                    item.get(
                        "duration",
                        round(item["end_time"] - item["start_time"], 2),
                    )
                ),
                reasoning=item.get("reasoning", ""),
                summary=item.get("summary", ""),
                virality_score=int(item.get("virality_score", 80)),
                hook_reason=item.get(
                    "hook_reason",
                    item.get("reasoning", ""),
                ),
                internal_criticism=item.get("internal_criticism", ""),
                first_words=item.get("first_words", ""),
                last_words=item.get("last_words", ""),
                adjusted_start_time=None,
                adjusted_end_time=None,
                status="cutting",
            )
            db.add(fragment)
            saved_fragments.append(fragment)

        db.commit()

        # Этап 4: Нарезка вертикальных видео FFmpeg (9:16)
        task.status = "cutting"
        task.current_step = "cutting"
        task.progress = 80
        db.commit()

        total_frags = len(saved_fragments)
        default_source = source_video_path or source_video_for_task(task_id)

        for idx, fragment in enumerate(saved_fragments):
            output_filename = f"fragment_{fragment.id}.mp4"

            try:
                cut_vertical_clip(
                    source_path=default_source,
                    output_filename=output_filename,
                    start_sec=fragment.start_time,
                    end_sec=fragment.end_time,
                )
                fragment.video_path = f"/media/clips/{output_filename}"
                fragment.status = "ready"

            except Exception:
                fragment.status = "error"

            if total_frags > 0:
                task.progress = min(
                    98,
                    80 + int(18 * (idx + 1) / total_frags),
                )

            db.commit()

        task.status = "completed"
        task.current_step = "completed"
        task.progress = 100
        task.transcription_progress = 100
        task.error_message = None
        db.commit()

        return {
            "task_id": task_id,
            "status": "completed",
            "audio_path": audio_path,
            "transcript_path": f"/shared/media/{task_id}_transcript.json",
            "fragments_path": f"/shared/media/{task_id}_fragments.json",
            "language": result["language"],
            "words_count": len(result["words"]),
            "fragments_count": len(fragments_data),
        }

    except Exception as exc:
        task.status = "error"
        task.error_message = str(exc)
        db.commit()
        raise

    finally:
        db.close()


@celery_app.task(name="render_fragment_video")
def render_fragment_video(
    fragment_id: int,
    start_sec: float,
    end_sec: float,
    source_video: str = "/shared/media/source.mp4",
):
    """Асинхронная генерация MP4-клипа и запись пути в БД."""

    output_filename = f"fragment_{fragment_id}.mp4"
    db = SessionLocal()

    try:
        fragment = (
            db.query(ShortFragment)
            .filter(ShortFragment.id == fragment_id)
            .first()
        )

        if not fragment:
            return {
                "status": "failed",
                "error": f"Fragment {fragment_id} not found",
            }

        task_source = source_video_for_task(fragment.task_id)
        actual_source = (
            task_source if os.path.exists(task_source) else source_video
        )

        rendered_path = cut_vertical_clip(
            source_path=actual_source,
            output_filename=output_filename,
            start_sec=start_sec,
            end_sec=end_sec,
        )

        fragment.video_path = f"/media/clips/{output_filename}"
        fragment.status = "ready"
        db.commit()

        return {
            "status": "completed",
            "fragment_id": fragment_id,
            "video_path": rendered_path,
        }

    except Exception as exc:
        fragment = (
            db.query(ShortFragment)
            .filter(ShortFragment.id == fragment_id)
            .first()
        )

        if fragment:
            fragment.status = "error"
            db.commit()

        return {"status": "failed", "error": str(exc)}

    finally:
        db.close()
