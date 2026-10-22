import os
import sys
import unittest
from pathlib import Path

# Ensure repo root is on sys.path
REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

# Set test environment before importing app
TEST_MEDIA_DIR = REPO_ROOT / "tmp" / "test_media"
TEST_MEDIA_DIR.mkdir(parents=True, exist_ok=True)
os.environ["SHARED_MEDIA_DIR"] = str(TEST_MEDIA_DIR)
os.environ["DATABASE_URL"] = f"sqlite:///{REPO_ROOT / 'tmp' / 'test_shorts.db'}"

from fastapi.testclient import TestClient
from database import Base, SessionLocal, ShortFragment, Transcript, VideoTask, engine, init_db
from llm import _align_fragments_to_words, _fallback_extract_moments, find_shorts_moments
import main


class TestCard1ViralityPromptAndScoring(unittest.TestCase):
    """Тесты Карточки 1: Алгоритм интересности, Virality Score 1–100 и устранение срезания фраз."""

    def test_fallback_moments_virality_score_range(self):
        sample_words = [
            {"word": "Привет,", "start": 0.0, "end": 0.5},
            {"word": "сегодня", "start": 0.52, "end": 0.95},
            {"word": "мы", "start": 1.0, "end": 1.2},
            {"word": "разберем", "start": 1.22, "end": 1.7},
            {"word": "секреты", "start": 1.72, "end": 2.15},
            {"word": "вирусных", "start": 2.18, "end": 2.65},
            {"word": "роликов.", "start": 2.68, "end": 3.1},
        ]
        text = "Привет, сегодня мы разберем секреты вирусных роликов."
        fragments = _fallback_extract_moments(text, sample_words)

        self.assertGreaterEqual(len(fragments), 1)
        for frag in fragments:
            score = frag.get("virality_score")
            self.assertIsInstance(score, int)
            self.assertGreaterEqual(score, 1)
            self.assertLessEqual(score, 100)
            self.assertTrue(bool(frag.get("hook_reason")), "hook_reason обязан быть заполнен")
            self.assertTrue(bool(frag.get("first_words")), "first_words обязан быть заполнен")
            self.assertTrue(bool(frag.get("last_words")), "last_words обязан быть заполнен")
            self.assertIn("internal_criticism", frag)

    def test_align_fragments_to_words_snapping(self):
        """Проверка привязки неточных таймкодов к пословным границам Faster-Whisper без срезания речи."""
        words = [
            {"word": "Главная", "start": 10.15, "end": 10.65},
            {"word": "мысль", "start": 10.70, "end": 11.20},
            {"word": "состоит", "start": 11.25, "end": 11.80},
            {"word": "в", "start": 11.82, "end": 11.95},
            {"word": "этом.", "start": 11.98, "end": 12.45},
            {"word": "Конечный", "start": 25.10, "end": 25.60},
            {"word": "вывод.", "start": 25.65, "end": 26.20},
        ]
        imprecise_fragments = [
            {
                "title": "Тестовый фрагмент",
                "start_time": 10.0,  # Неточный старт от LLM
                "end_time": 26.0,    # Неточный конец от LLM
                "virality_score": 88,
                "hook_reason": "Сильный хук",
                "first_words": "Главная мысль",
                "last_words": "Конечный вывод",
            }
        ]

        aligned = _align_fragments_to_words(imprecise_fragments, words)
        self.assertEqual(len(aligned), 1)
        frag = aligned[0]

        # Старт выравнивается по слову 10.15 с буфером -50мс: 10.10
        self.assertAlmostEqual(frag["start_time"], 10.10, places=2)
        # Конец выравнивается по последнему слову 26.20 с буфером +100мс: 26.30
        self.assertAlmostEqual(frag["end_time"], 26.30, places=2)
        self.assertGreater(frag["duration"], 15.0)

    def test_empty_transcript_handling(self):
        result = find_shorts_moments("", [])
        self.assertEqual(result, [])

    def test_align_fragments_edge_cases(self):
        """Граничные условия пословной синхронизации таймкодов."""
        # 1. Пустой список слов: фрагменты не меняются
        frags = [{"title": "F1", "start_time": 5.0, "end_time": 20.0}]
        self.assertEqual(_align_fragments_to_words(frags, []), frags)

        # 2. Пустой список фрагментов
        words = [{"word": "тест", "start": 1.0, "end": 2.0}]
        self.assertEqual(_align_fragments_to_words([], words), [])

        # 3. Слова далеко от границ (более 4 секунд): таймкод сохраняется
        frags = [{"title": "F2", "start_time": 50.0, "end_time": 70.0}]
        aligned = _align_fragments_to_words(frags, words)
        self.assertEqual(aligned[0]["start_time"], 50.0)

        # 4. Длительность более 65 секунд обрезается до 60 секунд
        frags = [{"title": "F3", "start_time": 10.0, "end_time": 90.0}]
        aligned = _align_fragments_to_words(frags, words)
        self.assertEqual(aligned[0]["duration"], 60.0)

        # 5. Старт в 0.02 секунды не уходит в отрицательное время из-за буфера -50мс
        words_zero = [{"word": "Старт", "start": 0.02, "end": 0.5}]
        frags_zero = [{"title": "F4", "start_time": 0.02, "end_time": 15.0}]
        aligned_zero = _align_fragments_to_words(frags_zero, words_zero)
        self.assertGreaterEqual(aligned_zero[0]["start_time"], 0.0)

    def test_zero_em_dashes_in_llm_module(self):
        llm_file = REPO_ROOT / "llm.py"
        content = llm_file.read_text(encoding="utf-8")
        self.assertNotIn("\u2014", content, "В llm.py обнаружено запрещенное длинное тире")


