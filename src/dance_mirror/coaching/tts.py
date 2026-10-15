"""Local and cloud speech output adapters.

The adapters never touch Qt widgets.  The speech worker is responsible for
calling them from its own thread.
"""

from __future__ import annotations

import logging
import platform
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path

LOGGER = logging.getLogger(__name__)


@dataclass(slots=True)
class SpeechConfig:
    """Voice selection and rate for SAPI or pyttsx3."""

    rate: int = 1
    volume: int = 100
    voice_name: str | None = None


@dataclass(slots=True)
class CloudTTSConfig:
    """OpenAI-compatible cloud speech endpoint settings."""

    base_url: str = "https://api.openai.com/v1"
    model: str = "gpt-4o-mini-tts"
    voice: str = "alloy"
    api_key: str = ""
    timeout_s: float = 30.0

    def endpoint(self) -> str:
        return f"{self.base_url.rstrip('/')}/audio/speech"


class NullSpeechSynthesizer:
    """No-op implementation used when speech is disabled or unavailable."""

    def speak(self, text: str) -> None:
        del text

    def stop(self) -> None:
        return None


class WindowsSapiSpeechSynthesizer:
    """Speak through Windows PowerShell's System.Speech assembly."""

    def __init__(self, config: SpeechConfig | None = None) -> None:
        self.config = config or SpeechConfig()
        self._process: subprocess.Popen[bytes] | None = None

    def speak(self, text: str) -> None:
        text = text.strip()
        if not text:
            return
        self.stop()
        executable = shutil.which("powershell.exe") or shutil.which("pwsh.exe")
        if executable is None:
            LOGGER.warning("PowerShell is unavailable; skipping speech cue")
            return
        voice = ""
        if self.config.voice_name:
            escaped_voice = self.config.voice_name.replace("'", "''")
            voice = f"$s.SelectVoice('{escaped_voice}');"
        escaped = text.replace("'", "''")
        script = (
            "Add-Type -AssemblyName System.Speech;"
            "$s=New-Object System.Speech.Synthesis.SpeechSynthesizer;"
            f"$s.Rate={int(self.config.rate)};"
            f"$s.Volume={int(self.config.volume)};"
            f"{voice}"
            f"$s.Speak('{escaped}');"
        )
        self._process = subprocess.Popen(
            [executable, "-NoProfile", "-NonInteractive", "-Command", script],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )

    def stop(self) -> None:
        if self._process is None:
            return
        if self._process.poll() is None:
            self._process.terminate()
        self._process = None


class Pyttsx3SpeechSynthesizer:
    """Optional cross-platform adapter backed by pyttsx3."""

    def __init__(self, config: SpeechConfig | None = None) -> None:
        self.config = config or SpeechConfig()
        try:
            import pyttsx3
        except ImportError as exc:
            raise RuntimeError("pyttsx3 is not installed") from exc
        self._engine = pyttsx3.init()
        self._engine.setProperty("rate", 170 + self.config.rate * 20)
        self._engine.setProperty("volume", self.config.volume / 100.0)

    def speak(self, text: str) -> None:
        text = text.strip()
        if not text:
            return
        self._engine.say(text)
        self._engine.runAndWait()

    def stop(self) -> None:
        self._engine.stop()


class CloudSpeechSynthesizer:
    """Fetch cloud TTS audio and play it asynchronously on Windows."""

    def __init__(self, config: CloudTTSConfig) -> None:
        self.config = config
        self._audio_path: Path | None = None

    def speak(self, text: str) -> None:
        text = text.strip()
        if not text:
            return
        if not self.config.api_key:
            raise RuntimeError("cloud TTS API key is not configured")
        self.stop()
        import httpx

        with httpx.Client(timeout=self.config.timeout_s) as client:
            response = client.post(
                self.config.endpoint(),
                headers={"Authorization": f"Bearer {self.config.api_key}"},
                json={
                    "model": self.config.model,
                    "voice": self.config.voice,
                    "input": text,
                    "response_format": "mp3",
                },
            )
            response.raise_for_status()
            audio = response.content
        if not audio:
            raise RuntimeError("cloud TTS returned empty audio")
        self._cleanup_audio()
        with tempfile.NamedTemporaryFile(mode="wb", suffix=".mp3", delete=False) as handle:
            handle.write(audio)
            path = Path(handle.name)
        self._audio_path = path
        try:
            import winsound

            winsound.PlaySound(str(path), winsound.SND_FILENAME | winsound.SND_ASYNC)
        except ImportError:
            LOGGER.warning("cloud TTS audio was fetched but winsound is unavailable")
        except (OSError, RuntimeError):
            LOGGER.exception("cloud TTS audio playback failed")

    def stop(self) -> None:
        try:
            import winsound

            winsound.PlaySound(None, winsound.SND_PURGE)
        except (ImportError, OSError, RuntimeError):
            pass
        self._cleanup_audio()

    def _cleanup_audio(self) -> None:
        if self._audio_path is None:
            return
        try:
            self._audio_path.unlink(missing_ok=True)
        except OSError:
            LOGGER.debug("failed to remove cloud TTS temp file", exc_info=True)
        self._audio_path = None


def create_speech_synthesizer(
    enabled: bool = True,
    cloud_config: CloudTTSConfig | None = None,
) -> object:
    """Choose a speech backend without making speech a hard dependency."""
    if not enabled:
        return NullSpeechSynthesizer()
    if cloud_config is not None and cloud_config.api_key:
        return CloudSpeechSynthesizer(cloud_config)
    if platform.system().lower() == "windows":
        return WindowsSapiSpeechSynthesizer()
    try:
        return Pyttsx3SpeechSynthesizer()
    except RuntimeError:
        return NullSpeechSynthesizer()
