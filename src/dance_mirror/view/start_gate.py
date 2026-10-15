"""Deterministic gate for starting a dance session after body and OK checks."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class DanceStartGate:
    """Require stable full-body placement and a sustained OK gesture."""

    min_readiness: float = 0.78
    min_ok_confidence: float = 0.55
    ready_hold_s: float = 0.8
    ok_hold_s: float = 0.7
    _armed: bool = False
    _ready_since: float | None = None
    _ok_since: float | None = None
    _hand_present: bool = False
    _last_reason: str = "点击开始准备，系统会检查全身就位和 OK 手势。"

    @property
    def armed(self) -> bool:
        return self._armed

    @property
    def reason(self) -> str:
        return self._last_reason

    def reset(self) -> None:
        self._armed = False
        self._ready_since = None
        self._ok_since = None
        self._hand_present = False
        self._last_reason = "点击开始准备，系统会检查全身就位和 OK 手势。"

    def arm(self, now_s: float) -> None:
        del now_s
        self._armed = True
        self._ready_since = None
        self._ok_since = None
        self._hand_present = False
        self._last_reason = "请后退到全身进入画面。"

    def observe_readiness(
        self,
        *,
        score: float,
        single_person: bool,
        full_body: bool,
        now_s: float,
    ) -> bool:
        if not self._armed:
            return False
        eligible = (
            bool(single_person)
            and bool(full_body)
            and float(score) >= self.min_readiness
        )
        if eligible:
            if self._ready_since is None:
                self._ready_since = float(now_s)
        else:
            self._ready_since = None
        return self._evaluate(now_s)

    def observe_hands(self, hand_present: bool) -> None:
        self._hand_present = bool(hand_present)
        if not self._hand_present:
            self._ok_since = None

    def observe_gesture(
        self,
        name: str,
        confidence: float,
        now_s: float,
    ) -> bool:
        if not self._armed:
            return False
        is_ok = (
            self._hand_present
            and str(name).strip().lower() == "ok"
            and float(confidence) >= self.min_ok_confidence
        )
        if is_ok:
            if self._ok_since is None:
                self._ok_since = float(now_s)
        else:
            self._ok_since = None
        return self._evaluate(now_s)

    def _evaluate(self, now_s: float) -> bool:
        if not self._armed:
            return False
        now = float(now_s)
        if self._ready_since is None:
            self._last_reason = "请让头部和双脚都进入画面，并保持一个人。"
            return False
        ready_for = now - self._ready_since
        if ready_for < self.ready_hold_s:
            self._last_reason = f"就位稳定中，还需 {self.ready_hold_s - ready_for:.1f} 秒。"
            return False
        if self._ok_since is None:
            self._last_reason = "就位完成，请保持清晰的 OK 手势。"
            return False
        ok_for = now - self._ok_since
        if ok_for < self.ok_hold_s:
            self._last_reason = f"正在确认 OK 手势，还需 {self.ok_hold_s - ok_for:.1f} 秒。"
            return False
        self._armed = False
        self._last_reason = "就位和 OK 手势已确认，准备开始。"
        return True