class TestCard9PipelinePolling(unittest.TestCase):
    """Тесты Карточки 9: Опрос статусов этапов обработки видео через REST API / Polling."""

    @classmethod
    def setUpClass(cls):
        init_db()
        cls.client = TestClient(main.app)

    def setUp(self):
        self.db = SessionLocal()

    def tearDown(self):
        self.db.close()

    def test_pipeline_stages_and_progress_flow(self):
        """Проверка динамики статусов, шагов и прогресса 0–100%."""
        task = VideoTask(
            session_id="test-session-1",
            youtube_url="https://www.youtube.com/watch?v=dQw4w9WgXcQ",
            status="downloading",
            current_step="downloading",
            progress=15,
        )
        self.db.add(task)
        self.db.commit()
        self.db.refresh(task)

        # 1. Этап downloading
        resp = self.client.get(f"/api/v1/tasks/{task.id}")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["status"], "downloading")
        self.assertEqual(data["progress"], 15)
        self.assertEqual(data["current_step"], "downloading")
        self.assertIn("Загрузка", data["step_label"])
        self.assertEqual(len(data["stages"]), 4)
        self.assertEqual(data["stages"][0]["status"], "in_progress")
        self.assertEqual(data["stages"][1]["status"], "pending")

        # 2. Этап transcribing
        task.status = "transcribing"
        task.current_step = "transcribing"
        task.progress = 40
        self.db.commit()

        resp = self.client.get(f"/api/v1/tasks/{task.id}/status")
        self.assertEqual(resp.status_code, 200)
        st_data = resp.json()
        self.assertEqual(st_data["progress"], 40)
        self.assertEqual(st_data["current_step"], "transcribing")
        self.assertEqual(st_data["stages"][0]["status"], "completed")
        self.assertEqual(st_data["stages"][1]["status"], "in_progress")

        # 3. Этап analyzing
        task.status = "analyzing"
        task.current_step = "analyzing"
        task.progress = 65
        self.db.commit()

        resp = self.client.get(f"/api/v1/tasks/{task.id}/status")
        self.assertEqual(resp.json()["progress"], 65)
        self.assertEqual(resp.json()["stages"][1]["status"], "completed")
        self.assertEqual(resp.json()["stages"][2]["status"], "in_progress")

        # 4. Этап cutting
        task.status = "cutting"
        task.current_step = "cutting"
        task.progress = 85
        frag = ShortFragment(
            task_id=task.id,
            title="Тестовый клип",
            start_time=5.0,
            end_time=25.0,
            duration=20.0,
            virality_score=85,
            hook_reason="Хук",
            status="ready",
        )
        self.db.add(frag)
        self.db.commit()

        resp = self.client.get(f"/api/v1/tasks/{task.id}")
        data = resp.json()
        self.assertEqual(data["progress"], 85)
        self.assertEqual(data["clips_summary"]["total"], 1)
        self.assertEqual(data["clips_summary"]["ready"], 1)

        # 5. Этап completed
        task.status = "completed"
        task.current_step = "completed"
        task.progress = 100
        self.db.commit()

        resp = self.client.get(f"/api/v1/tasks/{task.id}/status")
        st_data = resp.json()
        self.assertEqual(st_data["progress"], 100)
        self.assertTrue(st_data["is_completed"])
        self.assertFalse(st_data["is_failed"])
        for stage in st_data["stages"]:
            self.assertEqual(stage["status"], "completed")

    def test_pipeline_error_state(self):
        task = VideoTask(
            session_id="test-session-err",
            youtube_url="https://www.youtube.com/watch?v=error",
            status="error",
            current_step="transcribing",
            error_message="Faster-Whisper CUDA out of memory",
        )
        self.db.add(task)
        self.db.commit()

        resp = self.client.get(f"/api/v1/tasks/{task.id}/status")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertTrue(data["is_failed"])
        self.assertIn("Faster-Whisper", data["error_message"])
        self.assertEqual(data["stages"][1]["status"], "failed")

    def test_task_not_found(self):
        resp = self.client.get("/api/v1/tasks/999999")
        self.assertEqual(resp.status_code, 404)
        resp_status = self.client.get("/api/v1/tasks/999999/status")
        self.assertEqual(resp_status.status_code, 404)
        resp_frags = self.client.get("/api/v1/tasks/999999/fragments")
        self.assertEqual(resp_frags.status_code, 404)

    def test_pipeline_all_stages_error_propagation(self):
        """Проверка корректной индикации сбоя на каждом из 4 этапов пайплайна."""
        stages_configs = [
            ("downloading", 0),
            ("transcribing", 1),
            ("analyzing", 2),
            ("cutting", 3),
        ]
        for step_name, failed_idx in stages_configs:
            task = VideoTask(
                session_id=f"test-err-{step_name}",
                youtube_url="https://www.youtube.com/watch?v=err",
                status="error",
                current_step=step_name,
                error_message=f"Ошибка на шаге {step_name}",
            )
            self.db.add(task)
            self.db.commit()

            resp = self.client.get(f"/api/v1/tasks/{task.id}/status")
            self.assertEqual(resp.status_code, 200)
            data = resp.json()
            self.assertTrue(data["is_failed"])
            self.assertEqual(data["stages"][failed_idx]["status"], "failed")
            for prev_i in range(failed_idx):
                self.assertEqual(data["stages"][prev_i]["status"], "completed")
            for next_i in range(failed_idx + 1, 4):
                self.assertEqual(data["stages"][next_i]["status"], "pending")

    def test_pipeline_error_step_deduction_by_progress(self):
        """Отказоустойчивое определение этапа сбоя по прогрессу, если current_step равен 'error'."""
        task = VideoTask(
            session_id="test-err-deduce",
            youtube_url="https://www.youtube.com/watch?v=err",
            status="error",
            current_step="error",
            progress=65,
            error_message="Groq Cloud timeout",
        )
        self.db.add(task)
        self.db.commit()

        resp = self.client.get(f"/api/v1/tasks/{task.id}/status")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertTrue(data["is_failed"])
        self.assertEqual(data["stages"][0]["status"], "completed")
        self.assertEqual(data["stages"][1]["status"], "completed")
        self.assertEqual(data["stages"][2]["status"], "failed")
        self.assertEqual(data["stages"][3]["status"], "pending")

    def test_pipeline_pending_state(self):
        """Проверка начального состояния задачи в очереди ожидания."""
        task = VideoTask(
            session_id="test-pending",
            youtube_url="https://www.youtube.com/watch?v=pending",
            status="pending",
            current_step="pending",
            progress=0,
        )
        self.db.add(task)
        self.db.commit()

        resp = self.client.get(f"/api/v1/tasks/{task.id}/status")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["status"], "pending")
        self.assertEqual(data["progress"], 5)
        self.assertFalse(data["is_completed"])
        self.assertFalse(data["is_failed"])
        for stage in data["stages"]:
            self.assertEqual(stage["status"], "pending")

    def test_pipeline_polling_metadata(self):
        """Проверка наличия полных метаданных задачи (youtube_url, created_at, updated_at)."""
        task = VideoTask(
            session_id="test-meta",
            youtube_url="https://www.youtube.com/watch?v=metadata123",
            status="downloading",
            current_step="downloading",
            progress=15,
        )
        self.db.add(task)
        self.db.commit()
        self.db.refresh(task)

        resp = self.client.get(f"/api/v1/tasks/{task.id}/status")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["youtube_url"], task.youtube_url)
        self.assertIn("created_at", data)
        self.assertIn("updated_at", data)

    def test_pipeline_error_step_label(self):
        """Проверка информативного описания сбоя в step_label при возникновении ошибки."""
        task = VideoTask(
            session_id="test-err-label",
            youtube_url="https://www.youtube.com/watch?v=errlabel",
            status="error",
            current_step="transcribing",
            progress=40,
            error_message="Whisper failure",
        )
        self.db.add(task)
        self.db.commit()

        resp = self.client.get(f"/api/v1/tasks/{task.id}/status")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertTrue(data["is_failed"])
        self.assertIn("Сбой на этапе", data["step_label"])
        self.assertIn("Транскрибация", data["step_label"])


