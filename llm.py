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

    # Target chunks of ~30-45 seconds across the full video
    target_duration = 35.0
    current_start = 0.0
    chunk_index = 1

    while current_start < total_duration:
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

            # Score range 45 to 100
            score = max(45, min(95, 88 - (chunk_index - 1) * 3))
            hook_score = max(12, min(30, int(score * 0.30)))
            autonomy_score = max(12, min(30, int(score * 0.30)))
            punchline_score = max(10, min(25, int(score * 0.25)))

            fragments.append(
                {
                    "title": f"Фрагмент #{chunk_index}: {preview_title or 'Интересный момент'}",
                    "start_time": round(actual_start, 2),
                    "end_time": round(actual_end, 2),
                    "duration": duration,
                    "first_words": first_words,
                    "last_words": last_words,
                    "virality_score": score,
                    "hook_score": hook_score,
                    "autonomy_score": autonomy_score,
                    "punchline_score": punchline_score,
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
            "hook_score": 24,
            "autonomy_score": 23,
            "punchline_score": 20,
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
            score = max(45, min(100, score))

            hook_score = int(frag.get("hook_score", 0)) if frag.get("hook_score") is not None else round(score * 0.30)
            autonomy_score = int(frag.get("autonomy_score", 0)) if frag.get("autonomy_score") is not None else round(score * 0.30)
            punchline_score = int(frag.get("punchline_score", 0)) if frag.get("punchline_score") is not None else round(score * 0.25)

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
                    "hook_score": hook_score,
                    "autonomy_score": autonomy_score,
                    "punchline_score": punchline_score,
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


def _normalize_token(text: str) -> str:
    """Normalize word token by stripping punctuation and lowercasing."""
    return re.sub(r"[^\wа-яА-ЯёЁa-zA-Z0-9]", "", text).lower()


def _has_sentence_end_punctuation(word_str: str) -> bool:
    """Check if word string ends with terminal punctuation (. ! ? …)."""
    clean = word_str.strip()
    return any(clean.endswith(p) for p in [".", "!", "?", "...", "…", "»", "”", '"', "“", ".'", "!'", "?'"])


def _find_words_by_quote(
    quote: str,
    words: list[dict],
    target_time: float,
    search_window: float = 6.0,
    prefer_end: bool = False,
) -> list[int]:
    """Find indices in words matching the token sequence of quote near target_time.

    Uses multi-stage matching:
    1. Exact sequence match of all tokens.
    2. Longest sub-sequence (n-gram) match (down to 2 tokens).
    3. Anchor token match (excluding short prepositions).
    """
    if not quote or not words:
        return []

    tokens = [_normalize_token(t) for t in quote.split()]
    tokens = [t for t in tokens if t]
    if not tokens:
        return []

    candidate_indices = [
        i for i, w in enumerate(words)
        if abs(w.get("start", 0.0) - target_time) <= search_window or abs(w.get("end", 0.0) - target_time) <= search_window
    ]
    if not candidate_indices:
        candidate_indices = list(range(len(words)))

    # 1. Search for longest matching n-gram slice from len(tokens) down to 2
    for n in range(len(tokens), 1, -1):
        best_match_indices: list[int] = []
        min_dist = float("inf")

        if prefer_end:
            slices_to_check = [tokens[s : s + n] for s in range(len(tokens) - n, -1, -1)]
        else:
            slices_to_check = [tokens[s : s + n] for s in range(len(tokens) - n + 1)]

        for target_slice in slices_to_check:
            k = len(target_slice)
            for i in candidate_indices:
                if i + k <= len(words):
                    seq = [_normalize_token(words[i + j].get("word", "")) for j in range(k)]
                    if seq == target_slice:
                        mid_time = (words[i].get("start", 0.0) + words[i + k - 1].get("end", 0.0)) / 2.0
                        dist = abs(mid_time - target_time)
                        if dist < min_dist:
                            min_dist = dist
                            best_match_indices = list(range(i, i + k))

        if best_match_indices:
            return best_match_indices

    # 2. Single token match: prefer primary anchor token
    anchor_tokens = [tokens[-1]] if prefer_end else [tokens[0]]
    anchor_tokens.extend([t for t in tokens if len(t) >= 3 and t not in anchor_tokens])

    for token in anchor_tokens:
        best_match_indices = []
        min_dist = float("inf")
        for i in candidate_indices:
            word_norm = _normalize_token(words[i].get("word", ""))
            if word_norm == token:
                dist = abs(words[i].get("start", 0.0) - target_time)
                if dist < min_dist:
                    min_dist = dist
                    best_match_indices = [i]
        if best_match_indices:
            return best_match_indices

    return []


def _align_fragments_to_words(
    fragments: list[dict],
    words: list[dict],
    start_buffer: float = 0.08,
    end_buffer: float = 0.18,
) -> list[dict]:
    """Snap fragment timestamps to word boundaries from Faster-Whisper to eliminate audio cutoffs.

    Uses quote matching for first_words and last_words, verifies punctuation (. ! ?),
    and applies acoustic buffers (-80ms at start, +180ms at end).
    """
    if not fragments or not words:
        return fragments

    aligned = []
    for frag in fragments:
        start_t = float(frag.get("start_time", 0.0))
        end_t = float(frag.get("end_time", 0.0))
        first_words_quote = str(frag.get("first_words", "")).strip()
        last_words_quote = str(frag.get("last_words", "")).strip()

        # 1. Start boundary alignment
        best_start_word = None
        if first_words_quote:
            start_indices = _find_words_by_quote(first_words_quote, words, start_t, search_window=5.0, prefer_end=False)
            if start_indices:
                best_start_word = words[start_indices[0]]

        if best_start_word is None:
            min_start_diff = float("inf")
            for w in words:
                diff = abs(w.get("start", 0.0) - start_t)
                if diff < min_start_diff and diff <= 4.0:
                    min_start_diff = diff
                    best_start_word = w

        if best_start_word is not None:
            # Buffer -80ms (-0.08s) clamped at 0.0
            start_t = max(0.0, round(best_start_word.get("start", start_t) - start_buffer, 3))

        # 2. End boundary alignment
        best_end_word = None
        best_end_idx = None
        if last_words_quote:
            end_indices = _find_words_by_quote(last_words_quote, words, end_t, search_window=5.0, prefer_end=True)
            if end_indices:
                best_end_idx = end_indices[-1]
                best_end_word = words[best_end_idx]

        if best_end_word is None:
            min_end_diff = float("inf")
            for idx, w in enumerate(words):
                diff = abs(w.get("end", 0.0) - end_t)
                if diff < min_end_diff and diff <= 4.0:
                    min_end_diff = diff
                    best_end_word = w
                    best_end_idx = idx

        # 3. Check punctuation (. ! ?) and thought completeness
        if best_end_word is not None and best_end_idx is not None:
            if not _has_sentence_end_punctuation(best_end_word.get("word", "")):
                # Lookahead up to 8 words to reach terminal punctuation, unless speech pauses > 1.2s
                for lookahead_idx in range(best_end_idx + 1, min(len(words), best_end_idx + 9)):
                    ahead_word = words[lookahead_idx]
                    prev_word = words[lookahead_idx - 1]
                    if ahead_word.get("start", 0.0) - prev_word.get("end", 0.0) > 1.2:
                        break
                    if ahead_word.get("end", end_t) - start_t > 65.0:
                        break
                    best_end_word = ahead_word
                    if _has_sentence_end_punctuation(ahead_word.get("word", "")):
                        break

            # Buffer +180ms (+0.18s) to prevent clipped consonants
            end_t = round(best_end_word.get("end", end_t) + end_buffer, 3)

        if end_t <= start_t:
            end_t = start_t + 15.0

        duration = round(end_t - start_t, 3)
        if duration > 65.0:
            end_t = round(start_t + 60.0, 3)
            duration = 60.0

        # Anchor words from word list if missing or short
        window_words = [w for w in words if start_t - 0.2 <= w.get("start", 0.0) <= end_t + 0.2]
        first_words = frag.get("first_words", "").strip()
        last_words = frag.get("last_words", "").strip()
        if window_words and (not first_words or len(first_words.split()) < 2):
            first_words = " ".join(w.get("word", "").strip() for w in window_words[:4]).strip(" ,;:!?-")
        if window_words and (not last_words or len(last_words.split()) < 2):
            last_words = " ".join(w.get("word", "").strip() for w in window_words[-4:]).strip(" ,;:!?-")

        updated_frag = dict(frag)
        updated_frag["start_time"] = start_t
        updated_frag["end_time"] = end_t
        updated_frag["duration"] = duration
        if first_words:
            updated_frag["first_words"] = first_words
        if last_words:
            updated_frag["last_words"] = last_words

        aligned.append(updated_frag)

    return aligned


def find_shorts_moments(text: str, words: list[dict], task_id: int | None = None) -> list[dict]:
    """Analyze video transcript and find viral short moments up to 60 seconds with automatic LLM fallback cascade."""
    if not text.strip():
        return []

    timed_transcript = _prepare_timed_transcript(words) if words else text

    system_prompt = (
        "Ты являешься главным шеф-редактором и продюсером вирусных YouTube Shorts, Reels и TikTok с миллионными охватами.\n"
        "Твоя цель: проанализировать расшифровку видео с таймкодами и извлечь все качественные, "
        "смысловые и эмоционально цепляющие моменты по всему видеоматериалу со скорингом от 45 до 100 баллов.\n\n"
        "МЕТОДОЛОГИЯ АДВОКАТА ДЬЯВОЛА И САМОКРИТИКИ (SELF-DEBATE):\n"
        "Для каждого потенциального момента ты ОБЯЗАН провести внутренний спор Оптимиста (ищет вирусность) "
        "и Скептика-Критика (ищет причины свайпнуть видео):\n"
        "1. The 3-Second Hook Rule (Сила хука, max 30 баллов): Первые 3 секунды обязаны содержать интригующий вопрос, "
        "парадокс или острый тезис. Если спикер начинает со слов 'Ну', 'Кстати', 'И вот', вздохов или мычания, то Скептик штрафует фрагмент "
        "и сдвигает старт прямо к началу ударной мысли.\n"
        "2. The Stranger Test (Автономность контекста, max 30 баллов): Зритель, который никогда не смотрел исходное видео, "
        "обязан мгновенно понять суть без предыстории. Запрещены повисшие местоимения без субъекта ('он сказал ему', 'из-за этого случая').\n"
        "3. The Punchline & Outro Rule (Завершенность мысли и панчлайн, max 25 баллов): Фраза обязана оканчиваться четким смысловым выводом, "
        "ответом на вопрос или панчлайном. Категорически запрещено обрывать мысль на полуслове, вводных конструкциях или союзах "
        "('потому что...', 'если...', 'так как...', 'и вот...', 'но...'). Если предложение не закончено, сдвинь границу до завершающей точки "
        "или восклицательного/вопросительного знака.\n"
        "4. Viral Multiplier (Виральный триггер, max 15 баллов): Вызывает ли ролик желание переслать другу, сохранить или поспорить в комментариях?\n\n"
        "ШКАЛА ВИРУСНОСТИ (VIRALITY SCORE 45–100):\n"
        "Virality Score равен сумме 4 критериев (Hook + Stranger_Test + Punchline + Viral_Multiplier).\n"
        "Извлекай все качественные фрагменты по всему видео: топовые вирусные клипы (75–100 баллов) "
        "и добротные содержательные моменты для архива (45–74 баллов).\n\n"
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
        '      "hook_score": 28,\n'
        '      "autonomy_score": 27,\n'
        '      "punchline_score": 22,\n'
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
        "Проведи глубокий критический анализ, примени 4 правила и извлеки все качественные моменты (Virality Score от 45 до 100) по всему видеоматериалу в формате JSON."
    )

    # 1. Попытка через основной провайдер (OrcaRouter)
    if OPENAI_API_KEY:
        try:
            logger.info("Calling primary LLM provider (%s / %s)...", OPENAI_BASE_URL, LLM_MODEL)
            fragments = _execute_llm_request(OPENAI_API_KEY, OPENAI_BASE_URL, LLM_MODEL, system_prompt, user_prompt)
            if fragments:
                logger.info("Primary LLM provider returned %d fragments.", len(fragments))
                return _align_fragments_to_words(fragments, words)
        except Exception as exc:
            logger.warning("Primary LLM provider failed (%s). Attempting backup provider...", exc)

    # 2. Попытка через резервный провайдер (Groq API)
    if BACKUP_OPENAI_API_KEY:
        try:
            logger.info("Calling backup LLM provider (%s / %s)...", BACKUP_OPENAI_BASE_URL, BACKUP_LLM_MODEL)
            fragments = _execute_llm_request(BACKUP_OPENAI_API_KEY, BACKUP_OPENAI_BASE_URL, BACKUP_LLM_MODEL, system_prompt, user_prompt)
            if fragments:
                logger.info("Backup LLM provider returned %d fragments.", len(fragments))
                return _align_fragments_to_words(fragments, words)
        except Exception as exc:
            logger.warning("Backup LLM provider failed (%s). Falling back to heuristic segmentation...", exc)

    # 3. Офлайн-страховка: эвристический отбор по паузам речи Faster-Whisper
    logger.info("Using reliable heuristic fallback segmentation.")
    fallback_frags = _fallback_extract_moments(text, words)
    return _align_fragments_to_words(fallback_frags, words)


def save_fragments_json(fragments: list[dict], task_id: int) -> str:
    """Save extracted fragments to shared storage."""
    path = SHARED_MEDIA_DIR / f"{task_id}_fragments.json"
    path.write_text(json.dumps(fragments, ensure_ascii=False, indent=2), encoding="utf-8")
    return str(path)
