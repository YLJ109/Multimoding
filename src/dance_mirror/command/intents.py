"""Pure command contracts for speech, buttons, and LLM intent resolution."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import IntEnum, StrEnum
from typing import Any


class RobotCommand(StrEnum):
    """The only action names the robot runtime accepts."""

    START_IMITATION = "start_imitation"
    STOP_IMITATION = "stop_imitation"
    PAUSE_IMITATION = "pause_imitation"
    RESUME_IMITATION = "resume_imitation"
    SET_IMITATION_SCOPE = "set_imitation_scope"
    SET_MIRROR = "set_mirror"
    SET_SMOOTHING = "set_smoothing"
    RESET_POSE = "reset_pose"
    PLAY_DANCE = "play_dance"
    PAUSE_DANCE = "pause_dance"
    RESUME_DANCE = "resume_dance"
    SET_PLAYBACK_SPEED = "set_playback_speed"
    MOVE = "move"
    TURN = "turn"
    RUN = "run"
    JUMP = "jump"
    WAVE = "wave"
    CHANGE_SKIN = "change_skin"
    CHANGE_SCENE = "change_scene"
    SET_CAMERA = "set_camera"
    EMERGENCY_STOP = "emergency_stop"
    HELP = "help"
    UNKNOWN = "unknown"


class ImitationScope(StrEnum):
    """Skeleton groups that may be driven by live imitation."""

    FULL_BODY = "full_body"
    UPPER_BODY = "upper_body"
    LOWER_BODY = "lower_body"
    HANDS = "hands"
    HEAD = "head"


class SafetyClass(StrEnum):
    """How a command must be validated before execution."""

    SAFE_FAST = "safe_fast"
    NORMAL = "normal"
    RESTRICTED = "restricted"


class CommandPriority(IntEnum):
    """Higher-priority commands override lower-priority motion layers."""

    IDLE = 0
    APPEARANCE = 20
    PANEL = 30
    DETERMINISTIC_ACTION = 40
    IMITATION = 60
    PAUSE = 80
    SAFETY = 100


@dataclass(frozen=True, slots=True)
class CommandResult:
    """A validated, pure-data command ready for the actor runtime."""

    command: RobotCommand
    parameters: dict[str, Any] = field(default_factory=dict)
    priority: CommandPriority = CommandPriority.PANEL
    safety_class: SafetyClass = SafetyClass.NORMAL
    confidence: float = 1.0
    source: str = "local"
    raw_text: str = ""
    acknowledgement: str = ""
    trace_id: str = ""

    def __post_init__(self) -> None:
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError("command confidence must be in [0, 1]")
        if self.command is RobotCommand.PLAY_DANCE:
            package_id = str(self.parameters.get("package_id", "")).strip()
            if not package_id:
                raise ValueError("PLAY_DANCE requires a package_id")

    @property
    def is_safe(self) -> bool:
        return self.command is not RobotCommand.UNKNOWN


@dataclass(frozen=True, slots=True)
class CommandConflict:
    """Explain why a valid command was not allowed into the motion stack."""

    command: RobotCommand
    reason: str

    def __str__(self) -> str:
        return f"{self.command.value}: {self.reason}"
