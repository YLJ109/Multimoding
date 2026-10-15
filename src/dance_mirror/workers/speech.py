"""Serialized speech worker with a bounded cue queue."""

from __future__ import annotations

import contextlib
import logging
import queue

from dance_mirror.coaching.tts import CloudTTSConfig, create_speech_synthesizer
from dance_mirror.workers.base import CancellableWorker

LOGGER = logging.getLogger(__name__)


class SpeechWorker(CancellableWorker):
    """Speak cues in order without blocking the live inference loop."""

    def __init__(
        self,
        enabled: bool = True,
        cloud_config: CloudTTSConfig | None = None,
    ) -> None:
        super().__init__()
        self.enabled = enabled
        self._queue: queue.Queue[str | None] = queue.Queue(maxsize=8)
        self._speaker = create_speech_synthesizer(enabled, cloud_config)

    def enqueue(self, text: str) -> None:
        text = text.strip()
        if not text or self._stopped:
            return
        try:
            self._queue.put_nowait(text)
        except queue.Full:
            with contextlib.suppress(queue.Empty):
                self._queue.get_nowait()
            self._queue.put_nowait(text)

    def stop(self) -> None:
        super().stop()
        with contextlib.suppress(queue.Full):
            self._queue.put_nowait(None)
        self._speaker.stop()

    def run(self) -> None:
        try:
            while not self._stopped:
                try:
                    text = self._queue.get(timeout=0.2)
                except queue.Empty:
                    continue
                if text is None:
                    break
                self._speaker.speak(text)
            self.finished.emit()
        except Exception as exc:
            LOGGER.exception("speech worker failed")
            self.errorOccurred.emit(f"{type(exc).__name__}: {exc}")
