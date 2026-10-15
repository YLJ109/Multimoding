"""Cloud summary and validated command-planning workers."""

from __future__ import annotations

import logging
import time
from collections.abc import Mapping
from typing import Any

import httpx
from PyQt6.QtCore import pyqtSignal

from dance_mirror.coaching.cloud import CloudCommandPlanner, CloudConfig, CloudSummarizer
from dance_mirror.storage.motion_library import DancePackage
from dance_mirror.workers.base import CancellableWorker

LOGGER = logging.getLogger(__name__)


class CloudSummaryWorker(CancellableWorker):
    """Generate a cloud report only from an explicit structured summary."""

    summaryReady = pyqtSignal(str)

    def __init__(self, summary: Mapping[str, Any], config: CloudConfig) -> None:
        super().__init__()
        self.summary = dict(summary)
        self.config = config

    def run(self) -> None:
        try:
            if self._stopped:
                self.cancelled.emit()
                return
            summarizer = CloudSummarizer(self.config)
            text = summarizer.summarize(self.summary)
            if self._stopped:
                self.cancelled.emit()
                return
            self.summaryReady.emit(text)
            self.finished.emit()
        except Exception as exc:
            LOGGER.exception("cloud summary failed")
            self.errorOccurred.emit(f"{type(exc).__name__}: {exc}")


class CloudCapabilityWorker(CancellableWorker):
    """Test one configured cloud capability off the Qt UI thread."""

    resultReady = pyqtSignal(str, bool, float)

    def __init__(self, capability: str, config: Mapping[str, Any]) -> None:
        super().__init__()
        self.capability = str(capability).strip().lower()
        self.config = dict(config)

    def run(self) -> None:
        started = time.perf_counter()
        try:
            if self.capability == "llm":
                self._test_llm()
            elif self.capability in {"asr", "tts"}:
                self._test_audio_endpoint()
            else:
                raise ValueError(f"unsupported capability: {self.capability}")
            elapsed = time.perf_counter() - started
            self.resultReady.emit(f"连接成功，延迟 {elapsed * 1000:.0f} ms。", True, elapsed)
            self.finished.emit()
        except Exception as exc:
            elapsed = time.perf_counter() - started
            LOGGER.warning("cloud capability test failed: %s", exc)
            self.resultReady.emit(f"连接失败：{exc}", False, elapsed)
            self.finished.emit()

    def _test_llm(self) -> None:
        config = CloudConfig(
            base_url=str(self.config.get("base_url", "")),
            model=str(self.config.get("model", "")),
            api_key=str(self.config.get("api_key", "")),
            timeout_s=float(self.config.get("timeout_s", 30.0)),
            max_tokens=12,
            temperature=0.0,
        )
        text = CloudSummarizer(config).summarize(
            {"probe": "只回复连接正常", "overall_score": 0.0}
        )
        if not text.strip():
            raise RuntimeError("模型返回了空响应")

    def _test_audio_endpoint(self) -> None:
        api_key = str(self.config.get("api_key", "")).strip()
        if not api_key:
            raise ValueError("未填写 API Key")
        base_url = str(self.config.get("base_url", "")).rstrip("/")
        if not base_url:
            raise ValueError("未填写 Base URL")
        timeout = float(self.config.get("timeout_s", 30.0))
        response = httpx.get(
            f"{base_url}/models",
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=timeout,
        )
        response.raise_for_status()
        response.json()


class CloudCommandWorker(CancellableWorker):
    """Resolve one complex command without blocking the Qt GUI thread."""

    planReady = pyqtSignal(object)

    def __init__(
        self,
        text: str,
        config: CloudConfig,
        packages: tuple[DancePackage, ...] = (),
    ) -> None:
        super().__init__()
        self.text = str(text)[:500]
        self.config = config
        self.packages = packages

    def run(self) -> None:
        try:
            if self._stopped:
                self.cancelled.emit()
                return
            planner = CloudCommandPlanner(self.config, self.packages)
            plan = planner.plan(self.text)
            if self._stopped:
                self.cancelled.emit()
                return
            self.planReady.emit(plan)
            self.finished.emit()
        except Exception as exc:
            LOGGER.exception("cloud command planning failed")
            self.errorOccurred.emit(f"{type(exc).__name__}: {exc}")
