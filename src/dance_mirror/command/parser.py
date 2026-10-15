"""Deterministic Chinese command parser with a validated LLM fallback."""

from __future__ import annotations

import json
import math
import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Any
from uuid import uuid4

from dance_mirror.command.intents import (
    CommandPriority,
    CommandResult,
    ImitationScope,
    RobotCommand,
    SafetyClass,
)
from dance_mirror.storage.motion_library import DancePackage

_SPEED_RE = re.compile(r"(?P<speed>[0-9]+(?:\.[0-9]+)?)\s*(?:倍|x)", re.IGNORECASE)
_NUMBER_RE = re.compile(r"(?P<number>[0-9]+(?:\.[0-9]+)?)")

_SCENE_VALUES = frozenset({"studio", "dorm", "neon"})
_SKIN_VALUES = frozenset({"default", "cyber", "gold", "azure", "crimson"})
_CAMERA_VIEW_VALUES = frozenset(
    {"front", "back", "left_profile", "right_profile", "three_quarter", "unknown"}
)
_PREVIEW_SIZE_VALUES = frozenset({"small", "medium", "large", "collapsed"})
_SCOPE_VALUES = frozenset(item.value for item in ImitationScope)
_DIRECTION_VALUES = frozenset({"forward", "backward", "left", "right"})

# Safety controls intentionally remain local-only. A cloud response can never
# stop, pause, or bypass the local deterministic command path.
CLOUD_COMMAND_WHITELIST: frozenset[RobotCommand] = frozenset(
    {
        RobotCommand.START_IMITATION,
        RobotCommand.SET_IMITATION_SCOPE,
        RobotCommand.SET_MIRROR,
        RobotCommand.SET_SMOOTHING,
        RobotCommand.RESET_POSE,
        RobotCommand.PLAY_DANCE,
        RobotCommand.PAUSE_DANCE,
        RobotCommand.RESUME_DANCE,
        RobotCommand.SET_PLAYBACK_SPEED,
        RobotCommand.MOVE,
        RobotCommand.TURN,
        RobotCommand.RUN,
        RobotCommand.JUMP,
        RobotCommand.WAVE,
        RobotCommand.CHANGE_SKIN,
        RobotCommand.CHANGE_SCENE,
        RobotCommand.SET_CAMERA,
    }
)

_LOCAL_ONLY_COMMANDS: frozenset[RobotCommand] = frozenset(
    {
        RobotCommand.EMERGENCY_STOP,
        RobotCommand.STOP_IMITATION,
        RobotCommand.PAUSE_IMITATION,
        RobotCommand.RESUME_IMITATION,
    }
)


@dataclass(frozen=True, slots=True)
class ValidatedCommandPlan:
    """A bounded multi-step plan that passed local whitelist validation."""

    commands: tuple[CommandResult, ...] = ()
    reply_text: str = ""
    confidence: float = 0.0
    valid: bool = True

    def __post_init__(self) -> None:
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError("plan confidence must be in [0, 1]")


@dataclass(frozen=True, slots=True)
class _Rule:
    command: RobotCommand
    words: tuple[str, ...]
    parameters: Mapping[str, Any] | None = None
    priority: CommandPriority = CommandPriority.PANEL
    safety: SafetyClass = SafetyClass.NORMAL
    acknowledgement: str = ""


