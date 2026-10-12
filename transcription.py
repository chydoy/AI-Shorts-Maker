import json
import os
from pathlib import Path

from faster_whisper import WhisperModel

MODEL_SIZE = os.getenv("WHISPER_MODEL", "small")
DEVICE = os.getenv("WHISPER_DEVICE", "cpu")
COMPUTE_TYPE = os.getenv("WHISPER_COMPUTE_TYPE", "int8")

_model = None


def get_model() -> WhisperModel:
    global _model
    if _model is None:
        _model = WhisperModel(
            MODEL_SIZE,
            device=DEVICE,
            compute_type=COMPUTE_TYPE,
        )
    return _model


def transcribe_audio(audio_path: str) -> dict:
    """Transcribe audio and return text plus word-level timestamps."""
    if not Path(audio_path).exists():
        raise FileNotFoundError(f"Audio file does not exist: {audio_path}")

    model = get_model()
    segments, info = model.transcribe(
        audio_path,
        word_timestamps=True,
        vad_filter=False,
    )

    text_parts = []
    words = []

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

    return {
        "text": " ".join(part for part in text_parts if part),
        "words": words,
        "language": info.language,
    }


def save_transcript_json(result: dict, task_id: int) -> str:
    path = Path("/shared/media") / f"{task_id}_transcript.json"
    path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    return str(path)
