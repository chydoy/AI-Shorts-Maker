# AI Shorts Maker — Полная сборка (Части 1, 2 и 3)

## Архитектура и реализованный функционал

### 1. DevOps & Базовая среда (Екатерина)
- `docker-compose.yml` объединяет 4 сервиса: `web` (FastAPI), `worker` (Celery), `db` (PostgreSQL), `redis` (Redis).
- Общий Docker volume `/shared/media` для обмена медиафайлами между контейнерами.
- Автоматический retry при старте базы данных (`init_db` с автоповторами).
- Базовые таблицы: `video_tasks`, `transcripts`.

### 2. Медиа и распознавание речи (Влад)
- `yt-dlp[default]` для скачивания аудиодорожки с YouTube с поддержкой `player_client: android`.
- Установка **Deno** внутри Docker для надежного решения JavaScript-челленджей YouTube.
- FFmpeg для конвертации аудио в формат 16kHz WAV.
- `Faster-Whisper` (модель `small` на CPU с квантизацией `int8`) для высокоточного распознавания речи с пословными таймкодами (`word_timestamps=True`).
- Сохранение транскрипта в PostgreSQL и в `/shared/media/{id}_transcript.json`.

### 3. Семантический AI / LLM и выдача шортсов (Александр)
- Таблица `short_fragments` в PostgreSQL для хранения отобранных вирусных клипов.
- Модуль `llm.py`: системный промпт вирусного редактора для отбора от 1 до 5 фрагментов длительностью от 15 до 60 секунд с хуками и объяснением вирусности.
- Интеграция с **Groq Cloud** (сверхбыстрая модель `openai/gpt-oss-120b` / `llama-3.3-70b-versatile`) через формат OpenAI API.
- Встроенный резервный эвристический алгоритм нарезки (fallback): если ключ не задан или нет сети, пайплайн все равно завершается со статусом `completed`.
- Сохранение шортсов в `/shared/media/{id}_fragments.json` и в БД.
- REST API эндпоинт **`GET /api/v1/tasks/{task_id}/fragments`** для отдачи найденных клипов фронтенду Олега.

---

## Настройка окружения (`.env`)

В корне проекта лежит готовый файл `.env`:
```env
OPENAI_API_KEY=gsk_...
OPENAI_BASE_URL=https://api.groq.com/openai/v1
LLM_MODEL=openai/gpt-oss-120b
```

---

## Запуск проекта

1. Убедитесь, что запущен **Docker Desktop**.
2. В терминале в папке проекта выполните:
```bash
docker compose up --build
```

После завершения сборки откройте Swagger API:
👉 **http://localhost:8000/docs**

---

## Как протестировать

1. В Swagger откройте **`POST /api/v1/process`**, нажмите **«Try it out»** и отправьте ссылку:
```json
{
  "youtube_url": "https://www.youtube.com/watch?v=..."
}
```
2. Скопируйте полученный `task_id`.
3. Откройте **`GET /api/v1/tasks/{task_id}`** — статус последовательно пройдет:
   `pending` ➔ `downloading` ➔ `transcribing` ➔ `analyzing` ➔ `completed`.
4. Откройте **`GET /api/v1/tasks/{task_id}/fragments`** — вы получите массив отобранных шортсов с точными таймкодами, заголовками и обоснованием вирусности.

---

## Остановка

```bash
docker compose down
```


### 4. Пользовательский интерфейс и входной шлюз (Олег)
- `frontend/` — Next.js + Tailwind CSS интерфейс.
- Форма принимает и валидирует YouTube URL.
- `POST /api/v1/process` создаёт задачу и запускает Celery pipeline.
- Frontend автоматически опрашивает `GET /api/v1/tasks/{id}` до завершения.
- После `completed` загружает `GET /api/v1/tasks/{id}/fragments`.
- Карточки показывают заголовок, summary, таймкод и длительность.
- Кнопка «Предпросмотр» открывает исходное YouTube-видео на `start_time`.

### Полный запуск
```bash
docker compose up --build
```

- Frontend: http://localhost:3000
- Backend/Swagger: http://localhost:8000/docs
