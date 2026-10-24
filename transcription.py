
import json
import os
import subprocess
from pathlib import Path

MODEL_SIZE = os.getenv("WHISPER_MODEL", "small")
DEVICE = os.getenv("WHISPER_DEVICE", "cpu")
COMPUTE_TYPE = os.getenv("WHISPER_COMPUTE_TYPE", "int8")

_model = None


def get_model():
    global _model

    if _model is None:
        from faster_whisper import WhisperModel

        _model = WhisperModel(
            MODEL_SIZE,
            device=DEVICE,
            compute_type=COMPUTE_TYPE,
        )

    return _model


def transcribe_audio(audio_path: str, progress_callback=None) -> dict:
    """Transcribe audio and return text plus word-level timestamps."""

    if not Path(audio_path).exists():
        raise FileNotFoundError(f"Audio file does not exist: {audio_path}")

    duration = get_audio_duration(audio_path)

    if duration <= 0:
        raise ValueError(f"Invalid audio duration: {duration}")

    if progress_callback:
        progress_callback(0)

    model = get_model()

    segments, info = model.transcribe(
        audio_path,
        word_timestamps=True,
        vad_filter=False,
    )

    text_parts = []
    words = []
    last_progress = 0

    for segment in segments:
        text_parts.append(segment.text.strip())

        if segment.words:
            for word in segment.words:
                words.append(
                    {
                        "word": word.word.strip(),
                        "start": round(word.start, 3),
                        "end": round(word.end, 3),
                    }
                )

        # Процент по временной позиции текущего сегмента аудио.
        current_progress = min(
            99,
            int(segment.end / duration * 100),
        )

        # Отправляем обновление, только когда процент изменился.
        if current_progress > last_progress:
            last_progress = current_progress

            if progress_callback:
                progress_callback(current_progress)

    if progress_callback:
        progress_callback(100)

    return {
        "text": " ".join(part for part in text_parts if part),
        "words": words,
        "language": info.language,
    }


def get_audio_duration(audio_path: str) -> float:
    result = subprocess.run(
        [
            "ffprobe",
            "-v", "error",
            "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1",
            audio_path,
        ],
        capture_output=True,
        text=True,
        check=True,
    )

    return float(result.stdout.strip())


def save_transcript_json(result: dict, task_id: int) -> str:
    path = Path("/shared/media") / f"{task_id}_transcript.json"

    path.write_text(
        json.dumps(result, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    return str(path)
