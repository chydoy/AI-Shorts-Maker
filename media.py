from pathlib import Path

import yt_dlp

SHARED_MEDIA_DIR = Path("/shared/media")
SHARED_MEDIA_DIR.mkdir(parents=True, exist_ok=True)


def download_audio(youtube_url: str, task_id: int) -> str:
    """Download YouTube audio and convert it to WAV using the FFmpeg installed in Docker."""
    output_template = str(SHARED_MEDIA_DIR / f"{task_id}.%(ext)s")

    options = {
        "format": "bestaudio/best",
        "extractor_args": {
            "youtube": {
                "player_client": ["android"]
            }
        },
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