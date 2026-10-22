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


def download_audio(youtube_url: str, task_id: int) -> str:
    """Download YouTube audio and convert it to WAV using the FFmpeg installed in Docker."""
    import yt_dlp
    output_template = str(SHARED_MEDIA_DIR / f"{task_id}.%(ext)s")

    options = {
        "format": "bestaudio/best",
        "outtmpl": output_template,
        "noplaylist": True,
        "quiet": True,
        "no_warnings": True,
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
    crop_filter: str = "crop=ih*9/16:ih,scale=1080:1920"
) -> str:
    """Нарезка MP4-клипа 9:16"""
    SHARED_MEDIA_DIR.mkdir(parents=True, exist_ok=True)
    output_path = SHARED_MEDIA_DIR / output_filename
    duration = end_sec - start_sec

    if duration <= 0:
        raise ValueError("Время окончания должно быть строго больше времени начала")

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
        "-c:v", "libx264",
        "-pix_fmt", "yuv420p",
        "-preset", "veryfast",
        "-crf", "22",
        "-c:a", "aac",
        "-b:a", "128k",
        "-movflags", "+faststart",
        str(output_path)
    ]

    logger.info(f"Запуск нарезки FFmpeg: {' '.join(cmd)}")
    res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    if res.returncode != 0:
        logger.error(f"FFmpeg error: {res.stderr}")
        raise RuntimeError(f"FFmpeg failed: {res.stderr[-200:]}")

    return str(output_path)