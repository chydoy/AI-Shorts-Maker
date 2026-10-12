import json
import os

from celery import Celery

from database import SessionLocal, ShortFragment, Transcript, VideoTask
from llm import find_shorts_moments, save_fragments_json
from media import download_audio
from transcription import save_transcript_json, transcribe_audio

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")

celery_app = Celery(
    "worker",
    broker=REDIS_URL,
    backend=REDIS_URL,
)


@celery_app.task(bind=True, name="process_video")
def process_video(self, task_id: int, youtube_url: str):
    db = SessionLocal()
    task = db.get(VideoTask, task_id)

    if task is None:
        db.close()
        raise ValueError(f"Task {task_id} not found")

    try:
        task.status = "downloading"
        db.commit()

        audio_path = download_audio(youtube_url, task_id)

        task.status = "transcribing"
        db.commit()

        result = transcribe_audio(audio_path)
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

        # Step 3 (Alexander): Semantic AI analysis and shorts moments detection
        task.status = "analyzing"
        db.commit()

        fragments_data = find_shorts_moments(
            text=result["text"],
            words=result["words"],
            task_id=task_id,
        )
        save_fragments_json(fragments_data, task_id)

        for item in fragments_data:
            fragment = ShortFragment(
                task_id=task_id,
                title=item["title"],
                start_time=float(item["start_time"]),
                end_time=float(item["end_time"]),
                duration=float(item.get("duration", round(item["end_time"] - item["start_time"], 2))),
                reasoning=item.get("reasoning", ""),
                summary=item.get("summary", ""),
            )
            db.add(fragment)

        task.status = "completed"
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

    except Exception:
        task.status = "error"
        db.commit()
        raise
    finally:
        db.close()
