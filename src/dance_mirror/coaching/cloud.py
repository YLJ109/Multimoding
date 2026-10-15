"""OpenAI-compatible cloud coaching and bounded command planning."""

from __future__ import annotations

import hashlib
import json
import logging
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Any

import httpx

from dance_mirror.coaching.prompts import (
    COACH_REPORT_SYSTEM_PROMPT,
    COMMAND_PLANNER_SYSTEM_PROMPT,
    coach_report_prompt,
    command_planner_prompt,
)
from dance_mirror.command.parser import (
    CLOUD_COMMAND_WHITELIST,
    LocalCommandParser,
    ValidatedCommandPlan,
)
from dance_mirror.errors import CloudServiceError
from dance_mirror.storage.motion_library import DancePackage

LOGGER = logging.getLogger(__name__)


@dataclass(slots=True)
class CloudConfig:
    """Connection settings for an OpenAI-compatible chat endpoint."""

    base_url: str = "https://api.openai.com/v1"
    model: str = "gpt-4o-mini"
    api_key: str = ""
    timeout_s: float = 30.0
    max_tokens: int = 500
    temperature: float = 0.3

    def endpoint(self) -> str:
        return f"{self.base_url.rstrip('/')}/chat/completions"


def _chat_completion(
    config: CloudConfig,
    *,
    system_prompt: str,
    user_prompt: str,
    temperature: float,
    max_tokens: int,
) -> str:
    if not config.api_key:
        raise CloudServiceError("cloud API key is not configured")
    body = {
        "model": config.model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "temperature": temperature,
        "max_tokens": max_tokens,
    }
    try:
        with httpx.Client(timeout=config.timeout_s) as client:
            response = client.post(
                config.endpoint(),
                headers={
                    "Authorization": f"Bearer {config.api_key}",
                    "Content-Type": "application/json",
                },
                json=body,
            )
            response.raise_for_status()
            data = response.json()
    except (httpx.HTTPError, ValueError) as exc:
        raise CloudServiceError(f"cloud request failed: {exc}") from exc
    try:
        content = data["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as exc:
        raise CloudServiceError("cloud response has an unexpected shape") from exc
    if not isinstance(content, str) or not content.strip():
        raise CloudServiceError("cloud response was empty")
    return content.strip()


class CloudSummarizer:
    """Generate a short report from structured, non-video training summaries."""

    def __init__(self, config: CloudConfig) -> None:
        self.config = config
        self._cache: dict[str, str] = {}

    def summarize(self, summary: Mapping[str, Any]) -> str:
        payload_text = json.dumps(summary, ensure_ascii=False, sort_keys=True)
        cache_key = hashlib.sha256(payload_text.encode("utf-8")).hexdigest()
        if cache_key in self._cache:
            return self._cache[cache_key]
        text = _chat_completion(
            self.config,
            system_prompt=COACH_REPORT_SYSTEM_PROMPT,
            user_prompt=coach_report_prompt(dict(summary)),
            temperature=self.config.temperature,
            max_tokens=self.config.max_tokens,
        )
        self._cache[cache_key] = text
        return text


class CloudCommandPlanner:
    """Request a V6 JSON plan and validate it locally before returning it."""

    def __init__(self, config: CloudConfig, packages: Iterable[DancePackage] = ()) -> None:
        self.config = config
        self._packages = tuple(packages)
        self._parser = LocalCommandParser(self._packages)

    def set_packages(self, packages: Iterable[DancePackage]) -> None:
        self._packages = tuple(packages)
        self._parser.set_packages(self._packages)

    def plan(self, text: str) -> ValidatedCommandPlan:
        package_payload = tuple(
            {"package_id": item.package_id, "name": item.name}
            for item in self._packages[:100]
            if item.ready
        )
        prompt = command_planner_prompt(
            text,
            allowed_commands=tuple(
                sorted(command.value for command in CLOUD_COMMAND_WHITELIST)
            ),
            packages=package_payload,
        )
        response = _chat_completion(
            self.config,
            system_prompt=COMMAND_PLANNER_SYSTEM_PROMPT,
            user_prompt=prompt,
            temperature=0.0,
            max_tokens=min(self.config.max_tokens, 500),
        )
        plan = self._parser.parse_plan_json(response)
        if not plan.valid:
            LOGGER.warning("cloud command plan rejected by local validation")
            raise CloudServiceError(plan.reply_text)
        return plan
