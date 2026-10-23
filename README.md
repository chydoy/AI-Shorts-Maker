# AI Shorts Maker

Автоматизированный сервис для поиска, извлечения и генерации вирусных коротких видео (Shorts / Reels / TikTok) из длинных роликов YouTube на основе искусственного интеллекта.

Сервис принимает ссылку на видео с YouTube, извлекает аудиодорожку, транскрибирует речь с пословными таймкодами через модель Faster-Whisper, после чего нейросетевая модель (Groq / OpenAI API) находит наиболее яркие смысловые фрагменты длительностью 15–60 секунд с готовыми хуками и оценкой вирусности.

---

## Основные возможности

* **Загрузка и подготовка аудио**: скачивание аудиопотока через `yt-dlp` с интеграцией среды исполнения Deno для стабильного прохождения проверок YouTube, конвертация в формат WAV 16 кГц через FFmpeg.
* **Транскрибация речи**: высокоточное распознавание текста с пословными таймкодами с помощью `faster-whisper` (модель `small`, CPU, квантизация `int8`).
* **Smart Crop**: MediaPipe Face Mesh и OpenCV находят лица на выбранном интервале видео, выбирают вероятного спикера по размеру лица и изменению положения губ, сглаживают движение окна кадрирования через EMA и передают динамический crop-фильтр в FFmpeg. Если лицо не найдено или детекция недоступна, используется центральное кадрирование.
* **Интеллектуальный отбор вирусных фрагментов**: LLM-модуль на базе Groq (`openai/gpt-oss-120b` или `llama-3.3-70b-versatile`) анализирует контекст, выявляет кульминационные моменты, формулирует цепляющие заголовки и хуки.
* **Резервный эвристический алгоритм (Fallback)**: при временной недоступности LLM API система автоматически нарезает наиболее информативные сегменты по плотности речи.
* **Асинхронная очередь задач**: оркестрация длительных задач через Celery с брокером сообщений Redis.
* **Современный веб-интерфейс**: фронтенд на Next.js 14 и Tailwind CSS с процентным прогресс-баром, четырьмя визуальными стадиями обработки и карточками фрагментов со ссылками на предпросмотр в YouTube.
* **Полная контейнеризация**: единый запуск всей инфраструктуры (бэкенд, воркер, БД, брокер, фронтенд) через Docker Compose.

---

## Архитектура системы

```text
[ Пользователь / Браузер ]
           │
           ▼
[ Frontend (Next.js 14) ] ─── (REST API) ───► [ Backend (FastAPI) ]
                                                     │
                                                     ▼
                                          [ PostgreSQL 15 & Redis ]
                                                     │
                                                     ▼
                                          [ Worker (Celery) ]
                                            ├── yt-dlp + FFmpeg (скачивание видео и извлечение WAV)
                                            ├── Faster-Whisper (транскрипция речи)
                                            ├── Groq LLM API (поиск вирусных моментов)
                                            └── MediaPipe / OpenCV + FFmpeg (Smart Crop 9:16)
```

### Сервисы в Docker Compose:
1. `web`: REST API на базе FastAPI (порт 8000, документация Swagger UI).
2. `worker`: фоновый обработчик Celery, выполняющий ресурсоемкие операции транскрибации и взаимодействия с LLM.
3. `frontend`: веб-приложение на Next.js 14 (порт 3000).
4. `db`: реляционная база данных PostgreSQL 15 (порт 5432).
5. `redis`: брокер очередей сообщений и хранилище результатов Celery (порт 6379).

---

## Стек технологий

* **Backend**: Python 3.10, FastAPI, Celery, SQLAlchemy 2, Pydantic 2, Uvicorn.
* **AI & Media**: Faster-Whisper, yt-dlp, FFmpeg, Deno, Groq Cloud / OpenAI API.
* **Frontend**: Next.js 14 (App Router), React 18, TypeScript, Tailwind CSS.
* **Базы данных и инфраструктура**: PostgreSQL 15, Redis 7, Docker, Docker Compose.

---

## Быстрый запуск через Docker Compose

Для запуска требуется установленный и работающий **Docker Desktop**.

### 1. Настройка переменных окружения

Скопируйте шаблон конфигурации в файл `.env`:

```bash
cp .env.example .env
```

Откройте `.env` и укажите ваш API-ключ Groq (или OpenAI):

