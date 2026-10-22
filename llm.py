import json
import logging
import os
import re
from pathlib import Path

logger = logging.getLogger(__name__)

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "").strip()
OPENAI_BASE_URL = os.getenv("OPENAI_BASE_URL", "https://api.orcarouter.ai/v1").strip()
LLM_MODEL = os.getenv("LLM_MODEL", "deepseek/deepseek-v4.1-flash-free").strip()

# Резервный провайдер (горячий бекап Groq API)
BACKUP_OPENAI_API_KEY = os.getenv("BACKUP_OPENAI_API_KEY", "").strip()
BACKUP_OPENAI_BASE_URL = os.getenv("BACKUP_OPENAI_BASE_URL", "https://api.groq.com/openai/v1").strip()
BACKUP_LLM_MODEL = os.getenv("BACKUP_LLM_MODEL", "llama-3.3-70b-versatile").strip()


SHARED_MEDIA_DIR = Path(os.getenv("SHARED_MEDIA_DIR", "/shared/media"))
try:
    SHARED_MEDIA_DIR.mkdir(parents=True, exist_ok=True)
except Exception:
    SHARED_MEDIA_DIR = Path("./media")
    SHARED_MEDIA_DIR.mkdir(parents=True, exist_ok=True)


def _format_seconds(seconds: float) -> str:
    """Format seconds into MM:SS for prompt readability."""
    mins = int(seconds // 60)
    secs = int(seconds % 60)
    return f"{mins:02d}:{secs:02d}"


def _prepare_timed_transcript(words: list[dict], max_words: int = 8000) -> str:
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
                "first_words": "Начало фрагмента",
                "last_words": "Конец фрагмента",
                "virality_score": 78,
                "hook_reason": "Автоматически сформированный фрагмент по паузам речи",
                "internal_criticism": "Резервный режим без прямого вызова LLM API",
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

    while current_start < total_duration and len(fragments) < 5:
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
            preview_title = re.sub(r"[,;:!?-]+\s*$", "", preview_title).strip()
            if preview_title and not preview_title.endswith("."):
                preview_title += "..."

            first_words = " ".join(w.get("word", "").strip() for w in window_words[:4]).strip(" ,;:!?-")
            last_words = " ".join(w.get("word", "").strip() for w in window_words[-4:]).strip(" ,;:!?-")

            score = max(76, 85 - (chunk_index * 3))

            fragments.append(
                {
                    "title": f"Фрагмент #{chunk_index}: {preview_title or 'Интересный момент'}",
                    "start_time": round(actual_start, 2),
                    "end_time": round(actual_end, 2),
                    "duration": duration,
                    "first_words": first_words,
                    "last_words": last_words,
                    "virality_score": score,
                    "hook_reason": "Логически выделенный фрагмент на основе таймкодов речи",
                    "internal_criticism": "Автоматический отбор по границам предложений без срезания слов",
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
            "first_words": "Начало фрагмента",
            "last_words": "Завершение мысли",
            "virality_score": 78,
            "hook_reason": "Начальный содержательный отрезок видео",
            "internal_criticism": "Выделен базовый фрагмент по первым паузам",
            "reasoning": "Начальный содержательный отрезок видео",
            "summary": text[:200],
        }
    ]


def _execute_llm_request(
    api_key: str,
    base_url: str,
    model: str,
    system_prompt: str,
    user_prompt: str,
) -> list[dict] | None:
    """Execute chat completion request to an OpenAI-compatible API endpoint."""
    if not api_key:
        return None

    from openai import OpenAI

    client = OpenAI(
        api_key=api_key,
        base_url=base_url,
        timeout=35.0,
    )

    response = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        temperature=0.3,
        response_format={"type": "json_object"},
    )

    content = response.choices[0].message.content or "{}"
    clean_content = content.strip()
    if clean_content.startswith("```"):
        clean_content = re.sub(r"^```(?:json)?\s*", "", clean_content)
        clean_content = re.sub(r"\s*```$", "", clean_content).strip()

    parsed = json.loads(clean_content)
    if isinstance(parsed, list):
        raw_fragments = parsed
    else:
        raw_fragments = parsed.get("fragments") or parsed.get("shorts") or parsed.get("clips") or []

    validated = []
    for frag in raw_fragments:
        try:
            start = float(frag.get("start_time", 0.0))
            end = float(frag.get("end_time", 0.0))
            if end <= start:
                continue

            duration = round(end - start, 2)
            # Keep within shorts window (12s to 65s)
            if duration > 65.0:
                end = start + 60.0
                duration = 60.0

            score = int(frag.get("virality_score", 80))
            score = max(1, min(100, score))

            hook_reason = str(frag.get("hook_reason", "")).strip() or str(frag.get("reasoning", "")).strip()
            criticism = str(frag.get("internal_criticism", "")).strip()

            validated.append(
                {
                    "title": str(frag.get("title", "Вирусный фрагмент")).strip(),
                    "start_time": round(start, 2),
                    "end_time": round(end, 2),
                    "duration": duration,
                    "first_words": str(frag.get("first_words", "")).strip(),
                    "last_words": str(frag.get("last_words", "")).strip(),
                    "virality_score": score,
                    "hook_reason": hook_reason,
                    "internal_criticism": criticism,
                    "reasoning": hook_reason,
                    "summary": str(frag.get("summary", "")).strip(),
                }
            )
        except (ValueError, TypeError):
            continue

    if validated:
        validated.sort(key=lambda x: x["virality_score"], reverse=True)
        return validated
    return None