class TestCard6ClipsAndMediaContract(unittest.TestCase):
    """Тесты Карточки 6: Контракт DTO карточек клипов и прямое скачивание готового MP4."""

    @classmethod
    def setUpClass(cls):
        init_db()
        cls.client = TestClient(main.app)

    def setUp(self):
        self.db = SessionLocal()
        self.task = VideoTask(
            session_id="test-session-clips",
            youtube_url="https://www.youtube.com/watch?v=sample123",
            status="completed",
            current_step="completed",
            progress=100,
        )
        self.db.add(self.task)
        self.db.commit()
        self.db.refresh(self.task)

        self.fragment = ShortFragment(
            task_id=self.task.id,
            title="Секрет алгоритмов рекомендаций",
            start_time=12.5,
            end_time=45.2,
            duration=32.7,
            virality_score=92,
            hook_reason="Острый парадокс в первые 2 секунды видео",
            internal_criticism="Скептик отсек вступительные вздохи",
            first_words="Секрет заключается в",
            last_words="это дает максимальный охват",
            reasoning="Острый парадокс",
            summary="Краткая суть фрагмента",
            video_path=f"/media/clips/fragment_test.mp4",
            status="ready",
        )
        self.db.add(self.fragment)
        self.db.commit()
        self.db.refresh(self.fragment)

    def tearDown(self):
        self.db.close()

    def test_fragments_list_dto_contract_for_oleg(self):
        """Проверка полей DTO карточки клипа для фронтенда Next.js Олега."""
        resp = self.client.get(f"/api/v1/tasks/{self.task.id}/fragments")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["task_id"], self.task.id)
        self.assertEqual(data["count"], 1)

        frag_dto = data["fragments"][0]
        # Поля скоринга и хука (Карточка 6)
        self.assertEqual(frag_dto["virality_score"], 92)
        self.assertEqual(frag_dto["hook_reason"], "Острый парадокс в первые 2 секунды видео")
        self.assertEqual(frag_dto["internal_criticism"], "Скептик отсек вступительные вздохи")
        self.assertEqual(frag_dto["first_words"], "Секрет заключается в")
        self.assertEqual(frag_dto["last_words"], "это дает максимальный охват")

        # Прямые ссылки на скачивание и стриминг
        self.assertEqual(frag_dto["download_url"], f"/api/v1/fragments/{self.fragment.id}/download")
        self.assertEqual(frag_dto["stream_url"], f"/media/clips/fragment_{self.fragment.id}.mp4")

        # Таймкоды и форматирование (тире диапазона – en-dash \u2013)
        self.assertEqual(frag_dto["effective_start_time"], 12.5)
        self.assertEqual(frag_dto["effective_end_time"], 45.2)
        self.assertIn("\u2013", frag_dto["formatted_timecode"])

        # Обратная совместимость с типами Олега
        self.assertIn("reasoning", frag_dto)
        self.assertIn("summary", frag_dto)
        self.assertIn("duration", frag_dto)

    def test_single_fragment_detail_endpoint(self):
        resp = self.client.get(f"/api/v1/fragments/{self.fragment.id}")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["id"], self.fragment.id)
        self.assertEqual(data["virality_score"], 92)
        self.assertIn("download_url", data)

    def test_adjust_fragment_timecodes_success(self):
        resp = self.client.patch(
            f"/api/v1/fragments/{self.fragment.id}/adjust",
            json={"adjusted_start_time": 15.0, "adjusted_end_time": 40.0},
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["adjusted_start_time"], 15.0)
        self.assertEqual(data["adjusted_end_time"], 40.0)
        self.assertEqual(data["duration"], 25.0)
        self.assertEqual(data["status"], "retrim_pending")
        self.assertIn("download_url", data)

    def test_adjust_fragment_timecodes_validation(self):
        # Длительность меньше 5 секунд (4.99)
        resp = self.client.patch(
            f"/api/v1/fragments/{self.fragment.id}/adjust",
            json={"adjusted_start_time": 10.0, "adjusted_end_time": 14.99},
        )
        self.assertEqual(resp.status_code, 422)

        # Граничное значение: ровно 5.0 секунд
        resp_valid_min = self.client.patch(
            f"/api/v1/fragments/{self.fragment.id}/adjust",
            json={"adjusted_start_time": 10.0, "adjusted_end_time": 15.0},
        )
        self.assertEqual(resp_valid_min.status_code, 200)

        # Длительность больше 65 секунд (65.01)
        resp = self.client.patch(
            f"/api/v1/fragments/{self.fragment.id}/adjust",
            json={"adjusted_start_time": 0.0, "adjusted_end_time": 65.01},
        )
        self.assertEqual(resp.status_code, 422)

        # Граничное значение: ровно 65.0 секунд
        resp_valid_max = self.client.patch(
            f"/api/v1/fragments/{self.fragment.id}/adjust",
            json={"adjusted_start_time": 0.0, "adjusted_end_time": 65.0},
        )
        self.assertEqual(resp_valid_max.status_code, 200)

        # Отрицательное время старта
        resp = self.client.patch(
            f"/api/v1/fragments/{self.fragment.id}/adjust",
            json={"adjusted_start_time": -1.0, "adjusted_end_time": 20.0},
        )
        self.assertEqual(resp.status_code, 422)

        # Конец раньше начала
        resp = self.client.patch(
            f"/api/v1/fragments/{self.fragment.id}/adjust",
            json={"adjusted_start_time": 30.0, "adjusted_end_time": 20.0},
        )
        self.assertEqual(resp.status_code, 422)

        # Несуществующий фрагмент
        resp = self.client.patch(
            "/api/v1/fragments/999999/adjust",
            json={"adjusted_start_time": 10.0, "adjusted_end_time": 25.0},
        )
        self.assertEqual(resp.status_code, 404)

    def test_missing_fragment_endpoints_404(self):
        resp_detail = self.client.get("/api/v1/fragments/999999")
        self.assertEqual(resp_detail.status_code, 404)

        resp_dl = self.client.get("/api/v1/fragments/999999/download")
        self.assertEqual(resp_dl.status_code, 404)

    def test_dto_contract_defaults_and_null_handling(self):
        """Проверка безопасной сериализации DTO при незаполненных необязательных полях."""
        frag = ShortFragment(
            task_id=self.task.id,
            title="Минимальный фрагмент",
            start_time=0.0,
            end_time=15.0,
            duration=15.0,
            virality_score=1,
            hook_reason=None,
            internal_criticism=None,
            first_words=None,
            last_words=None,
            reasoning="Запасное объяснение",
            summary=None,
            status="pending",
        )
        self.db.add(frag)
        self.db.commit()
        self.db.refresh(frag)

        resp = self.client.get(f"/api/v1/fragments/{frag.id}")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["virality_score"], 1)
        self.assertEqual(data["hook_reason"], "Запасное объяснение")
        self.assertEqual(data["internal_criticism"], "")
        self.assertEqual(data["first_words"], "")
        self.assertEqual(data["last_words"], "")
        self.assertEqual(data["summary"], "")
        self.assertFalse(data["has_video"])
        self.assertIn("\u2013", data["formatted_timecode"])

    def test_download_existing_fragment(self):
        # Создаем тестовый файл MP4
        fake_file = TEST_MEDIA_DIR / f"fragment_{self.fragment.id}.mp4"
        fake_file.write_bytes(b"\x00\x00\x00\x18ftypmp42\x00\x00\x00\x00mp42mp41")

        resp = self.client.get(f"/api/v1/fragments/{self.fragment.id}/download")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.headers.get("content-type"), "video/mp4")
        self.assertIn("attachment", resp.headers.get("content-disposition", ""))
        self.assertIn(f"shorts_{self.fragment.id}.mp4", resp.headers.get("content-disposition", ""))

    def test_stream_video_clip_endpoint(self):
        fake_file = TEST_MEDIA_DIR / "fragment_stream_test.mp4"
        fake_file.write_bytes(b"\x00\x00\x00\x18ftypmp42\x00\x00\x00\x00mp42mp41")

        resp = self.client.get("/media/clips/fragment_stream_test.mp4")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.headers.get("content-type"), "video/mp4")

        # Несуществующий клип без привязки к БД
        resp_missing = self.client.get("/media/clips/non_existent_random_file.mp4")
        self.assertEqual(resp_missing.status_code, 404)

    def test_youtube_url_validation(self):
        valid_urls = [
            "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
            "https://youtu.be/dQw4w9WgXcQ",
            "https://www.youtube.com/shorts/dQw4w9WgXcQ",
        ]
        for u in valid_urls:
            resp = self.client.post("/api/v1/process", json={"youtube_url": u})
            self.assertEqual(resp.status_code, 202, f"URL {u} должен быть принят")
            self.assertIn("task_id", resp.json())
            self.assertIn("celery_task_id", resp.json())

        invalid_urls = [
            "https://vimeo.com/123456",
            "https://rutube.ru/video/123",
        ]
        for u in invalid_urls:
            resp = self.client.post("/api/v1/process", json={"youtube_url": u})
            self.assertEqual(resp.status_code, 422, f"URL {u} должен быть отклонен")

    def test_backward_compatibility_of_all_task_fields(self):
        """Проверка строгой обратной совместимости с существующим кодом страницы Олега."""
        resp = self.client.get(f"/api/v1/tasks/{self.task.id}")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()

        # Поля, которые напрямую читает frontend/app/page.tsx Олега:
        # data.id, data.status, data.youtube_url, data.fragments_count
        self.assertEqual(data["id"], self.task.id)
        self.assertEqual(data["status"], "completed")
        self.assertEqual(data["youtube_url"], self.task.youtube_url)
        self.assertIsInstance(data["fragments_count"], int)

        # Новые поля Александра:
        self.assertIn("progress", data)
        self.assertIn("current_step", data)
        self.assertIn("step_label", data)
        self.assertIn("stages", data)
        self.assertIn("clips_summary", data)
        self.assertIn("clips", data)
        self.assertIn("created_at", data)
        self.assertIn("updated_at", data)

    def test_youtube_preview_url_generation_variants(self):
        """Проверка корректной генерации ссылок предпросмотра YouTube для разных форматов URL."""
        from main import _build_youtube_preview_url

        # 1. Обычная ссылка watch?v=
        url1 = "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
        p1 = _build_youtube_preview_url(url1, 25.4)
        self.assertEqual(p1, "https://www.youtube.com/watch?v=dQw4w9WgXcQ&t=25s")

        # 2. Короткая ссылка youtu.be/
        url2 = "https://youtu.be/dQw4w9WgXcQ"
        p2 = _build_youtube_preview_url(url2, 10.0)
        self.assertEqual(p2, "https://www.youtube.com/watch?v=dQw4w9WgXcQ&t=10s")

        # 3. Ссылка на Shorts
        url3 = "https://www.youtube.com/shorts/dQw4w9WgXcQ"
        p3 = _build_youtube_preview_url(url3, 0.0)
        self.assertEqual(p3, "https://www.youtube.com/watch?v=dQw4w9WgXcQ&t=0s")

        # 4. Пустая ссылка
        self.assertIsNone(_build_youtube_preview_url(None, 10.0))

    def test_stream_video_clip_path_traversal_protection(self):
        """Проверка отклонения попыток path traversal и некорректных расширений."""
        # Попытка выхода из директории
        resp = self.client.get("/media/clips/..%2F..%2Fsecret.mp4")
        self.assertIn(resp.status_code, [400, 404])

        # Некорректное расширение
        resp_ext = self.client.get("/media/clips/test_file.sh")
        self.assertEqual(resp_ext.status_code, 400)

    def test_clips_dto_timecode_en_dash_format(self):
        """Проверка соответствия таймкода правилу числового диапазона с коротким тире без пробелов."""
        resp = self.client.get(f"/api/v1/fragments/{self.fragment.id}")
        self.assertEqual(resp.status_code, 200)
        tc = resp.json()["formatted_timecode"]
        self.assertIn("\u2013", tc)
        self.assertNotIn(" ", tc, "Диапазон таймкода не должен содержать пробелы вокруг тире")


class TestTypographyCompliance(unittest.TestCase):
    """Строгая проверка запрета длинных тире (\u2014) в русском тексте и коде проекта."""

    def test_zero_em_dashes_in_all_repo_code(self):
        em_dash = "\u2014"
        py_files = [
            f for f in REPO_ROOT.rglob("*.py")
            if ".venv" not in f.parts and "__pycache__" not in f.parts
        ]
        violations = []
        for f in py_files:
            content = f.read_text(encoding="utf-8", errors="ignore")
            if em_dash in content:
                violations.append(str(f))

        self.assertEqual(
            violations,
            [],
            f"Обнаружены запрещенные длинные тире (\\u2014) в следующих файлах: {violations}"
        )

    def test_zero_em_dashes_in_setup_guide(self):
        setup_file = REPO_ROOT / "SETUP.md"
        if setup_file.exists():
            content = setup_file.read_text(encoding="utf-8", errors="ignore")
            self.assertNotIn("\u2014", content, "В SETUP.md обнаружено запрещенное длинное тире")


if __name__ == "__main__":
    unittest.main()