```env
OPENAI_API_KEY=ваш_ключ_groq
OPENAI_BASE_URL=https://api.groq.com/openai/v1
LLM_MODEL=openai/gpt-oss-120b
```

### 2. Запуск контейнеров

Выполните команду сборки и запуска:

```bash
docker compose up --build
```

После завершения инициализации сервисы доступны по адресам:
* Веб-интерфейс: [http://localhost:3000](http://localhost:3000)
* Документация API (Swagger): [http://localhost:8000/docs](http://localhost:8000/docs)
* База данных PostgreSQL: `localhost:5432`
* Redis: `localhost:6379`

### 3. Остановка сервисов

```bash
docker compose down
```

Для полной очистки вместе с томами данных используйте:

```bash
docker compose down -v
```

---

## Локальная разработка без Docker

Если требуется запустить компоненты локально для отладки:

### Предварительные требования
* Python 3.10+
* Node.js 18+ и npm
* FFmpeg (добавлен в системную переменную `PATH`)
* Локально запущенные PostgreSQL и Redis

### Бэкенд и воркер
```bash
# Создание виртуального окружения
python -m venv .venv
source .venv/bin/activate  # Для Linux/macOS
# .venv\Scripts\activate   # Для Windows PowerShell

# Установка зависимостей
pip install -r requirements.txt

# Запуск API-сервера
uvicorn main:app --reload --port 8000

# Запуск Celery воркера (в отдельном терминале)
# На Linux/macOS:
celery -A worker.celery_app worker --loglevel=info
# На Windows:
celery -A worker.celery_app worker --loglevel=info -P solo
```

### Фронтенд
```bash
cd frontend
npm install
npm run dev
```

---

## Использование API

### Создание задачи обработки видео
```http
POST /api/v1/process
Content-Type: application/json

{
  "youtube_url": "https://www.youtube.com/watch?v=..."
}
```

Ответ:
```json
{
  "task_id": "c1f72a6e-716c-4822-b52e-ec5f884a44b1",
  "status": "pending",
  "message": "Task created successfully"
}
```

### Проверка статуса задачи
```http
GET /api/v1/tasks/{task_id}
```

Статус последовательно переходит по этапам:
`pending` ➔ `downloading` ➔ `transcribing` ➔ `analyzing` ➔ `cutting` ➔ `completed`.

Для фронтенд-индикаторов используется лёгкий эндпоинт `GET /api/v1/tasks/{task_id}/status`; он возвращает процент `progress`, список `stages` и `error_message` при сбое.

### Получение отобранных фрагментов
```http
GET /api/v1/tasks/{task_id}/fragments
```

Пример ответа:
```json
{
  "task_id": "c1f72a6e-716c-4822-b52e-ec5f884a44b1",
  "status": "completed",
  "fragments": [
    {
      "id": 1,
      "start_time": 42.5,
      "end_time": 88.0,
      "duration": 45.5,
      "title": "Главный секрет продуктивности",
      "summary": "Спикер объясняет фундаментальную причину прокрастинации.",
      "hook": "Вы никогда не начнете действовать, пока думаете так...",
      "score": 9.5
    }
  ]
}
```

---

## Структура репозитория

```text
├── database.py          # Модели SQLAlchemy и инициализация таблиц
├── docker-compose.yml   # Конфигурация мультисервисного запуска
├── Dockerfile           # Образ бэкенда (Python, FFmpeg, Deno, yt-dlp)
├── llm.py               # Логика работы с LLM API и алгоритм fallback
├── main.py              # Эндпоинты FastAPI и CORS-настройки
├── media.py             # Скачивание исходного видео, извлечение WAV и нарезка через FFmpeg
├── smart_crop.py        # MediaPipe/OpenCV, выбор лица и сглаживание окна Smart Crop
├── requirements.txt     # Python-зависимости проекта
├── transcription.py     # Модуль транскрибации речи через Faster-Whisper
├── worker.py            # Очередь задач Celery и конвейер обработки
├── frontend/            # Клиентская часть на Next.js 14
│   ├── app/             # Страницы и компоненты интерфейса
│   ├── Dockerfile       # Образ сборки фронтенда
│   ├── package.json     # Скрипты и зависимости Node.js
│   └── tailwind.config  # Стилизация интерфейса
├── .env.example         # Пример конфигурации окружения
└── .gitignore           # Правила исключения временных файлов и секретов
```

---
