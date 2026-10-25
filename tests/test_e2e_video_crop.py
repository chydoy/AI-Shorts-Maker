import os
import shutil
import subprocess
import tempfile
import unittest
import numpy as np

try:
    import cv2
    HAS_CV2 = True
except ImportError:
    HAS_CV2 = False

try:
    import imageio_ffmpeg
    FFMPEG_EXE = imageio_ffmpeg.get_ffmpeg_exe()
except Exception:
    FFMPEG_EXE = shutil.which("ffmpeg")

from smart_crop import (
    _make_step_x_expression,
    detect_scene_cut_histogram,
)


class TestE2EVideoCrop(unittest.TestCase):
    """End-to-end verification of scene detection, step crop filter, and real FFmpeg rendering."""

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    @unittest.skipUnless(HAS_CV2, "OpenCV is required for this test")
    def test_opencv_histogram_and_ffmpeg_crop_execution(self):
        # 1. Create a 3-second synthetic video with a scene cut at 1.5s
        video_path = os.path.join(self.temp_dir, "input_test.mp4")
        width, height = 640, 360
        fps = 20
        total_frames = 60  # 3 seconds

        fourcc = cv2.VideoWriter_fourcc(*"mp4v")
        out = cv2.VideoWriter(video_path, fourcc, fps, (width, height))

        frame_scene1 = np.zeros((height, width, 3), dtype=np.uint8)
        frame_scene1[:, :] = (180, 50, 40)  # Blueish background
        cv2.circle(frame_scene1, (160, 180), 50, (0, 0, 255), -1)  # Left subject

        frame_scene2 = np.zeros((height, width, 3), dtype=np.uint8)
        frame_scene2[:, :] = (30, 160, 40)  # Greenish background
        cv2.circle(frame_scene2, (480, 180), 50, (0, 255, 255), -1)  # Right subject

        for i in range(total_frames):
            if i < 30:
                out.write(frame_scene1)
            else:
                out.write(frame_scene2)
        out.release()

        self.assertTrue(os.path.exists(video_path))

        # 2. Verify histogram cut detection between scene 1 and scene 2
        is_cut, score = detect_scene_cut_histogram(frame_scene1, frame_scene2)
        self.assertTrue(is_cut)
        self.assertLess(score, 0.55)

        # 3. Create step crop filter for the two scenes
        crop_width = height * 9.0 / 16.0  # 202.5
        max_x = width - crop_width        # 437.5
        x_scene1 = max(0.0, min(160 - crop_width / 2.0, max_x))
        x_scene2 = max(0.0, min(480 - crop_width / 2.0, max_x))

        scene_segments = [
            (0.0, 1.5, x_scene1),
            (1.5, 3.0, x_scene2),
        ]
        x_expr = _make_step_x_expression(scene_segments)
        filter_str = f"crop=w=ih*9/16:h=ih:x='{x_expr}':y=0,scale=1080:1920"

        self.assertLessEqual(len(filter_str), 150)
        self.assertIn("lt(t\\,1.5)", filter_str)

        # 4. If FFmpeg binary is available, test real rendering
        if FFMPEG_EXE and os.path.exists(FFMPEG_EXE):
            output_clip = os.path.join(self.temp_dir, "output_9_16.mp4")
            cmd = [
                FFMPEG_EXE, "-y",
                "-ss", "0.0",
                "-t", "3.0",
                "-i", video_path,
                "-vf", filter_str,
                "-c:v", "libx264",
                "-pix_fmt", "yuv420p",
                "-preset", "ultrafast",
                output_clip,
            ]
            result = subprocess.run(cmd, capture_output=True, text=True)
            self.assertEqual(
                result.returncode, 0,
                f"FFmpeg failed with error:\n{result.stderr[-400:]}",
            )
            self.assertTrue(os.path.exists(output_clip))
            self.assertGreater(os.path.getsize(output_clip), 0)


if __name__ == "__main__":
    unittest.main()