_RULES: tuple[_Rule, ...] = (
    _Rule(
        RobotCommand.EMERGENCY_STOP,
        ("紧急停止", "急停", "停下", "停止所有", "安全停止"),
        priority=CommandPriority.SAFETY,
        safety=SafetyClass.SAFE_FAST,
        acknowledgement="已紧急停止。",
    ),
    _Rule(
        RobotCommand.STOP_IMITATION,
        ("停止模仿", "不要模仿", "结束模仿"),
        priority=CommandPriority.SAFETY,
        safety=SafetyClass.SAFE_FAST,
        acknowledgement="已停止模仿。",
    ),
    _Rule(
        RobotCommand.PAUSE_IMITATION,
        ("暂停模仿", "暂停", "别动"),
        priority=CommandPriority.PAUSE,
        safety=SafetyClass.SAFE_FAST,
        acknowledgement="已暂停。",
    ),
    _Rule(
        RobotCommand.RESUME_IMITATION,
        ("继续模仿", "继续", "恢复"),
        acknowledgement="继续模仿。",
    ),
    _Rule(
        RobotCommand.START_IMITATION,
        ("开始模仿我", "开始模仿", "模仿我", "跟着我", "复制我的动作"),
        priority=CommandPriority.IMITATION,
        acknowledgement="开始实时模仿。",
    ),
    _Rule(
        RobotCommand.SET_IMITATION_SCOPE,
        ("只模仿上半身", "上半身", "上面"),
        parameters={"scope": ImitationScope.UPPER_BODY.value},
        acknowledgement="模仿范围切换为上半身。",
    ),
    _Rule(
        RobotCommand.SET_IMITATION_SCOPE,
        ("只模仿下半身", "下半身", "腿"),
        parameters={"scope": ImitationScope.LOWER_BODY.value},
        acknowledgement="模仿范围切换为下半身。",
    ),
    _Rule(
        RobotCommand.SET_IMITATION_SCOPE,
        ("只模仿手", "手部"),
        parameters={"scope": ImitationScope.HANDS.value},
        acknowledgement="模仿范围切换为手部。",
    ),
    _Rule(
        RobotCommand.SET_IMITATION_SCOPE,
        ("只模仿头", "头部"),
        parameters={"scope": ImitationScope.HEAD.value},
        acknowledgement="模仿范围切换为头部。",
    ),
    _Rule(
        RobotCommand.SET_IMITATION_SCOPE,
        ("全身模仿", "模仿全身", "全身"),
        parameters={"scope": ImitationScope.FULL_BODY.value},
        acknowledgement="模仿范围切换为全身。",
    ),
    _Rule(
        RobotCommand.SET_MIRROR,
        ("镜像我", "开启镜像", "打开镜像", "镜像"),
        parameters={"enabled": True},
        acknowledgement="已开启镜像。",
    ),
    _Rule(
        RobotCommand.SET_MIRROR,
        ("关闭镜像", "不要镜像"),
        parameters={"enabled": False},
        acknowledgement="已关闭镜像。",
    ),
    _Rule(
        RobotCommand.SET_SMOOTHING,
        ("减少抖动", "更平滑", "提高平滑", "平滑一点"),
        parameters={"smoothing": 0.82},
        acknowledgement="已提高动作平滑。",
    ),
    _Rule(
        RobotCommand.SET_SMOOTHING,
        ("更灵敏", "减少平滑", "反应快一点"),
        parameters={"smoothing": 0.25},
        acknowledgement="已提高动作灵敏度。",
    ),
    _Rule(
        RobotCommand.RESET_POSE,
        ("重置姿势", "回到待机", "复位"),
        acknowledgement="机器人已回到待机。",
    ),
    _Rule(
        RobotCommand.PAUSE_DANCE,
        ("暂停舞蹈", "舞蹈暂停"),
        priority=CommandPriority.PAUSE,
        acknowledgement="舞蹈已暂停。",
    ),
    _Rule(
        RobotCommand.RESUME_DANCE,
        ("继续舞蹈", "恢复舞蹈"),
        acknowledgement="继续播放舞蹈。",
    ),
    _Rule(
        RobotCommand.PLAY_DANCE,
        ("跳这个舞", "播放舞蹈", "跳舞包", "开始跳舞"),
        acknowledgement="开始播放舞蹈包。",
    ),
    _Rule(RobotCommand.WAVE, ("挥挥手", "挥手", "打个招呼", "你好"), acknowledgement="机器人挥手。"),
    _Rule(RobotCommand.RUN, ("跑起来", "跑步", "跑"), acknowledgement="机器人开始跑步。"),
    _Rule(RobotCommand.MOVE, ("向前走", "走过去", "走一走", "行走", "走"), acknowledgement="机器人开始行走。"),
    _Rule(RobotCommand.JUMP, ("跳一下", "跳跃", "跳"), acknowledgement="机器人跳跃。"),
    _Rule(
        RobotCommand.CHANGE_SKIN,
        ("赛博皮肤", "赛博", "霓虹皮肤"),
        parameters={"skin": "cyber"},
        priority=CommandPriority.APPEARANCE,
        acknowledgement="已切换赛博皮肤。",
    ),
    _Rule(
        RobotCommand.CHANGE_SKIN,
        ("金色皮肤", "金色", "冠军皮肤"),
        parameters={"skin": "gold"},
        priority=CommandPriority.APPEARANCE,
        acknowledgement="已切换金色皮肤。",
    ),
    _Rule(
        RobotCommand.CHANGE_SKIN,
        ("蓝色皮肤", "蓝色"),
        parameters={"skin": "azure"},
        priority=CommandPriority.APPEARANCE,
        acknowledgement="已切换蓝色皮肤。",
    ),
    _Rule(
        RobotCommand.CHANGE_SKIN,
        ("红色皮肤", "红色"),
        parameters={"skin": "crimson"},
        priority=CommandPriority.APPEARANCE,
        acknowledgement="已切换红色皮肤。",
    ),
    _Rule(
        RobotCommand.CHANGE_SKIN,
        ("默认皮肤", "恢复默认", "默认"),
        parameters={"skin": "default"},
        priority=CommandPriority.APPEARANCE,
        acknowledgement="已恢复默认皮肤。",
    ),
    _Rule(
        RobotCommand.CHANGE_SCENE,
        ("霓虹场景", "赛博场景"),
        parameters={"scene": "neon"},
        priority=CommandPriority.APPEARANCE,
        acknowledgement="已切换霓虹场景。",
    ),
    _Rule(
        RobotCommand.CHANGE_SCENE,
        ("宿舍场景", "安静场景"),
        parameters={"scene": "dorm"},
        priority=CommandPriority.APPEARANCE,
        acknowledgement="已切换宿舍场景。",
    ),
    _Rule(
        RobotCommand.CHANGE_SCENE,
        ("训练房", "舞台", "默认场景"),
        parameters={"scene": "studio"},
        priority=CommandPriority.APPEARANCE,
        acknowledgement="已切换训练舞台。",
    ),
)


