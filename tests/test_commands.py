"""Command parser, queue, and cloud-plan safety contracts."""

from __future__ import annotations

import json
from types import SimpleNamespace

from dance_mirror.command.intents import (
    CommandPriority,
    CommandResult,
    RobotCommand,
    SafetyClass,
)
from dance_mirror.command.parser import LocalCommandParser
from dance_mirror.command.queue import CommandQueue


def _packages() -> tuple[SimpleNamespace, ...]:
    return (SimpleNamespace(package_id="demo-1", name="宿舍律动"),)


def test_speed_command_is_parsed_and_clamped() -> None:
    parser = LocalCommandParser()
    result = parser.parse("把速度调到 1.5 倍")
    assert result.command is RobotCommand.SET_PLAYBACK_SPEED
    assert result.parameters["speed"] == 1.5

    clamped = parser.parse("速度 9 倍")
    assert clamped.parameters["speed"] == 2.0


def test_cloud_plan_is_whitelisted_and_package_checked() -> None:
    parser = LocalCommandParser(_packages())  # type: ignore[arg-type]
    payload = {
        "steps": [
            {"kind": "play_dance", "parameters": {"package_id": "demo-1"}, "depends_on": []},
            {"kind": "set_playback_speed", "parameters": {"speed": 1.25}, "depends_on": [0]},
        ],
        "reply_text": "开始播放并调整速度。",
        "confidence": 0.91,
    }
    plan = parser.parse_plan_json(json.dumps(payload, ensure_ascii=False))
    assert plan.valid
    assert [item.command for item in plan.commands] == [
        RobotCommand.PLAY_DANCE,
        RobotCommand.SET_PLAYBACK_SPEED,
    ]
    assert plan.commands[0].parameters["package_name"] == "宿舍律动"


def test_cloud_plan_rejects_safety_and_unknown_parameters() -> None:
    parser = LocalCommandParser(_packages())  # type: ignore[arg-type]
    emergency = parser.parse_plan_json(
        json.dumps(
            {
                "steps": [{"kind": "emergency_stop", "parameters": {}}],
                "reply_text": "",
                "confidence": 0.99,
            }
        )
    )
    assert not emergency.valid
    assert emergency.commands == ()

    escaped = parser.parse_plan_json(
        json.dumps(
            {
                "steps": [
                    {
                        "kind": "change_skin",
                        "parameters": {"skin": "default", "path": "/tmp/x"},
                    }
                ]
            }
        )
    )
    assert not escaped.valid


def test_single_command_json_uses_enums_and_scalar_parameters() -> None:
    parser = LocalCommandParser()
    valid = parser.parse_llm_json('{"command":"wave","parameters":{},"confidence":0.8}')
    assert valid.command is RobotCommand.WAVE

    rejected = parser.parse_llm_json(
        '{"command":"move","parameters":{"direction":{"nested":true}}}'
    )
    assert rejected.command is RobotCommand.UNKNOWN


def test_command_queue_prioritizes_safety_and_expires_panel_commands(
    monkeypatch: object,
) -> None:
    clock = [10.0]
    monkeypatch.setattr(  # type: ignore[attr-defined]
        "dance_mirror.command.queue.time.monotonic",
        lambda: clock[0],
    )
    queue = CommandQueue(default_ttl_s=0.2)
    appearance = CommandResult(
        command=RobotCommand.CHANGE_SKIN,
        parameters={"skin": "gold"},
        priority=CommandPriority.APPEARANCE,
        safety_class=SafetyClass.NORMAL,
    )
    safety = CommandResult(
        command=RobotCommand.PAUSE_DANCE,
        priority=CommandPriority.SAFETY,
        safety_class=SafetyClass.SAFE_FAST,
    )
    assert queue.push(appearance)
    assert queue.push(safety)
    assert queue.pop() is safety
    clock[0] = 10.3
    assert queue.size == 0
    assert queue.discarded >= 1
