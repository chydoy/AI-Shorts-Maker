import json
import logging
import os
import re
from pathlib import Path

logger = logging.getLogger(__name__)

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "").strip()
OPENAI_BASE_URL = os.getenv("OPENAI_BASE_URL", "https://api.groq.com/openai/v1").strip()
LLM_MODEL = os.getenv("LLM_MODEL", "openai/gpt-oss-120b").strip()


SHARED_MEDIA_DIR = Path("/shared/media")
SHARED_MEDIA_DIR.mkdir(parents=True, exist_ok=True)


def _format_seconds(seconds: float) -> str:
    """Format seconds into MM:SS for prompt readability."""
    mins = int(seconds // 60)
    secs = int(seconds % 60)
    return f"{mins:02d}:{secs:02d}"


def _prepare_timed_transcript(words: list[dict], max_words: int = 1500) -> str:
    """Group words into timed lines (~15 words per line) to give the LLM clear context."""
    if not words:
        return ""

    words_to_use = words[:max_words]
    lines = []
    chunk = []

    for word_info in words_to_use:
        chunk.append(word_info)
        # Group around sentence ends or every ~12 words
        is_sentence_end = any(word_info.get("word", "").endswith(p) for p in [".", "!", "?", "..."])
        if is_sentence_end or len(chunk) >= 12:
            start_str = _format_seconds(chunk[0].get("start", 0.0))
            end_str = _format_seconds(chunk[-1].get("end", 0.0))
            line_text = " ".join(w.get("word", "") for w in chunk).strip()
            lines.append(f"[{start_str} - {end_str}] ({chunk[0].get('start', 0.0):.1f}s - {chunk[-1].get('end', 0.0):.1f}s): {line_text}")
            chunk = []

    if chunk:
        start_str = _format_seconds(chunk[0].get("start", 0.0))
        end_str = _format_seconds(chunk[-1].get("end", 0.0))
        line_text = " ".join(w.get("word", "") for w in chunk).strip()
        lines.append(f"[{start_str} - {end_str}] ({chunk[0].get('start', 0.0):.1f}s - {chunk[-1].get('end', 0.0):.1f}s): {line_text}")

    return "\n".join(lines)


def _fallback_extract_moments(text: str, words: list[dict]) -> list[dict]:
    """Smart heuristic fallback when LLM API is unavailable or unconfigured."""
    if not words:
        return [
            {
                "title": "Ключевой фрагмент видео",
                "start_time": 0.0,
                "end_time": min(60.0, 30.0),
                "duration": min(60.0, 30.0),
                "reasoning": "Автоматически сформированный фрагмент (резервный режим без LLM API)",
                "summary": text[:200] if text else "Содержание видео",
            }
        ]

    total_duration = words[-1].get("end", 0.0)
    fragments = []

    # Target chunks of ~30-45 seconds
    target_duration = 35.0
    current_start = 0.0
    chunk_index = 1

    while current_start < total_duration and len(fragments) < 3:
        target_end = min(current_start + target_duration, total_duration)

        # Find words within this time window
        window_words = [w for w in words if current_start <= w.get("start", 0.0) <= target_end]
        if not window_words:
            current_start += target_duration
            continue

        actual_start = window_words[0].get("start", current_start)
        actual_end = window_words[-1].get("end", target_end)
        duration = round(actual_end - actual_start, 2)

        if duration >= 10.0:
            frag_text = " ".join(w.get("word", "") for w in window_words)
            preview_title = frag_text[:50].strip()
            if preview_title and not preview_title.endswith("."):
                preview_title += "..."

            fragments.append(
                {
                    "title": f"Фрагмент #{chunk_index}: {preview_title or 'Интересный момент'}",
                    "start_time": round(actual_start, 2),
                    "end_time": round(actual_end, 2),
                    "duration": duration,
                    "reasoning": "Логически выделенный фрагмент на основе таймкодов речи",
                    "summary": frag_text[:250],
                }
            )
            chunk_index += 1

        current_start = actual_end + 10.0

    return fragments or [
        {
            "title": "Фрагмент видео",
            "start_time": round(words[0].get("start", 0.0), 2),
            "end_time": round(min(words[-1].get("end", 60.0), 59.0), 2),
            "duration": round(min(words[-1].get("end", 60.0), 59.0) - words[0].get("start", 0.0), 2),
            "reasoning": "Начальный содержательный отрезок видео",
            "summary": text[:200],
        }
    ]


def find_shorts_moments(text: str, words: list[dict], task_id: int | None = None) -> list[dict]:
    """Analyze video transcript and find viral short moments up to 60 seconds using LLM API."""
    if not text.strip():
        return []

    if not OPENAI_API_KEY:
        logger.warning("OPENAI_API_KEY is not configured. Falling back to heuristic segmentation.")
        return _fallback_extract_moments(text, words)

    timed_transcript = _prepare_timed_transcript(words) if words else text

    system_prompt = (
        "Ты — профессиональный вирусный редактор YouTube Shorts, TikTok и Reels.\n"
        "Твоя цель: проанализировать расшифровку видео с таймкодами и отобрать от 1 до 5 самых вирусных, "
        "смысловых и эмоционально цепляющих моментов.\n\n"
        "КРИТЕРИИ ОТБОРА:\n"
        "1. Длительность каждого фрагмента: СТРОГО от 15 до 60 секунд (end_time - start_time <= 60.0).\n"
        "2. Начало фрагмента (start_time) должно содержать яркий хук (интригующий вопрос, неожиданный тезис).\n"
        "3. Конец фрагмента (end_time) должен логически завершать мысль, без обрыва фразы на полуслове.\n"
        "4. Точные секунды (float): используй секунды из предоставленной транскрипции.\n\n"
        "ФОРМАТ ОТВЕТА:\n"
        "Ответь ИСКЛЮЧИТЕЛЬНО валидным JSON объектом следующей структуры:\n"
        "{\n"
        '  "fragments": [\n'
        "    {\n"
        '      "title": "Цепляющий кликбейтный, но честный заголовок",\n'
        '      "start_time": 15.2,\n'
        '      "end_time": 48.6,\n'
        '      "reasoning": "Почему этот момент удержит внимание зрителя",\n'
        '      "summary": "Краткая суть фрагмента"\n'
        "    }\n"
        "  ]\n"
        "}"
    )

    user_prompt = (
        "Вот расшифровка видео с таймкодами:\n\n"
        f"{timed_transcript}\n\n"
        "Выдели лучшие вирусные моменты длиной до 60 секунд. Верни только JSON."
    )

    try:
        from openai import OpenAI

        client = OpenAI(
            api_key=OPENAI_API_KEY,
            base_url=OPENAI_BASE_URL,
            timeout=45.0,
        )

        response = client.chat.completions.create(
            model=LLM_MODEL,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.4,
            response_format={"type": "json_object"},
        )

        content = response.choices[0].message.content or "{}"
        parsed = json.loads(content)
        raw_fragments = parsed.get("fragments", [])

        validated = []
        for frag in raw_fragments:
            try:
                start = float(frag.get("start_time", 0.0))
                end = float(frag.get("end_time", 0.0))
                if end <= start:
                    continue

                duration = round(end - start, 2)
                # Keep within reasonable shorts window (10s to 65s)
                if duration > 65.0:
                    end = start + 60.0
                    duration = 60.0

                validated.append(
                    {
                        "title": str(frag.get("title", "Вирусный фрагмент")).strip(),
                        "start_time": round(start, 2),
                        "end_time": round(end, 2),
                        "duration": duration,
                        "reasoning": str(frag.get("reasoning", "")).strip(),
                        "summary": str(frag.get("summary", "")).strip(),
                    }
                )
            except (ValueError, TypeError):
                continue

        if validated:
            return validated

        logger.warning("LLM returned empty or invalid fragments list. Using fallback.")
        return _fallback_extract_moments(text, words)

    except Exception as exc:
        logger.error(f"Error calling LLM API ({exc}). Using reliable fallback segmentation.")
        return _fallback_extract_moments(text, words)


def save_fragments_json(fragments: list[dict], task_id: int) -> str:
    """Save extracted fragments to shared storage."""
    path = SHARED_MEDIA_DIR / f"{task_id}_fragments.json"
    path.write_text(json.dumps(fragments, ensure_ascii=False, indent=2), encoding="utf-8")
    return str(path)