def _bounded_confidence(value: object, default: float = 0.0) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return default
    if not math.isfinite(number):
        return default
    return max(0.0, min(1.0, number))


def _bounded_text(value: object, *, limit: int = 300) -> str:
    return str(value or "").strip()[:limit]


def _scalar_parameters(parameters: Mapping[object, object]) -> dict[str, object] | None:
    output: dict[str, object] = {}
    for raw_key, value in parameters.items():
        key = str(raw_key)
        if not key or len(key) > 40:
            return None
        if isinstance(value, bool) or isinstance(value, int | float) and math.isfinite(float(value)):
            output[key] = value
        elif isinstance(value, str):
            if len(value) > 120:
                return None
            output[key] = value.strip()
        elif value is None:
            output[key] = None
        else:
            return None
    return output


def _number(value: object, *, minimum: float, maximum: float) -> float | None:
    if isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(number) or not minimum <= number <= maximum:
        return None
    return number


def _validated_parameters(
    command: RobotCommand,
    raw: object,
    *,
    packages: Mapping[str, str],
) -> dict[str, object] | None:
    if raw is None:
        parameters: dict[str, object] = {}
    elif isinstance(raw, Mapping):
        parsed = _scalar_parameters(raw)
        if parsed is None:
            return None
        parameters = parsed
    else:
        return None

    if command is RobotCommand.PLAY_DANCE:
        if not set(parameters) <= {"package_id", "package_name"}:
            return None
        package_id = str(parameters.get("package_id", ""))
        if package_id not in packages:
            return None
        return {"package_id": package_id, "package_name": packages[package_id]}

    if command is RobotCommand.SET_PLAYBACK_SPEED:
        if not set(parameters) <= {"speed"}:
            return None
        speed = _number(parameters.get("speed", 1.0), minimum=0.5, maximum=2.0)
        return None if speed is None else {"speed": speed}

    if command is RobotCommand.SET_SMOOTHING:
        if not set(parameters) <= {"smoothing"}:
            return None
        smoothing = _number(parameters.get("smoothing"), minimum=0.0, maximum=0.95)
        return None if smoothing is None else {"smoothing": smoothing}

    if command is RobotCommand.SET_MIRROR:
        if set(parameters) != {"enabled"} or not isinstance(parameters["enabled"], bool):
            return None
        return {"enabled": parameters["enabled"]}

    if command is RobotCommand.SET_IMITATION_SCOPE:
        if set(parameters) != {"scope"}:
            return None
        scope = str(parameters["scope"])
        return {"scope": scope} if scope in _SCOPE_VALUES else None

    if command is RobotCommand.CHANGE_SKIN:
        if set(parameters) != {"skin"}:
            return None
        skin = str(parameters["skin"]).lower()
        return {"skin": skin} if skin in _SKIN_VALUES else None

    if command is RobotCommand.CHANGE_SCENE:
        if set(parameters) != {"scene"}:
            return None
        scene = str(parameters["scene"]).lower()
        return {"scene": scene} if scene in _SCENE_VALUES else None

    if command is RobotCommand.MOVE:
        if not set(parameters) <= {"direction"}:
            return None
        direction = str(parameters.get("direction", "forward")).lower()
        return {"direction": direction} if direction in _DIRECTION_VALUES else None

    if command is RobotCommand.TURN:
        if set(parameters) != {"direction"}:
            return None
        direction = str(parameters["direction"]).lower()
        return {"direction": direction} if direction in {"left", "right"} else None

    if command is RobotCommand.RUN:
        if not set(parameters) <= {"direction"}:
            return None
        direction = str(parameters.get("direction", "forward")).lower()
        return {"direction": direction} if direction in _DIRECTION_VALUES else None

    if command is RobotCommand.SET_CAMERA:
        if not set(parameters) <= {"view", "preview_size"} or not parameters:
            return None
        result: dict[str, object] = {}
        if "view" in parameters:
            view = str(parameters["view"]).lower()
            if view not in _CAMERA_VIEW_VALUES:
                return None
            result["view"] = view
        if "preview_size" in parameters:
            preview_size = str(parameters["preview_size"]).lower()
            if preview_size not in _PREVIEW_SIZE_VALUES:
                return None
            result["preview_size"] = preview_size
        return result

    if command in {
        RobotCommand.START_IMITATION,
        RobotCommand.RESET_POSE,
        RobotCommand.PAUSE_DANCE,
        RobotCommand.RESUME_DANCE,
        RobotCommand.JUMP,
        RobotCommand.WAVE,
    }:
        return {} if not parameters else None
    return None


