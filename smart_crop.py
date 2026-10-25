"""Face-aware 9:16 crop generation for horizontal source videos.

MediaPipe Face Mesh is sampled through OpenCV. Scene cuts are detected via HSV
histogram differences to eliminate nauseating panning and provide instant cuts.
Mouth Aspect Ratio (MAR = lip height / mouth width) provides scale-invariant lip
mobility measurement. Active speakers are detected individually per montage plan,
and a compact step filter (up to 150 characters) is generated for FFmpeg.
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


def calculate_mar(landmarks) -> float:
    """Calculate normalized Mouth Aspect Ratio (MAR = lip height / mouth width).

    Eliminates dependency on distance between face and camera.
    MediaPipe Face Mesh landmarks:
      - Upper inner lip: 13
      - Lower inner lip: 14
      - Left mouth corner: 61
      - Right mouth corner: 291
    """
    try:
        if hasattr(landmarks, "landmark"):
            points = landmarks.landmark
        else:
            points = landmarks

        p13 = points[13]
        p14 = points[14]
        p61 = points[61]
        p291 = points[291]

        def _coord(p, attr):
            if isinstance(p, dict):
                return float(p.get(attr, 0.0))
            return float(getattr(p, attr, 0.0))

        lip_height = math.hypot(_coord(p13, "x") - _coord(p14, "x"), _coord(p13, "y") - _coord(p14, "y"))
        mouth_width = math.hypot(_coord(p61, "x") - _coord(p291, "x"), _coord(p61, "y") - _coord(p291, "y"))

        if mouth_width > 1e-5:
            return round(lip_height / mouth_width, 4)
        return 0.0
    except (IndexError, AttributeError, KeyError):
        return 0.0


def detect_scene_cut_histogram(prev_frame, curr_frame, threshold: float = 0.55) -> tuple[bool, float]:
    """Detect if a scene cut occurred between two frames using OpenCV HSV histogram correlation.

    Returns (is_cut, correlation_score). Lower correlation indicates a scene transition.
    """
    import cv2

    if prev_frame is None or curr_frame is None:
        return False, 1.0

    prev_hsv = cv2.cvtColor(prev_frame, cv2.COLOR_BGR2HSV)
    curr_hsv = cv2.cvtColor(curr_frame, cv2.COLOR_BGR2HSV)

    hist_prev = cv2.calcHist([prev_hsv], [0, 1], None, [16, 16], [0, 180, 0, 256])
    hist_curr = cv2.calcHist([curr_hsv], [0, 1], None, [16, 16], [0, 180, 0, 256])

    cv2.normalize(hist_prev, hist_prev, alpha=0, beta=1, norm_type=cv2.NORM_MINMAX)
    cv2.normalize(hist_curr, hist_curr, alpha=0, beta=1, norm_type=cv2.NORM_MINMAX)

    score = float(cv2.compareHist(hist_prev, hist_curr, cv2.HISTCMP_CORREL))
    is_cut = score < threshold
    return is_cut, score


def _tracks_and_scenes_from_video(
    source_path: str,
    start_sec: float,
    end_sec: float,
    sample_interval: float = 0.4,
    hist_threshold: float = 0.55,
):
    """Sample video, detect scene cuts via histogram differences, and extract face observations."""
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

    scenes: list[dict] = []
    current_scene_start = 0.0
    current_scene_detections: list[dict] = []
    prev_frame = None

    frame_width = int(capture.get(cv2.CAP_PROP_FRAME_WIDTH) or 1920)
    frame_height = int(capture.get(cv2.CAP_PROP_FRAME_HEIGHT) or 1080)

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

            frame_height, frame_width = frame.shape[:2]
            rel_t = max(0.0, round(absolute_t - start_sec, 2))

            # Scene Cut Detection via HSV histogram correlation
            if prev_frame is not None:
                is_cut, _ = detect_scene_cut_histogram(prev_frame, frame, threshold=hist_threshold)
                if is_cut and (rel_t - current_scene_start) >= 1.0:
                    scenes.append({
                        "start_t": current_scene_start,
                        "end_t": rel_t,
                        "detections": current_scene_detections,
                    })
                    current_scene_start = rel_t
                    current_scene_detections = []

            prev_frame = frame.copy()

            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            result = mesh.process(rgb)

            for landmarks in (result.multi_face_landmarks or []):
                xs = [point.x for point in landmarks.landmark]
                ys = [point.y for point in landmarks.landmark]
                left, right = _clamp(min(xs), 0.0, 1.0), _clamp(max(xs), 0.0, 1.0)
                top, bottom = _clamp(min(ys), 0.0, 1.0), _clamp(max(ys), 0.0, 1.0)
                face_area = max(0.0, right - left) * max(0.0, bottom - top)
                center_x = (left + right) / 2.0
                center_y = (top + bottom) / 2.0

                mar = calculate_mar(landmarks)

                current_scene_detections.append({
                    "time": rel_t,
                    "center_x": center_x,
                    "center_y": center_y,
                    "area": face_area,
                    "mar": mar,
                    "mouth_gap": mar,
                    "width": frame_width,
                    "height": frame_height,
                })

        clip_duration = max(0.1, round(clip_end - start_sec, 2))
        scenes.append({
            "start_t": current_scene_start,
            "end_t": clip_duration,
            "detections": current_scene_detections,
        })
    finally:
        mesh.close()
        capture.release()

    return scenes, frame_width, frame_height


def _tracks_from_video(source_path: str, start_sec: float, end_sec: float, sample_interval: float = 0.4):
    """Return face tracks sampled across a clip for legacy and compatibility."""
    scenes, _, _ = _tracks_and_scenes_from_video(source_path, start_sec, end_sec, sample_interval)
    tracks: dict[int, list[dict]] = defaultdict(list)
    next_track_id = 0
    previous_centres: dict[int, tuple[float, float]] = {}

    all_detections = []
    for s in scenes:
        all_detections.extend(s["detections"])

    for d in sorted(all_detections, key=lambda item: item["time"]):
        best_id = None
        best_distance = float("inf")
        for track_id, center in previous_centres.items():
            dist = math.hypot(d["center_x"] - center[0], d["center_y"] - center[1])
            if dist < best_distance and dist <= 0.22:
                best_id, best_distance = track_id, dist
        if best_id is None:
            best_id = next_track_id
            next_track_id += 1
        tracks[best_id].append(d)
        previous_centres[best_id] = (d["center_x"], d["center_y"])

    return tracks


def _speaker_track(tracks: dict[int, list[dict]]) -> list[dict] | None:
    """Prefer a large, consistently visible face with normalized MAR mouth activity."""
    if not tracks:
        return None

    def score(observations: list[dict]) -> float:
        areas = [item["area"] for item in observations]
        mars = [item.get("mar", item.get("mouth_gap", 0.0)) for item in observations]
        avg_area = sum(areas) / len(areas)
        if len(mars) > 1:
            avg_mar = sum(mars) / len(mars)
            mar_variance = sum((value - avg_mar) ** 2 for value in mars) / len(mars)
            mouth_activity = min(1.0, math.sqrt(mar_variance) * 15.0)
        else:
            mouth_activity = 0.0
        visibility = min(1.0, len(observations) / 4.0)
        return 0.50 * avg_area + 0.40 * avg_area * mouth_activity + 0.10 * avg_area * visibility

    return max(tracks.values(), key=score)


def _active_speaker_in_scene(detections: list[dict], frame_width: int, crop_width: float, max_x: float) -> float:
    """Determine the active speaker crop X individually for a single montage plan (scene segment)."""
    if not detections:
        return max_x / 2.0

    # Cluster detections in this scene into speaker tracks by proximity
    clusters: list[list[dict]] = []
    for d in sorted(detections, key=lambda item: item["time"]):
        matched = False
        for cl in clusters:
            last = cl[-1]
            if math.hypot(d["center_x"] - last["center_x"], d["center_y"] - last["center_y"]) <= 0.20:
                cl.append(d)
                matched = True
                break
        if not matched:
            clusters.append([d])

    def scene_speaker_score(cluster: list[dict]) -> float:
        areas = [item["area"] for item in cluster]
        mars = [item.get("mar", item.get("mouth_gap", 0.0)) for item in cluster]
        avg_area = sum(areas) / len(areas)
        if len(mars) > 1:
            avg_mar = sum(mars) / len(mars)
            mar_variance = sum((m - avg_mar) ** 2 for m in mars) / len(mars)
            mar_activity = min(1.0, math.sqrt(mar_variance) * 15.0)
        else:
            mar_activity = 0.0
        return 0.50 * avg_area + 0.50 * avg_area * mar_activity

    best_cluster = max(clusters, key=scene_speaker_score)
    avg_x = sum(d["center_x"] for d in best_cluster) / len(best_cluster)
    target_x = _clamp(avg_x * frame_width - crop_width / 2.0, 0.0, max_x)
    return target_x


def _ema(values: list[float], alpha: float = 0.35) -> list[float]:
    if not values:
        return []
    smoothed = [values[0]]
    for value in values[1:]:
        smoothed.append(alpha * value + (1.0 - alpha) * smoothed[-1])
    return smoothed


def _make_step_x_expression(scene_segments: list[tuple[float, float, float]]) -> str:
    """Create a compact step FFmpeg x expression for scene cuts without recursive bloat.

    Guarantees the overall filter remains compact (length up to 150 characters).
    """
    if not scene_segments:
        return "(iw-ih*9/16)/2"

    merged: list[tuple[float, float, int]] = []
    for t_start, t_end, x_val in scene_segments:
        x_int = int(round(x_val))
        if merged and abs(merged[-1][2] - x_int) <= 15:
            merged[-1] = (merged[-1][0], t_end, merged[-1][2])
        else:
            merged.append((t_start, t_end, x_int))

    # Keep at most 3 scene cut transitions to strictly guarantee filter <= 150 chars
    while len(merged) > 3:
        shortest_idx = min(range(len(merged) - 1), key=lambda i: (merged[i][1] - merged[i][0]))
        t0, _, x0 = merged[shortest_idx]
        _, t2, _ = merged[shortest_idx + 1]
        merged[shortest_idx] = (t0, t2, x0)
        del merged[shortest_idx + 1]

    if len(merged) == 1:
        return str(merged[0][2])

    expr = str(merged[-1][2])
    for i in range(len(merged) - 2, -1, -1):
        cut_t = _ffmpeg_number(merged[i][1])
        x_val = merged[i][2]
        expr = f"if(lt(t\\,{cut_t})\\,{x_val}\\,{expr})"

    return expr


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
    return f"max(0\\,min(iw-ih*9/16\\,{expression}))"


def build_smart_crop_filter(source_path: str, start_sec: float, end_sec: float, alpha: float = 0.35) -> str:
    """Build a scene-aware step crop filter for a single clip with instant cuts between speakers.

    Uses OpenCV histogram differences for scene cuts, normalized MAR for lip mobility,
    and produces a compact FFmpeg filter expression of length up to 150 characters.
    """
    fallback = "crop=w=ih*9/16:h=ih:x=(iw-ih*9/16)/2:y=0,scale=1080:1920"
    if not Path(source_path).exists():
        logger.warning("Smart Crop: source video missing; using centre crop")
        return fallback

    try:
        scenes, frame_width, frame_height = _tracks_and_scenes_from_video(source_path, start_sec, end_sec)
        crop_width = frame_height * 9.0 / 16.0
        max_x = max(0.0, frame_width - crop_width)

        has_any_face = any(bool(s["detections"]) for s in scenes)
        if not has_any_face:
            logger.info("Smart Crop: faces not found; using centre crop")
            return fallback

        scene_segments = []
        for s in scenes:
            scene_crop_x = _active_speaker_in_scene(s["detections"], frame_width, crop_width, max_x)
            scene_segments.append((s["start_t"], s["end_t"], scene_crop_x))

        x_expr = _make_step_x_expression(scene_segments)
        filter_str = f"crop=w=ih*9/16:h=ih:x='{x_expr}':y=0,scale=1080:1920"

        # Guarantee compact filter <= 150 characters
        if len(filter_str) > 150:
            avg_x = int(round(sum(seg[2] for seg in scene_segments) / len(scene_segments)))
            filter_str = f"crop=w=ih*9/16:h=ih:x={avg_x}:y=0,scale=1080:1920"

        logger.info("Smart Crop generated step filter (len=%d): %s", len(filter_str), filter_str)
        return filter_str
    except Exception as exc:
        logger.warning("Smart Crop failed (%s); using centre crop", exc)
        return fallback
