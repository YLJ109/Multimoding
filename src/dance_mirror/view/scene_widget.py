"""WebEngine-backed single-robot scene with a 2D camera overlay."""

from __future__ import annotations

import json
import logging
from contextlib import suppress

from PyQt6 import sip
from PyQt6.QtCore import QEvent, QTimer, QUrl, pyqtSignal
from PyQt6.QtGui import QResizeEvent
from PyQt6.QtWidgets import QVBoxLayout, QWidget

from dance_mirror.motion.retarget import RetargetedSkeleton
from dance_mirror.multimodal.preview import CameraPreviewPacket
from dance_mirror.renderer.render_bridge import LatestFrameRenderBridge
from dance_mirror.renderer.three_scene import (
    ROBOT_MODEL_LOCAL_FILE,
    THREE_LOCAL_FILE,
    build_three_scene_html,
    payload_as_javascript,
)
from dance_mirror.view.camera_preview import CameraPreview
from dance_mirror.view.skeleton_preview import SkeletonPreview

LOGGER = logging.getLogger(__name__)


def _javascript_string(value: str) -> str:
    return json.dumps(str(value), ensure_ascii=False)


class SceneWidget(QWidget):
    """Own one 3D robot stage and one isolated camera overlay."""

    sceneStateReady = pyqtSignal(object)

    def __init__(
        self,
        parent: QWidget | None = None,
        *,
        model_mode: str = "overlay",
        render_fps: int = 60,
        camera_size_mode: str = "medium",
    ) -> None:
        super().__init__(parent)
        self._loaded = False
        self._pending_robot: str | None = None
        self._model_mode = model_mode
        self._skin = "default"
        self._theme = "studio"
        self._interface_theme = "dark"
        self._action = "idle"
        self._action_paused = False
        self._imitation_scope = "full_body"
        self._root_mode = "none"
        self._motion_preset = "balanced"
        self._scene_active = False
        self._model_url = (
            QUrl.fromLocalFile(str(ROBOT_MODEL_LOCAL_FILE)).toString()
            if ROBOT_MODEL_LOCAL_FILE.is_file()
            else ""
        )
        self._low_power = False
        self._web_view: QWidget | None = None
        self._fallback: SkeletonPreview | None = None
        self._render_bridge: LatestFrameRenderBridge | None = None
        self._render_fps = max(30, min(60, int(render_fps)))
        self._render_timer = QTimer(self)
        self._configure_render_fps(render_fps)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        if not self._try_create_web_view(layout):
            self._fallback = SkeletonPreview(self)
            layout.addWidget(self._fallback)

        self.camera_preview = CameraPreview(self, size_mode=camera_size_mode)
        self.camera_preview.raise_()

    def _camera_preview_alive(self) -> bool:
        preview = getattr(self, "camera_preview", None)
        return preview is not None and not sip.isdeleted(preview)
        self.camera_preview.set_placeholder("等待摄像头")
        self._position_camera_preview()

    def _configure_render_fps(self, render_fps: int) -> None:
        fps = max(30, min(60, int(render_fps)))
        self._render_fps = fps
        self._render_timer.setInterval(max(1, round(1000 / fps)))
        with suppress(TypeError):
            self._render_timer.timeout.disconnect()
        self._render_timer.timeout.connect(self._flush_render_commands)

    def _try_create_web_view(self, layout: QVBoxLayout) -> bool:
        try:
            from PyQt6.QtWebEngineCore import QWebEngineSettings
            from PyQt6.QtWebEngineWidgets import QWebEngineView
        except ImportError:
            LOGGER.info("PyQt6-WebEngine is unavailable; using native skeleton preview")
            return False
        view = QWebEngineView(self)
        view.settings().setAttribute(
            QWebEngineSettings.WebAttribute.LocalContentCanAccessFileUrls,
            True,
        )
        base_url = QUrl.fromLocalFile(str(THREE_LOCAL_FILE))
        view.loadFinished.connect(self._on_load_finished)
        view.setHtml(build_three_scene_html(), base_url)
        self._web_view = view
        layout.addWidget(view)
        self._render_bridge = LatestFrameRenderBridge(
            self._dispatch_render_batch,
            min_interval_s=1.0 / 60.0,
            max_pending_age_s=0.300,
        )
        self._render_timer.start()
        return True

    def _on_load_finished(self, ok: bool) -> None:
        self._loaded = ok
        if not ok:
            LOGGER.warning("3D scene HTML failed to load")
            return
        if self._pending_robot is not None:
            self._run_js(self._pending_robot, channel="robot")
        self._apply_scene_configuration()
        self._run_js(
            f"window.updateSceneStatus({_javascript_string('3D 机器人舞台已就绪')});",
            channel="status",
        )
        self._flush_render_commands(force=True)

    def _apply_scene_configuration(self) -> None:
        self._run_js(
            f"window.setModelMode({_javascript_string(self._model_mode)});",
            channel="mode",
        )
        self._run_js(f"window.setSkin({_javascript_string(self._skin)});", channel="skin")
        self._run_js(
            f"window.setRobotModelUrl({_javascript_string(self._model_url)});",
            channel="robot-model",
        )
        self._run_js(
            f"window.setSceneTheme({_javascript_string(self._theme)});",
            channel="theme",
        )
        self._run_js(f"window.playAction({_javascript_string(self._action)});", channel="action")
        paused = "true" if self._action_paused else "false"
        self._run_js(f"window.setActionPaused({paused});", channel="action-paused")
        self._run_js(
            f"window.setImitationScope({_javascript_string(self._imitation_scope)});",
            channel="scope",
        )
        self._run_js(
            f"window.setRootMotion({_javascript_string(self._root_mode)});",
            channel="root-motion",
        )
        self._run_js(
            f"window.setMotionPreset({_javascript_string(self._motion_preset)});",
            channel="motion-preset",
        )
        low_power = "true" if self._low_power else "false"
        self._run_js(f"window.setLowPower({low_power});", channel="low-power")
        self._run_js(
            f"window.setRenderFps({self._render_fps});",
            channel="render-fps",
        )
        self._run_js(
            f"window.setInterfaceTheme({_javascript_string(self._interface_theme)});",
            channel="interface-theme",
        )
        active = "true" if self._scene_active else "false"
        self._run_js(f"window.setSceneActive({active});", channel="scene-active")

    def set_robot(self, skeleton: RetargetedSkeleton) -> None:
        """Set the standard or live robot pose; the user never enters 3D."""
        if self._fallback is not None:
            self._fallback.set_reference(skeleton)
            return
        command = payload_as_javascript("updateRobot", skeleton)
        self._pending_robot = command
        if self._loaded:
            self._run_js(command, channel="robot")

    def set_reference(self, skeleton: RetargetedSkeleton) -> None:
        """Compatibility alias retained for older call sites."""
        self.set_robot(skeleton)

    def clear_robot(self) -> None:
        self._pending_robot = None
        if self._fallback is not None:
            self._fallback.clear_reference()
            return
        if self._loaded:
            self._run_js("window.clearRobot();", channel="robot")

    def clear_reference(self) -> None:
        self.clear_robot()

    def set_camera_packet(self, packet: CameraPreviewPacket) -> None:
        if not self._camera_preview_alive():
            return
        self.camera_preview.set_packet(packet)

    def clear_camera(self) -> None:
        if not self._camera_preview_alive():
            return
        self.camera_preview.clear()

    def set_camera_size_mode(self, mode: str) -> None:
        if not self._camera_preview_alive():
            return
        self.camera_preview.set_size_mode(mode)
        self._position_camera_preview()
        self.camera_preview.raise_()

    def set_model_mode(self, mode: str) -> None:
        self._model_mode = mode if mode in {"skeleton", "body", "overlay"} else "overlay"
        if self._fallback is not None:
            return
        if self._loaded:
            self._run_js(
                f"window.setModelMode({_javascript_string(self._model_mode)});",
                channel="mode",
            )

    def set_model_url(self, url: str) -> None:
        self._model_url = str(url or "")
        if self._loaded:
            self._run_js(
                f"window.setRobotModelUrl({_javascript_string(self._model_url)});",
                channel="robot-model",
            )

    def set_skin(self, name: str) -> None:

        self._skin = str(name or "default").lower()
        if self._loaded:
            self._run_js(f"window.setSkin({_javascript_string(self._skin)});", channel="skin")

    def set_scene_theme(self, name: str) -> None:
        self._theme = str(name or "studio").lower()
        if self._loaded:
            self._run_js(
                f"window.setSceneTheme({_javascript_string(self._theme)});",
                channel="theme",
            )

    def set_theme_mode(self, theme: str) -> None:
        mode = "dark" if str(theme).lower() == "dark" else "light"
        self._interface_theme = mode
        if self._camera_preview_alive():
            self.camera_preview.set_theme_mode(mode)
        if self._loaded:
            self._run_js(
                f"window.setInterfaceTheme({_javascript_string(mode)});",
                channel="interface-theme",
            )
        if self._fallback is not None:
            self._fallback.set_theme_mode(mode)

    def play_action(self, name: str) -> None:
        self._action = str(name or "idle").lower()
        if self._loaded:
            self._run_js(
                f"window.playAction({_javascript_string(self._action)});",
                channel="action",
            )

    def set_action_paused(self, paused: bool) -> None:
        self._action_paused = bool(paused)
        if self._loaded:
            value = "true" if self._action_paused else "false"
            self._run_js(f"window.setActionPaused({value});", channel="action-paused")

    def set_imitation_scope(self, scope: str) -> None:
        allowed = {"full_body", "upper_body", "lower_body", "hands", "head"}
        self._imitation_scope = scope if scope in allowed else "full_body"
        if self._loaded:
            self._run_js(
                f"window.setImitationScope({_javascript_string(self._imitation_scope)});",
                channel="scope",
            )

    def set_root_motion(self, mode: str) -> None:
        self._root_mode = mode if mode in {"none", "sway", "planar"} else "none"
        if self._loaded:
            self._run_js(
                f"window.setRootMotion({_javascript_string(self._root_mode)});",
                channel="root-motion",
            )

    def set_motion_preset(self, name: str) -> None:
        allowed = {"low_latency", "balanced", "smooth"}
        self._motion_preset = name if name in allowed else "balanced"
        if self._loaded:
            self._run_js(
                f"window.setMotionPreset({_javascript_string(self._motion_preset)});",
                channel="motion-preset",
            )

    def reset_camera(self) -> None:
        if self._loaded:
            self._run_js("window.resetRobotCamera();", channel="camera")

    def set_low_power(self, enabled: bool) -> None:
        self._low_power = bool(enabled)
        if self._loaded:
            value = "true" if self._low_power else "false"
            self._run_js(f"window.setLowPower({value});", channel="low-power")

    def set_render_fps(self, fps: int) -> None:
        if self._render_bridge is not None:
            self._render_bridge = LatestFrameRenderBridge(
                self._dispatch_render_batch,
                min_interval_s=1.0 / max(30, min(60, int(fps))),
                max_pending_age_s=0.300,
            )
        self._configure_render_fps(fps)
        if self._loaded:
            self._run_js(f"window.setRenderFps({self._render_fps});", channel="render-fps")

    def request_scene_state(self) -> None:
        view = self._web_view
        if view is None or not self._loaded:
            self.sceneStateReady.emit({})
            return
        view.page().runJavaScript(
            "window.getSceneState ? window.getSceneState() : {}",
            self.sceneStateReady.emit,
        )  # type: ignore[attr-defined]

    def set_status(self, text: str) -> None:
        if self._fallback is not None:
            self._fallback.setToolTip(text)
            return
        if self._loaded:
            self._run_js(
                f"window.updateSceneStatus({_javascript_string(text)});",
                channel="status",
            )

    def _run_js(self, script: str, *, channel: str = "command") -> None:
        bridge = self._render_bridge
        if bridge is None:
            self._dispatch_render_batch(script)
            return
        bridge.submit(channel, script)

    def _dispatch_render_batch(self, script: str) -> None:
        view = self._web_view
        if view is None:
            return
        if sip.isdeleted(view):
            return
        with suppress(RuntimeError):
            view.page().runJavaScript(script)  # type: ignore[attr-defined]

    def _flush_render_commands(self, *, force: bool = False) -> None:
        bridge = self._render_bridge
        if bridge is not None:
            bridge.flush(force=force)

    def resizeEvent(self, event: QResizeEvent) -> None:  # noqa: N802 - Qt API
        super().resizeEvent(event)
        self._position_camera_preview()

    def showEvent(self, event: object) -> None:  # noqa: N802 - Qt API
        super().showEvent(event)  # type: ignore[misc]
        self._scene_active = True
        if self._loaded:
            self._run_js("window.setSceneActive(true);", channel="scene-active")

    def hideEvent(self, event: object) -> None:  # noqa: N802 - Qt API
        self._scene_active = False
        if self._loaded:
            self._run_js("window.setSceneActive(false);", channel="scene-active")
        super().hideEvent(event)  # type: ignore[misc]

    def event(self, event: QEvent) -> bool:
        if event.type() == QEvent.Type.ChildAdded:
            child = getattr(event, "child", lambda: None)()
            if child is getattr(self, "camera_preview", None):
                QTimer.singleShot(0, self._position_camera_preview)
        return super().event(event)

    def _position_camera_preview(self) -> None:
        preview = getattr(self, "camera_preview", None)
        if preview is not None and sip.isdeleted(preview):
            return
        if preview is None or preview.size_mode == "collapsed":
            return
        preview.move(16, 16)
        preview.raise_()

    def stop(self) -> None:
        """Stop page timers and pending render commands cleanly."""
        self._scene_active = False
        with suppress(RuntimeError):
            self._render_timer.stop()
        if self._render_bridge is not None:
            self._render_bridge.clear()
        if self._web_view is not None:
            view = self._web_view
            with suppress(RuntimeError):
                if hasattr(view, "stop"):
                    view.stop()  # type: ignore[attr-defined]
                if hasattr(view, "setUrl"):
                    view.setUrl(QUrl("about:blank"))  # type: ignore[attr-defined]