def _priority_for(command: RobotCommand) -> CommandPriority:
    if command in {RobotCommand.PAUSE_DANCE, RobotCommand.PAUSE_IMITATION}:
        return CommandPriority.PAUSE
    if command in _LOCAL_ONLY_COMMANDS:
        return CommandPriority.SAFETY
    if command is RobotCommand.START_IMITATION:
        return CommandPriority.IMITATION
    if command in {
        RobotCommand.CHANGE_SKIN,
        RobotCommand.CHANGE_SCENE,
        RobotCommand.SET_CAMERA,
    }:
        return CommandPriority.APPEARANCE
    if command in {
        RobotCommand.PLAY_DANCE,
        RobotCommand.RESUME_DANCE,
        RobotCommand.MOVE,
        RobotCommand.TURN,
        RobotCommand.RUN,
        RobotCommand.JUMP,
        RobotCommand.WAVE,
        RobotCommand.RESET_POSE,
    }:
        return CommandPriority.DETERMINISTIC_ACTION
    return CommandPriority.PANEL


class LocalCommandParser:
    """Parse common commands without network access.

    Cloud plans are accepted only through :meth:`parse_plan_json`, which
    performs package, parameter, command, and dependency validation locally.
    """

    def __init__(self, packages: Iterable[DancePackage] = ()) -> None:
        self._packages = tuple(packages)

    def set_packages(self, packages: Iterable[DancePackage]) -> None:
        self._packages = tuple(packages)

    def parse(self, text: str, *, source: str = "voice") -> CommandResult:
        cleaned = " ".join(text.strip().split())
        if not cleaned:
            return self._unknown(text, source=source)
        lowered = cleaned.lower()

        for package in self._packages:
            if package.name and package.name.lower() in lowered:
                return CommandResult(
                    command=RobotCommand.PLAY_DANCE,
                    parameters={"package_id": package.package_id, "package_name": package.name},
                    priority=CommandPriority.DETERMINISTIC_ACTION,
                    safety_class=SafetyClass.NORMAL,
                    confidence=0.96,
                    source=source,
                    raw_text=text,
                    acknowledgement=f"开始播放《{package.name}》。",
                    trace_id=uuid4().hex,
                )

        speed_match = _SPEED_RE.search(cleaned)
        if speed_match and any(word in cleaned for word in ("速度", "倍速", "快", "慢")):
            speed = max(0.5, min(2.0, float(speed_match.group("speed"))))
            return CommandResult(
                command=RobotCommand.SET_PLAYBACK_SPEED,
                parameters={"speed": speed},
                confidence=0.98,
                source=source,
                raw_text=text,
                acknowledgement=f"播放速度已设为 {speed:.2f} 倍。",
                trace_id=uuid4().hex,
            )

        # Longest phrase first prevents "停" from swallowing "暂停模仿".
        ordered_rules = sorted(_RULES, key=lambda rule: max(map(len, rule.words)), reverse=True)
        for rule in ordered_rules:
            for word in sorted(rule.words, key=len, reverse=True):
                if word in cleaned:
                    return CommandResult(
                        command=rule.command,
                        parameters=dict(rule.parameters or {}),
                        priority=rule.priority,
                        safety_class=rule.safety,
                        confidence=0.98 if rule.safety is SafetyClass.SAFE_FAST else 0.94,
                        source=source,
                        raw_text=text,
                        acknowledgement=rule.acknowledgement,
                        trace_id=uuid4().hex,
                    )
        return self._unknown(text, source=source)

    def parse_llm_json(self, text: str, *, source: str = "cloud_llm") -> CommandResult:
        """Validate one JSON object supplied by an LLM or external adapter."""
        payload = self._json_object(text)
        if payload is None or "steps" in payload:
            return self._unknown(text, source=source)
        result = self._result_from_payload(
            payload,
            allowed_commands=CLOUD_COMMAND_WHITELIST,
            source=source,
            raw_text=text,
        )
        return result or self._unknown(text, source=source)

    def parse_plan_json(self, text: str, *, source: str = "cloud_llm") -> ValidatedCommandPlan:
        """Parse the V6 multi-step schema and reject the whole plan if unsafe."""
        payload = self._json_object(text)
        if payload is None:
            return self._invalid_plan()
        steps = payload.get("steps")
        if not isinstance(steps, list) or len(steps) > 6:
            return self._invalid_plan()
        reply_text = _bounded_text(payload.get("reply_text"), limit=240)
        confidence = _bounded_confidence(payload.get("confidence"), default=0.0)
        commands: list[CommandResult] = []
        package_map = {item.package_id: item.name for item in self._packages}
        dance_steps = 0
        for index, raw_step in enumerate(steps):
            if not isinstance(raw_step, Mapping):
                return self._invalid_plan()
            command_name = raw_step.get("kind", raw_step.get("command"))
            try:
                command = RobotCommand(str(command_name))
            except ValueError:
                return self._invalid_plan()
            if command not in CLOUD_COMMAND_WHITELIST:
                return self._invalid_plan()
            if command is RobotCommand.PLAY_DANCE:
                dance_steps += 1
                if dance_steps > 1:
                    return self._invalid_plan()
            dependencies = raw_step.get("depends_on", [])
            if not isinstance(dependencies, list):
                return self._invalid_plan()
            if any(
                isinstance(item, bool)
                or not isinstance(item, int)
                or item < 0
                or item >= index
                for item in dependencies
            ):
                return self._invalid_plan()
            parameters = _validated_parameters(
                command,
                raw_step.get("parameters", {}),
                packages=package_map,
            )
            if parameters is None:
                return self._invalid_plan()
            commands.append(
                self._command_result(
                    command,
                    parameters,
                    confidence=confidence,
                    source=source,
                    raw_text=text,
                )
            )
        if not commands and not reply_text:
            reply_text = "没有识别到可安全执行的命令，请换一种说法。"
        return ValidatedCommandPlan(
            commands=tuple(commands),
            reply_text=reply_text,
            confidence=confidence,
            valid=True,
        )

    def _result_from_payload(
        self,
        payload: Mapping[str, object],
        *,
        allowed_commands: frozenset[RobotCommand],
        source: str,
        raw_text: str,
    ) -> CommandResult | None:
        command_name = payload.get("kind", payload.get("command"))
        try:
            command = RobotCommand(str(command_name))
        except ValueError:
            return None
        if command not in allowed_commands:
            return None
        package_map = {item.package_id: item.name for item in self._packages}
        parameters = _validated_parameters(
            command,
            payload.get("parameters", {}),
            packages=package_map,
        )
        if parameters is None:
            return None
        return self._command_result(
            command,
            parameters,
            confidence=_bounded_confidence(payload.get("confidence"), default=0.8),
            source=source,
            raw_text=raw_text,
            acknowledgement=_bounded_text(
                payload.get("acknowledgement", payload.get("reply_text")),
                limit=240,
            ),
        )

    @staticmethod
    def _command_result(
        command: RobotCommand,
        parameters: dict[str, object],
        *,
        confidence: float,
        source: str,
        raw_text: str,
        acknowledgement: str = "",
    ) -> CommandResult:
        return CommandResult(
            command=command,
            parameters=parameters,
            priority=_priority_for(command),
            safety_class=SafetyClass.NORMAL,
            confidence=confidence,
            source=source,
            raw_text=raw_text,
            acknowledgement=acknowledgement,
            trace_id=uuid4().hex,
        )

    @staticmethod
    def _json_object(text: str) -> Mapping[str, object] | None:
        try:
            payload = json.loads(text)
        except (TypeError, json.JSONDecodeError):
            return None
        return payload if isinstance(payload, Mapping) else None

    @staticmethod
    def _invalid_plan() -> ValidatedCommandPlan:
        return ValidatedCommandPlan(
            commands=(),
            reply_text="云端返回的指令计划未通过本地安全校验。",
            confidence=0.0,
            valid=False,
        )

    @staticmethod
    def _unknown(text: str, *, source: str) -> CommandResult:
        return CommandResult(
            command=RobotCommand.UNKNOWN,
            parameters={},
            confidence=0.0,
            source=source,
            raw_text=text,
            acknowledgement="没有识别到安全命令，请换一种说法。",
            trace_id=uuid4().hex,
        )
