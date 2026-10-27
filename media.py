import logging
import os
from pathlib import Path
import subprocess

logger = logging.getLogger(__name__)

SHARED_MEDIA_DIR = Path(os.getenv("SHARED_MEDIA_DIR", "/shared/media"))
try:
    SHARED_MEDIA_DIR.mkdir(parents=True, exist_ok=True)
except Exception:
    SHARED_MEDIA_DIR = Path("./media")
    SHARED_MEDIA_DIR.mkdir(parents=True, exist_ok=True)


def download_source_video(youtube_url: str, task_id: int) -> str:
    """Download the source video used by Smart Crop and FFmpeg rendering."""
    import yt_dlp

    output_template = str(SHARED_MEDIA_DIR / f"{task_id}_source.%(ext)s")
    options = {
        "format": "bestvideo+bestaudio/best",
        "outtmpl": output_template,
        "noplaylist": True,
        "quiet": True,
        "no_warnings": True,
        "merge_output_format": "mp4",
        "nocheckcertificate": True,
        "extractor_args": {
            "youtube": {
                "player_client": ["android", "ios", "web"],
            }
        },
        "http_headers": {
            "User-Agent": "com.google.android.youtube/19.09.37 (Linux; U; Android 11) gzip",
            "Accept-Language": "en-US,en;q=0.9",
        },
    }
    with yt_dlp.YoutubeDL(options) as ydl:
        ydl.download([youtube_url])

    candidates = sorted(SHARED_MEDIA_DIR.glob(f"{task_id}_source.*"))
    candidates = [
        path for path in candidates
        if path.suffix.lower() in {".mp4", ".mkv", ".webm", ".mov"}
        and not path.name.endswith((".part", ".ytdl"))
    ]
    if not candidates:
        raise FileNotFoundError(f"Исходное видео не было создано для задачи {task_id}")
    # Prefer MP4 when yt-dlp successfully merged video and audio into it.
    candidates.sort(key=lambda path: (path.suffix.lower() == ".mp4", path.stat().st_size), reverse=True)
    return str(candidates[0])


def source_video_for_task(task_id: int) -> str:
    """Find the downloaded source video for a task, preferring MP4."""
    candidates = [
        path for path in SHARED_MEDIA_DIR.glob(f"{task_id}_source.*")
        if path.suffix.lower() in {".mp4", ".mkv", ".webm", ".mov"}
        and not path.name.endswith((".part", ".ytdl"))
    ]
    if candidates:
        candidates.sort(key=lambda path: (path.suffix.lower() == ".mp4", path.stat().st_size), reverse=True)
        return str(candidates[0])
    legacy = SHARED_MEDIA_DIR / f"{task_id}.mp4"
    if legacy.exists():
        return str(legacy)
    return str(SHARED_MEDIA_DIR / "source.mp4")


def download_audio(youtube_url: str, task_id: int, source_video_path: str | None = None) -> str:
    """Extract mono 16 kHz WAV from the already-downloaded video when possible."""
    wav_path = SHARED_MEDIA_DIR / f"{task_id}.wav"
    if source_video_path and os.path.exists(source_video_path):
        command = [
            "ffmpeg", "-y", "-i", source_video_path, "-vn",
            "-ac", "1", "-ar", "16000", "-c:a", "pcm_s16le", str(wav_path),
        ]
        result = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        if result.returncode != 0:
            raise RuntimeError(f"Не удалось извлечь аудио из исходного видео: {result.stderr[-500:]}")
        if not wav_path.exists():
            raise FileNotFoundError(f"Audio file was not created: {wav_path}")
        return str(wav_path)

    import yt_dlp
    output_template = str(SHARED_MEDIA_DIR / f"{task_id}.%(ext)s")

    options = {
        "format": "bestaudio/best",
        "outtmpl": output_template,
        "noplaylist": True,
        "quiet": True,
        "no_warnings": True,
        "nocheckcertificate": True,
        "extractor_args": {
            "youtube": {
                "player_client": ["android", "ios", "web"],
            }
        },
        "http_headers": {
            "User-Agent": "com.google.android.youtube/19.09.37 (Linux; U; Android 11) gzip",
            "Accept-Language": "en-US,en;q=0.9",
        },
        "postprocessors": [
            {
                "key": "FFmpegExtractAudio",
                "preferredcodec": "wav",
                "preferredquality": "192",
            }
        ],
    }

    with yt_dlp.YoutubeDL(options) as ydl:
        ydl.download([youtube_url])

    wav_path = SHARED_MEDIA_DIR / f"{task_id}.wav"
    if not wav_path.exists():
        raise FileNotFoundError(f"Audio file was not created: {wav_path}")

    return str(wav_path)


def cut_vertical_clip(
    source_path: str,
    output_filename: str,
    start_sec: float,
    end_sec: float,
    crop_filter: str | None = None
) -> str:
    """Нарезка MP4-клипа 9:16"""
    SHARED_MEDIA_DIR.mkdir(parents=True, exist_ok=True)
    output_path = SHARED_MEDIA_DIR / output_filename
    duration = end_sec - start_sec
    if duration <= 0:
        raise ValueError("Время окончания должно быть строго больше времени начала")

    if crop_filter is None:
        from smart_crop import build_smart_crop_filter
        crop_filter = build_smart_crop_filter(source_path, start_sec, end_sec)

    if not os.path.exists(source_path):
        test_source = SHARED_MEDIA_DIR / "test_source.mp4"
        if not test_source.exists():
            create_cmd = [
                "ffmpeg", "-y", "-f", "lavfi",
                "-i", "testsrc=size=1920x1080:rate=30",
                "-f", "lavfi", "-i", "sine=frequency=1000:duration=120",
                "-t", "120",
                "-c:v", "libx264",
                "-pix_fmt", "yuv420p", 
                "-c:a", "aac", 
                str(test_source)
            ]
            subprocess.run(create_cmd, check=True)
        source_path = str(test_source)

    cmd = [
        "ffmpeg", "-y",
        "-ss", f"{start_sec:.3f}",
        "-t", f"{duration:.3f}",
        "-i", str(source_path),
        "-vf", crop_filter,
        "-sws_flags", "lanczos",
        "-c:v", "libx264",
        "-pix_fmt", "yuv420p",
        "-preset", "medium",
        "-crf", "18",
        "-b:v", "6000k",
        "-maxrate", "8000k",
        "-bufsize", "12000k",
        "-c:a", "aac",
        "-b:a", "192k",
        "-movflags", "+faststart",
        str(output_path)
    ]

    logger.info(f"Запуск нарезки FFmpeg: {' '.join(cmd)}")
    res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    if res.returncode != 0:
        logger.error(f"FFmpeg error: {res.stderr}")
        raise RuntimeError(f"FFmpeg failed: {res.stderr[-200:]}")

    return str(output_path)