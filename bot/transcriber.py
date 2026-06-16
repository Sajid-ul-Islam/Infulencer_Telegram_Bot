import os
import re
import asyncio
from pathlib import Path
from bot.config import logger

AUDIO_DIR = Path(os.path.join(os.path.dirname(os.path.dirname(__file__)), "audio_cache"))
AUDIO_DIR.mkdir(exist_ok=True)

def _sanitize_filename(name: str) -> str:
    return re.sub(r'[^\w\-_. ]', '', name)[:80]

async def transcribe_youtube(video_url: str, video_id: str = None) -> str:
    try:
        video_id = video_id or video_url.split("v=")[-1].split("&")[0] if "v=" in video_url else "unknown"
        audio_path = AUDIO_DIR / f"{_sanitize_filename(video_id)}.mp3"
        if audio_path.exists():
            return await _transcribe_file(str(audio_path))
        proc = await asyncio.create_subprocess_exec(
            "yt-dlp", "-x", "--audio-format", "mp3", "-o", str(audio_path),
            video_url, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
        )
        await proc.communicate()
        if not audio_path.exists():
            logger.error(f"Failed to download audio for {video_url}")
            return ""
        text = await _transcribe_file(str(audio_path))
        return text
    except Exception as e:
        logger.error(f"Transcription error for {video_url}: {e}")
        return ""

async def transcribe_voice(file_path: str) -> str:
    return await _transcribe_file(file_path)

async def _transcribe_file(audio_path: str) -> str:
    try:
        from faster_whisper import WhisperModel
        model = WhisperModel("base", device="cpu", compute_type="int8")
        segments, _ = model.transcribe(audio_path, beam_size=5)
        text = " ".join(seg.text for seg in segments)
        return text.strip()
    except ImportError:
        logger.warning("faster-whisper not installed, trying openai whisper api")
        return await _transcribe_api(audio_path)
    except Exception as e:
        logger.error(f"Whisper error: {e}")
        return ""

async def _transcribe_api(audio_path: str) -> str:
    from bot.config import OPENAI_API_KEY
    if not OPENAI_API_KEY:
        return ""
    import httpx
    try:
        async with httpx.AsyncClient(timeout=120.0) as client:
            with open(audio_path, "rb") as f:
                files = {"file": (os.path.basename(audio_path), f, "audio/mpeg")}
                headers = {"Authorization": f"Bearer {OPENAI_API_KEY}"}
                response = await client.post(
                    "https://api.openai.com/v1/audio/transcriptions",
                    headers=headers, data={"model": "whisper-1"}, files=files
                )
                response.raise_for_status()
                return response.json().get("text", "")
    except Exception as e:
        logger.error(f"OpenAI Whisper API error: {e}")
        return ""

def cleanup_audio(age_hours: int = 24):
    import time
    now = time.time()
    for f in AUDIO_DIR.iterdir():
        if f.is_file() and now - f.stat().st_mtime > age_hours * 3600:
            f.unlink()
