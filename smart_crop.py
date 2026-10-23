"""Face-aware 9:16 crop generation for horizontal source videos.

MediaPipe Face Mesh is sampled through OpenCV. A lightweight nearest-centre tracker
keeps detections associated between samples, lip movement helps choose the speaker,
and an EMA smooths the crop window before an FFmpeg time expression is generated.
"""
from __future__ import annotations

import logging
import math
from collections import defaultdict
from pathlib import Path

logger = logging.getLogger(__name__)


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(value, high))


def _ffmpeg_number(value: float) -> str:
    return f"{value:.2f}".rstrip("0").rstrip(".") or "0"


def _tracks_from_video(source_path: str, start_sec: float, end_sec: float, sample_interval: float = 0.4):
    """Return face tracks sampled across a clip. Import CV dependencies lazily."""
    import cv2
    import mediapipe as mp

    capture = cv2.VideoCapture(str(source_path))
    if not capture.isOpened():
        raise RuntimeError(f"OpenCV не смог открыть видео: {source_path}")

    fps = capture.get(cv2.CAP_PROP_FPS) or 25.0
    frame_count = capture.get(cv2.CAP_PROP_FRAME_COUNT) or 0
    duration = frame_count / fps if fps > 0 and frame_count > 0 else end_sec
    clip_end = min(end_sec, duration) if duration > 0 else end_sec
    if clip_end <= start_sec:
        capture.release()
        raise ValueError("Интервал Smart Crop выходит за границы видео")

    tracks: dict[int, list[dict]] = defaultdict(list)
    next_track_id = 0
    previous_centres: dict[int, tuple[float, float]] = {}
    mesh = mp.solutions.face_mesh.FaceMesh(
        static_image_mode=True,
        max_num_faces=8,
        refine_landmarks=True,
        min_detection_confidence=0.5,
    )
    try:
        sample_times = []
        t = start_sec
        while t < clip_end:
            sample_times.append(t)
            t += sample_interval
        if not sample_times or sample_times[-1] < clip_end:
            sample_times.append(clip_end)

        for absolute_t in sample_times:
            capture.set(cv2.CAP_PROP_POS_MSEC, absolute_t * 1000.0)
            ok, frame = capture.read()
            if not ok:
                continue
            height, width = frame.shape[:2]
            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            result = mesh.process(rgb)
            detections = []
            for landmarks in (result.multi_face_landmarks or []):
                xs = [point.x for point in landmarks.landmark]
                ys = [point.y for point in landmarks.landmark]
                left, right = _clamp(min(xs), 0.0, 1.0), _clamp(max(xs), 0.0, 1.0)
                top, bottom = _clamp(min(ys), 0.0, 1.0), _clamp(max(ys), 0.0, 1.0)
                face_area = max(0.0, right - left) * max(0.0, bottom - top)
                center_x = (left + right) / 2.0
                center_y = (top + bottom) / 2.0
                # MediaPipe Face Mesh inner-lip landmarks: upper 13, lower 14.
                upper_lip = landmarks.landmark[13]
                lower_lip = landmarks.landmark[14]
                mouth_gap = math.hypot(upper_lip.x - lower_lip.x, upper_lip.y - lower_lip.y)
                detections.append({
                    "time": max(0.0, absolute_t - start_sec),
                    "center_x": center_x,
                    "center_y": center_y,
                    "area": face_area,
                    "mouth_gap": mouth_gap,
                    "width": width,
                    "height": height,
                })

            used_tracks: set[int] = set()
            # Greedy nearest-centre matching preserves identity between adjacent samples.
            for detection in sorted(detections, key=lambda item: item["area"], reverse=True):
                best_id = None
                best_distance = float("inf")
                for track_id, center in previous_centres.items():
                    if track_id in used_tracks:
                        continue
                    distance = math.hypot(
                        detection["center_x"] - center[0],
                        detection["center_y"] - center[1],
                    )
                    if distance < best_distance and distance <= 0.22:
                        best_id, best_distance = track_id, distance
                if best_id is None:
                    best_id = next_track_id
                    next_track_id += 1
                tracks[best_id].append(detection)
                previous_centres[best_id] = (detection["center_x"], detection["center_y"])
                used_tracks.add(best_id)
    finally:
        mesh.close()
        capture.release()

    return tracks


