import numpy as np
import unittest

from smart_crop import (
    _active_speaker_in_scene,
    _ema,
    _make_step_x_expression,
    _make_x_expression,
    build_smart_crop_filter,
    calculate_mar,
    detect_scene_cut_histogram,
)


class MockPoint:
    def __init__(self, x: float, y: float):
        self.x = x
        self.y = y


class SmartCropTests(unittest.TestCase):
    def test_ema_smooths_window_movement(self):
        values = _ema([0.0, 100.0, 100.0], alpha=0.5)
        self.assertEqual(values, [0.0, 50.0, 75.0])

    def test_expression_contains_time_based_interpolation(self):
        expression = _make_x_expression([(0.0, 100.0), (0.5, 200.0)])
        self.assertIn("lt(t\\,0.5)", expression)
        self.assertIn("iw-ih*9/16", expression)

    def test_missing_source_uses_safe_center_crop(self):
        result = build_smart_crop_filter("/path/that/does/not/exist.mp4", 0.0, 10.0)
        self.assertEqual(
            result,
            "crop=w=ih*9/16:h=ih:x=(iw-ih*9/16)/2:y=0,scale=1080:1920",
        )

    def test_calculate_mar_scale_invariance(self):
        """Проверка нормализации MAR: масштабирование лица (приближение к камере) не меняет показатель."""
        # 1. Лицо на стандартном расстоянии:
        # Верхняя губа 13, нижняя 14; левый угол рта 61, правый угол 291
        landmarks_normal = {
            13: MockPoint(0.5, 0.50),
            14: MockPoint(0.5, 0.55),   # высота = 0.05
            61: MockPoint(0.40, 0.525),
            291: MockPoint(0.60, 0.525),  # ширина = 0.20
        }
        mar_normal = calculate_mar(landmarks_normal)
        self.assertAlmostEqual(mar_normal, 0.05 / 0.20, places=3)

        # 2. Лицо приближено к камере (масштаб x2):
        landmarks_close = {
            13: MockPoint(0.5, 0.45),
            14: MockPoint(0.5, 0.55),   # высота = 0.10 (x2)
            61: MockPoint(0.30, 0.50),
            291: MockPoint(0.70, 0.50),  # ширина = 0.40 (x2)
        }
        mar_close = calculate_mar(landmarks_close)
        # Отношение высота / ширина обязано оставаться инвариантным:
        self.assertAlmostEqual(mar_normal, mar_close, places=3)

    def test_calculate_mar_zero_division_guard(self):
        """Защита от деления на ноль при нулевой ширине рта."""
        landmarks_zero = {
            13: MockPoint(0.5, 0.5),
            14: MockPoint(0.5, 0.5),
            61: MockPoint(0.5, 0.5),
            291: MockPoint(0.5, 0.5),
        }
        self.assertEqual(calculate_mar(landmarks_zero), 0.0)

    def test_detect_scene_cut_histogram(self):
        """Детекция смены планов через корреляцию HSV гистограмм в OpenCV."""
        # Два идентичных кадра:
        frame_a = np.zeros((240, 320, 3), dtype=np.uint8)
        frame_a[50:150, 50:150] = (255, 100, 50)
        frame_same = frame_a.copy()

        is_cut_same, score_same = detect_scene_cut_histogram(frame_a, frame_same)
        self.assertFalse(is_cut_same)
        self.assertAlmostEqual(score_same, 1.0, places=2)

        # Кадр с контрастной сменой сцены (яркий зеленый/красный):
        frame_b = np.full((240, 320, 3), 240, dtype=np.uint8)
        frame_b[0:240, 0:160] = (0, 255, 0)
        frame_b[0:240, 160:320] = (0, 0, 255)

        is_cut_diff, score_diff = detect_scene_cut_histogram(frame_a, frame_b, threshold=0.55)
        self.assertTrue(is_cut_diff)
        self.assertLess(score_diff, 0.55)

    def test_compact_step_x_expression_length(self):
        """Ступенчатый фильтр не превышает лимит длины в 150 символов при любых монтажных планах."""
        # 3 монтажных плана со склейками
        scenes = [
            (0.0, 12.4, 210.0),
            (12.4, 25.1, 580.0),
            (25.1, 40.0, 340.0),
        ]
        expr = _make_step_x_expression(scenes)
        filter_str = f"crop=w=ih*9/16:h=ih:x='{expr}':y=0,scale=1080:1920"

        self.assertLessEqual(len(filter_str), 150)
        # Проверяем наличие условий мгновенной склейки:
        self.assertIn("if(lt(t\\,12.4)", expr)
        self.assertIn("if(lt(t\\,25.1)", expr)

    def test_active_speaker_in_scene_selection(self):
        """Выбор активного спикера индивидуально для монтажного плана по площади и MAR."""
        # Два спикера в одной сцене: спикер 1 говорит (высокая вариативность MAR), спикер 2 молчит
        detections = [
            {"time": 0.0, "center_x": 0.25, "center_y": 0.5, "area": 0.08, "mar": 0.05},
            {"time": 0.4, "center_x": 0.25, "center_y": 0.5, "area": 0.08, "mar": 0.32},
            {"time": 0.8, "center_x": 0.25, "center_y": 0.5, "area": 0.08, "mar": 0.06},
            {"time": 0.0, "center_x": 0.75, "center_y": 0.5, "area": 0.08, "mar": 0.05},
            {"time": 0.4, "center_x": 0.75, "center_y": 0.5, "area": 0.08, "mar": 0.05},
            {"time": 0.8, "center_x": 0.75, "center_y": 0.5, "area": 0.08, "mar": 0.05},
        ]
        # Frame 1920x1080, crop_width = 1080 * 9 / 16 = 607.5, max_x = 1312.5
        frame_width = 1920
        crop_width = 607.5
        max_x = 1312.5

        chosen_x = _active_speaker_in_scene(detections, frame_width, crop_width, max_x)
        # Говорящий спикер на x=0.25: 0.25 * 1920 - 303.75 = 176.25
        self.assertAlmostEqual(chosen_x, 176.25, places=1)

    def test_detect_scene_cut_luminance_black_to_white(self):
        """Проверка детекции смены плана при резкой смене освещенности и яркости (черный vs белый кадр)."""
        frame_black = np.zeros((200, 200, 3), dtype=np.uint8)
        frame_white = np.full((200, 200, 3), 255, dtype=np.uint8)

        is_cut, score = detect_scene_cut_histogram(frame_black, frame_white, threshold=0.55)
        self.assertTrue(is_cut, "Смена черного кадра на белый обязана определяться как смена плана")
        self.assertLess(score, 0.55)

    def test_step_x_expression_preserves_dominant_coordinate(self):
        """При объединении короткого плана с длинным сохраняется координата доминирующего плана."""
        # 1-секундный план на x=100 и 25-секундный план на x=800
        scenes = [
            (0.0, 1.0, 100.0),
            (1.0, 26.0, 800.0),
            (26.0, 28.0, 200.0),
            (28.0, 60.0, 850.0),
            (60.0, 61.0, 120.0),
        ]
        expr = _make_step_x_expression(scenes, max_filter_length=150)
        filter_str = f"crop=w=ih*9/16:h=ih:x='{expr}':y=0,scale=1080:1920"

        self.assertLessEqual(len(filter_str), 150)
        # Координата 800 обязана остаться, а не замениться на 100
        self.assertIn("800", expr)

    def test_step_x_expression_handles_shortest_last_segment(self):
        """Короткий фрагмент в самом конце видео корректно объединяется с предыдущим планом."""
        scenes = [
            (0.0, 20.0, 300.0),
            (20.0, 40.0, 700.0),
            (40.0, 59.5, 450.0),
            (59.5, 60.0, 100.0),  # Самый короткий фрагмент (0.5 сек) в конце
        ]
        expr = _make_step_x_expression(scenes, max_filter_length=150)
        filter_str = f"crop=w=ih*9/16:h=ih:x='{expr}':y=0,scale=1080:1920"

        self.assertLessEqual(len(filter_str), 150)
        # План 450 доминирует над 0.5-секундным планом 100
        self.assertIn("450", expr)

    def test_step_x_expression_length_guarantee_with_ten_cuts(self):
        """Гарантия длины фильтра до 150 символов даже при 10 частых монтажных склейках."""
        scenes = [(float(i * 3), float((i + 1) * 3), float(100 + i * 50)) for i in range(10)]
        expr = _make_step_x_expression(scenes, max_filter_length=150)
        filter_str = f"crop=w=ih*9/16:h=ih:x='{expr}':y=0,scale=1080:1920"

        self.assertLessEqual(len(filter_str), 150)


if __name__ == "__main__":
    unittest.main()
