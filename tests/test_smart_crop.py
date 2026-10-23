import unittest

from smart_crop import _ema, _make_x_expression, build_smart_crop_filter


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


if __name__ == "__main__":
    unittest.main()