def _speaker_track(tracks: dict[int, list[dict]]) -> list[dict] | None:
    """Prefer a large, consistently visible face with visible mouth activity."""
    if not tracks:
        return None

    def score(observations: list[dict]) -> float:
        areas = [item["area"] for item in observations]
        mouth = [item["mouth_gap"] for item in observations]
        avg_area = sum(areas) / len(areas)
        if len(mouth) > 1:
            avg_mouth = sum(mouth) / len(mouth)
            mouth_variance = sum((value - avg_mouth) ** 2 for value in mouth) / len(mouth)
            mouth_activity = min(1.0, math.sqrt(mouth_variance) * 18.0)
        else:
            mouth_activity = 0.0
        visibility = min(1.0, len(observations) / 4.0)
        return (0.60 * avg_area + 0.30 * avg_area * mouth_activity + 0.10 * avg_area * visibility)

    return max(tracks.values(), key=score)


def _ema(values: list[float], alpha: float = 0.35) -> list[float]:
    if not values:
        return []
    smoothed = [values[0]]
    for value in values[1:]:
        smoothed.append(alpha * value + (1.0 - alpha) * smoothed[-1])
    return smoothed


def _make_x_expression(points: list[tuple[float, float]]) -> str:
    """Create a piecewise-linear FFmpeg x expression; commas must be escaped."""
    if not points:
        return "(iw-ih*9/16)/2"
    expression = _ffmpeg_number(points[-1][1])
    for index in range(len(points) - 2, -1, -1):
        t0, x0 = points[index]
        t1, x1 = points[index + 1]
        if t1 <= t0:
            segment = _ffmpeg_number(x1)
        else:
            segment = (
                f"({_ffmpeg_number(x0)}+({_ffmpeg_number(x1)}-({_ffmpeg_number(x0)}))"
                f"*(t-{_ffmpeg_number(t0)})/{_ffmpeg_number(t1 - t0)})"
            )
        expression = f"if(lt(t\\,{_ffmpeg_number(t1)})\\,{segment}\\,{expression})"
    # Keep the crop within the source frame even if the speaker moves to an edge.
    return f"max(0\\,min(iw-ih*9/16\\,{expression}))"


def build_smart_crop_filter(source_path: str, start_sec: float, end_sec: float, alpha: float = 0.35) -> str:
    """Build a smoothed speaker-following crop filter for a single clip.

    If face detection is unavailable or no face is found, use a stable centre crop.
    """
    fallback = "crop=w=ih*9/16:h=ih:x=(iw-ih*9/16)/2:y=0,scale=1080:1920"
    if not Path(source_path).exists():
        logger.warning("Smart Crop: source video missing; using centre crop")
        return fallback

    try:
        tracks = _tracks_from_video(source_path, start_sec, end_sec)
        speaker = _speaker_track(tracks)
        if not speaker:
            logger.info("Smart Crop: faces not found; using centre crop")
            return fallback

        frame_width = int(speaker[0]["width"])
        frame_height = int(speaker[0]["height"])
        crop_width = frame_height * 9.0 / 16.0
        max_x = max(0.0, frame_width - crop_width)
        target_x = []
        for observation in speaker:
            # Keep the face centre near the middle of the vertical crop.
            x = _clamp(observation["center_x"] * frame_width - crop_width / 2.0, 0.0, max_x)
            target_x.append(x)
        smoothed_x = _ema(target_x, alpha=alpha)
        points = [(item["time"], x) for item, x in zip(speaker, smoothed_x)]
        x_expression = _make_x_expression(points)
        crop = f"crop=w=ih*9/16:h=ih:x='{x_expression}':y=0,scale=1080:1920"
        logger.info("Smart Crop selected a face track with %s samples", len(points))
        return crop
    except Exception as exc:
        # Crop detection must not prevent a video from being produced.
        logger.warning("Smart Crop failed (%s); using centre crop", exc)
        return fallback
