"""
Text-to-speech via ElevenLabs API (Eleven Flash v2.5).
API key via argument, ELEVENLABS_API_KEY env, or .env file. Voice ID is required.
"""

import subprocess
import sys
import tempfile
from os import environ
from pathlib import Path
from typing import Optional

from .exceptions import TTSError

def _get_api_key(api_key: Optional[str]) -> Optional[str]:
    if api_key:
        return api_key
    try:
        from dotenv import load_dotenv
        root = Path(__file__).resolve().parent.parent.parent
        load_dotenv(root / ".env")
        load_dotenv()  # cwd override
    except ImportError:
        pass
    return environ.get("ELEVENLABS_API_KEY")

DEFAULT_MODEL_ID = "eleven_flash_v2_5"
DEFAULT_OUTPUT_FORMAT = "mp3_44100_128"


def _convert_sync(
    text: str,
    api_key: str,
    voice_id: str,
    model_id: str = DEFAULT_MODEL_ID,
    output_format: str = DEFAULT_OUTPUT_FORMAT,
) -> bytes:
    from elevenlabs.client import ElevenLabs

    client = ElevenLabs(api_key=api_key)
    try:
        audio = client.text_to_speech.convert(
            voice_id=voice_id,
            text=text,
            model_id=model_id,
            output_format=output_format,
        )
    except Exception as e:
        raise TTSError(str(e)) from e
    if isinstance(audio, bytes):
        return audio
    return b"".join(audio) if hasattr(audio, "__iter__") else bytes(audio)


async def text_to_speech(
    text: str,
    voice_id: str,
    api_key: Optional[str] = None,
    model_id: str = DEFAULT_MODEL_ID,
    output_format: str = DEFAULT_OUTPUT_FORMAT,
    output_path: Optional[str] = None,
) -> bytes:
    """
    Convert text to speech using ElevenLabs (Eleven Flash v2.5 by default).

    Args:
        text: Text to synthesize.
        voice_id: ElevenLabs voice ID (required). Example: JBFqnCBsd6RMkjVDRZzb.
        api_key: ElevenLabs API key. Defaults to ELEVENLABS_API_KEY env.
        model_id: Model ID. Defaults to eleven_flash_v2_5.
        output_format: Audio format, e.g. mp3_44100_128.
        output_path: If set, write audio bytes to this file path.

    Returns:
        Audio as bytes.

    Raises:
        TTSError: On API or network errors.
    """
    from asyncio import get_event_loop

    key = _get_api_key(api_key)
    if not key:
        raise TTSError("ElevenLabs API key required: pass api_key or set ELEVENLABS_API_KEY")
    if not text.strip():
        raise TTSError("Text must not be empty")
    loop = get_event_loop()
    audio = await loop.run_in_executor(
        None,
        lambda: _convert_sync(text, key, voice_id, model_id, output_format),
    )
    if output_path:
        with open(output_path, "wb") as f:
            f.write(audio)
    return audio


def play_audio(audio: bytes, suffix: str = ".mp3") -> None:
    """
    Play audio bytes in the system default player (no extra dependencies).
    Writes to a temp file and opens it. Temp file is left for the OS to clean.

    Args:
        audio: Raw audio bytes (e.g. from text_to_speech).
        suffix: File extension for the temp file. Must match the audio format (default mp3).
    """
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as f:
        f.write(audio)
        path = Path(f.name)
    if sys.platform == "darwin":
        subprocess.run(["open", str(path)], check=False)
    elif sys.platform == "win32":
        subprocess.run(["start", "", str(path)], shell=True, check=False)
    else:
        subprocess.run(["xdg-open", str(path)], check=False)


def play_audio_file(path: str) -> None:
    """
    Play an audio file in the system default player (no extra dependencies).

    Args:
        path: Path to the audio file (e.g. "test.mp3").
    """
    path = Path(path).resolve()
    if not path.is_file():
        raise FileNotFoundError(str(path))
    if sys.platform == "darwin":
        subprocess.run(["open", str(path)], check=False)
    elif sys.platform == "win32":
        subprocess.run(["start", "", str(path)], shell=True, check=False)
    else:
        subprocess.run(["xdg-open", str(path)], check=False)
