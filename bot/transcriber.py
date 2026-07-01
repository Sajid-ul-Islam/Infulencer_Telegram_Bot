import os
import re
import asyncio
from pathlib import Path
from bot.config import logger

AUDIO_DIR = Path(os.path.join(os.path.dirname(os.path.dirname(__file__)), "audio_cache"))
AUDIO_DIR.mkdir(exist_ok=True)

_whisper_model = None

def _sanitize_filename(name: str) -> str:
    return re.sub(r'[^\w\-_. ]', '', name)[:80]

async def transcribe_youtube(video_url: str, video_id: str = None) -> str:
    try:
        if not video_id:
            # Matches watch?v=ID, shorts/ID, embed/ID, youtu.be/ID
            match = re.search(r'(?:v=|\/shorts\/|\/embed\/|\/youtu\.be\/)([a-zA-Z0-9\-_]{11})', video_url)
            video_id = match.group(1) if match else "unknown"
            if video_id == "unknown":
                import uuid
                video_id = f"unknown_{uuid.uuid4().hex[:8]}"
        
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
    from bot.config import GROQ_API_KEY
    if not GROQ_API_KEY:
        logger.warning("Groq API key missing; cannot transcribe audio.")
        return ""
        
    import httpx
    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            with open(audio_path, "rb") as f:
                # Telegram sends OGG files
                content_type = "audio/ogg" if audio_path.endswith(".ogg") else "audio/mpeg"
                files = {"file": (os.path.basename(audio_path), f, content_type)}
                headers = {"Authorization": f"Bearer {GROQ_API_KEY}"}
                response = await client.post(
                    "https://api.groq.com/openai/v1/audio/transcriptions",
                    headers=headers, data={"model": "whisper-large-v3-turbo"}, files=files
                )
                response.raise_for_status()
                return response.json().get("text", "")
    except Exception as e:
        logger.error(f"Groq Whisper API error: {e}")
        return ""

def cleanup_audio(age_hours: int = 24):
    import time
    now = time.time()
    for f in AUDIO_DIR.iterdir():
        if f.is_file() and now - f.stat().st_mtime > age_hours * 3600:
            f.unlink()
