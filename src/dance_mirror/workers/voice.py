"""Optional low-latency microphone transcription for robot commands."""

from __future__ import annotations

import io
import logging
import time
import wave
from dataclasses import dataclass

import httpx
from PyQt6.QtCore import pyqtSignal

from dance_mirror.workers.base import CancellableWorker

LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class CloudSpeechRecognitionConfig:
    """OpenAI-compatible speech-to-text endpoint configuration."""

    base_url: str = "https://api.openai.com/v1"
    model: str = "whisper-1"
    api_key: str = ""
    language: str = "zh"
    timeout_s: float = 30.0
    sample_rate: int = 16000
    window_s: float = 1.8


class VoiceCommandWorker(CancellableWorker):
    """Capture short microphone windows and transcribe them off the UI thread."""

    transcriptReady = pyqtSignal(str, bool)
    statusChanged = pyqtSignal(str)
    levelChanged = pyqtSignal(float)

    def __init__(self, config: CloudSpeechRecognitionConfig) -> None:
        super().__init__()
        self.config = config

    def run(self) -> None:
        if not self.config.api_key:
            self.statusChanged.emit("云端语音识别未配置 API Key")
            self.finished.emit()
            return
        try:
            import numpy as np
            import sounddevice as sd
        except ImportError:
            self.statusChanged.emit("未安装 sounddevice，可使用文字指令")
            self.finished.emit()
            return

        block_s = 0.10
        blocks_per_window = max(1, round(self.config.window_s / block_s))
        block_frames = max(1, round(self.config.sample_rate * block_s))
        self.statusChanged.emit("正在监听实时语音")
        try:
            with sd.InputStream(
                samplerate=self.config.sample_rate,
                channels=1,
                dtype="int16",
                blocksize=block_frames,
            ) as stream:
                while not self._stopped:
                    blocks: list[object] = []
                    peak = 0.0
                    for _ in range(blocks_per_window):
                        if self._stopped:
                            break
                        block, overflowed = stream.read(block_frames)
                        if overflowed:
                            LOGGER.debug("microphone input overflow")
                        samples = np.asarray(block, dtype=np.int16).reshape(-1)
                        blocks.append(samples.copy())
                        if samples.size:
                            peak = max(peak, float(np.max(np.abs(samples))) / 32768.0)
                        self.levelChanged.emit(peak)
                    if self._stopped:
                        break
                    if peak < 0.012 or not blocks:
                        self.transcriptReady.emit("", False)
                        continue
                    audio = np.concatenate(blocks)
                    text = self._transcribe(audio)
                    self.transcriptReady.emit(text, bool(text))
            self.finished.emit()
        except Exception as exc:
            LOGGER.exception("microphone transcription failed")
            self.errorOccurred.emit(f"{type(exc).__name__}: {exc}")

    def _transcribe(self, samples: object) -> str:
        import numpy as np

        audio = np.asarray(samples, dtype=np.int16)
        buffer = io.BytesIO()
        with wave.open(buffer, "wb") as wav:
            wav.setnchannels(1)
            wav.setsampwidth(2)
            wav.setframerate(self.config.sample_rate)
            wav.writeframes(audio.tobytes())
        buffer.seek(0)
        endpoint = f"{self.config.base_url.rstrip('/')}/audio/transcriptions"
        try:
            with httpx.Client(timeout=self.config.timeout_s) as client:
                response = client.post(
                    endpoint,
                    headers={"Authorization": f"Bearer {self.config.api_key}"},
                    data={
                        "model": self.config.model,
                        "language": self.config.language,
                        "response_format": "json",
                    },
                    files={"file": ("command.wav", buffer, "audio/wav")},
                )
                response.raise_for_status()
                payload = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            LOGGER.warning("cloud speech recognition failed: %s", exc)
            return ""
        text = str(payload.get("text", "")).strip()
        return text if 0 < len(text) <= 160 else ""


class TextCommandThrottle:
    """Prevent duplicate text submissions from keyboard auto-repeat."""

    def __init__(self, min_interval_s: float = 0.35) -> None:
        self.min_interval_s = min_interval_s
        self._last: dict[str, float] = {}

    def allow(self, text: str) -> bool:
        now = time.monotonic()
        last = self._last.get(text, float("-inf"))
        if now - last < self.min_interval_s:
            return False
        self._last[text] = now
        return True