def find_shorts_moments(text: str, words: list[dict], task_id: int | None = None) -> list[dict]:
    """Analyze video transcript and find viral short moments up to 60 seconds with automatic LLM fallback cascade."""
    if not text.strip():
        return []

    timed_transcript = _prepare_timed_transcript(words) if words else text

    system_prompt = (
        "Ты — главный шеф-редактор и продюсер вирусных YouTube Shorts, Reels и TikTok с миллионными охватами.\n"
        "Твоя цель: проанализировать расшифровку видео с таймкодами и отобрать от 1 до 5 самых вирусных, "
        "смысловых и эмоционально цепляющих моментов.\n\n"
        "МЕТОДОЛОГИЯ АДВОКАТА ДЬЯВОЛА И САМОКРИТИКИ (SELF-DEBATE):\n"
        "Для каждого потенциального момента ты ОБЯЗАН провести внутренний спор Оптимиста (ищет вирусность) "
        "и Скептика-Критика (ищет причины свайпнуть видео):\n"
        "1. The 3-Second Hook Rule (Сила хука, max 30 баллов): Первые 3 секунды обязаны содержать интригующий вопрос, "
        "парадокс или острый тезис. Если спикер начинает со слов 'Ну', 'Кстати', 'И вот', вздохов или мычания — Скептик штрафует фрагмент "
        "и сдвигает старт прямо к началу ударной мысли.\n"
        "2. The Stranger Test (Автономность контекста, max 30 баллов): Зритель, который никогда не смотрел исходное видео, "
        "обязан мгновенно понять суть без предыстории. Запрещены повисшие местоимения без субъекта ('он сказал ему', 'из-за этого случая').\n"
        "3. The Punchline Rule (Логическая законченность, max 25 баллов): Мысль обязана прийти к четкому выводу или панчлайну. "
        "Категорически запрещено обрывать предложение на союзах ('потому что...', 'и тогда...').\n"
        "4. Viral Multiplier (Виральный триггер, max 15 баллов): Вызывает ли ролик желание переслать другу, сохранить или поспорить в комментариях?\n\n"
        "ШКАЛА ВИРУСНОСТИ (VIRALITY SCORE 1–100):\n"
        "Virality Score равен сумме 4 критериев (Hook + Stranger_Test + Punchline + Viral_Multiplier).\n"
        "В финальный список включай ТОЛЬКО моменты с Virality Score от 75 до 100 баллов!\n\n"
        "ФРАЗЫ-ЯКОРЯ ДЛЯ МИЛЛИСЕКУНДНОГО МОНТАЖА:\n"
        "Обязательно укажи точные цитаты первых 3–5 слов ('first_words') и последних 3–5 слов ('last_words') из расшифровки, "
        "чтобы звуковой модуль Faster-Whisper выровнял границы без обрезки звуков.\n\n"
        "ФОРМАТ ОТВЕТА (СТРОГО ВАЛИДНЫЙ JSON):\n"
        "{\n"
        '  "fragments": [\n'
        "    {\n"
        '      "title": "Кликбейтный, но правдивый заголовок до 60 символов",\n'
        '      "start_time": 14.2,\n'
        '      "end_time": 48.6,\n'
        '      "first_words": "Точные первые слова фразы",\n'
        '      "last_words": "Точные последние слова фразы",\n'
        '      "virality_score": 89,\n'
        '      "hook_reason": "Почему зритель не свайпнет в первые 3 секунды",\n'
        '      "internal_criticism": "Спор Оптимиста и Скептика: почему забраковали лишнее и почему выбраны именно эти границы",\n'
        '      "summary": "Краткая законченная суть фрагмента"\n'
        "    }\n"
        "  ]\n"
        "}"
    )

    user_prompt = (
        "Вот расшифровка видео с таймкодами:\n\n"
        f"{timed_transcript}\n\n"
        "Проведи глубокий критический анализ, примени 4 теста и верни только лучшие вирусные моменты (Virality Score >= 75) в формате JSON."
    )

    # 1. Попытка через основной провайдер (OrcaRouter)
    if OPENAI_API_KEY:
        try:
            logger.info("Calling primary LLM provider (%s / %s)...", OPENAI_BASE_URL, LLM_MODEL)
            fragments = _execute_llm_request(OPENAI_API_KEY, OPENAI_BASE_URL, LLM_MODEL, system_prompt, user_prompt)
            if fragments:
                logger.info("Primary LLM provider returned %d fragments.", len(fragments))
                return fragments
        except Exception as exc:
            logger.warning("Primary LLM provider failed (%s). Attempting backup provider...", exc)

    # 2. Попытка через резервный провайдер (Groq API)
    if BACKUP_OPENAI_API_KEY:
        try:
            logger.info("Calling backup LLM provider (%s / %s)...", BACKUP_OPENAI_BASE_URL, BACKUP_LLM_MODEL)
            fragments = _execute_llm_request(BACKUP_OPENAI_API_KEY, BACKUP_OPENAI_BASE_URL, BACKUP_LLM_MODEL, system_prompt, user_prompt)
            if fragments:
                logger.info("Backup LLM provider returned %d fragments.", len(fragments))
                return fragments
        except Exception as exc:
            logger.warning("Backup LLM provider failed (%s). Falling back to heuristic segmentation...", exc)

    # 3. Офлайн-страховка: эвристический отбор по паузам речи Faster-Whisper
    logger.info("Using reliable heuristic fallback segmentation.")
    return _fallback_extract_moments(text, words)


def save_fragments_json(fragments: list[dict], task_id: int) -> str:
    """Save extracted fragments to shared storage."""
    path = SHARED_MEDIA_DIR / f"{task_id}_fragments.json"
    path.write_text(json.dumps(fragments, ensure_ascii=False, indent=2), encoding="utf-8")
    return str(path)
