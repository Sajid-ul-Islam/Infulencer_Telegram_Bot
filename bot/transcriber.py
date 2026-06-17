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
    global _whisper_model
    try:
        from faster_whisper import WhisperModel
        if _whisper_model is None:
            logger.info("Initializing local faster-whisper model...")
            _whisper_model = WhisperModel("base", device="cpu", compute_type="int8")
        segments, _ = _whisper_model.transcribe(audio_path, beam_size=5)
        text = " ".join(seg.text for seg in segments)
        return text.strip()
    except Exception as e:
        logger.warning(f"Local faster-whisper failed, trying OpenAI Whisper API: {e}")
        return await _transcribe_api(audio_path)

async def _transcribe_api(audio_path: str) -> str:
    from bot.config import OPENAI_API_KEY
    if not OPENAI_API_KEY:
        logger.warning("OpenAI API key missing; cannot transcribe audio via API.")
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
