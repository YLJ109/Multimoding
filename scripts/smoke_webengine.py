"""Offscreen/desktop smoke test for the local Three.js renderer."""

from __future__ import annotations

import json
import os
import sys

os.environ.setdefault("QTWEBENGINE_CHROMIUM_FLAGS", "--enable-unsafe-swiftshader")

from PyQt6.QtCore import Qt, QTimer, QUrl
from PyQt6.QtWidgets import QApplication

from dance_mirror.view.scene_widget import SceneWidget


def main() -> int:
    print("creating Qt application", flush=True)
    QApplication.setAttribute(Qt.ApplicationAttribute.AA_ShareOpenGLContexts)
    app = QApplication(sys.argv)
    print("creating scene widget", flush=True)
    widget = SceneWidget()
    model_override = os.environ.get("DANCE_MIRROR_SMOKE_MODEL", "").strip()
    if model_override:
        widget.set_model_url(QUrl.fromLocalFile(model_override).toString())
    print("scene widget created", flush=True)
    widget.resize(960, 640)
    widget.show()
    view = widget._web_view  # noqa: SLF001 - smoke test boundary
    if view is None:
        print("FAIL: WebEngine view is unavailable")
        return 2

    result = {"ok": False, "message": "timeout"}
    checks = iter(("overlay", "skeleton", "body"))
    inspection_started = False
    interaction_checked = False
    screenshot_path = os.environ.get("DANCE_MIRROR_SMOKE_SCREENSHOT", "").strip()
    screenshot_saved = False

    def finish(ok: bool, message: str) -> None:
        result["ok"] = ok
        result["message"] = message
        print(("PASS: " if ok else "FAIL: ") + message, flush=True)
        # The CI-style desktop session can race Chromium teardown after a
        # JavaScript callback. The renderer result is already known here.
        os._exit(0 if ok else 1)

    def inspect(expected_mode: str) -> None:
        print(f"inspecting {expected_mode}", flush=True)
        view.page().runJavaScript(
            "JSON.stringify(window.getSceneState ? window.getSceneState() : null)",
            lambda value: on_state(expected_mode, value),
        )

    def save_screenshot() -> bool:
        return bool(view.grab().save(screenshot_path))

    def on_state(expected_mode: str, value: object) -> None:
        nonlocal interaction_checked, screenshot_saved
        print(f"state callback {expected_mode}", flush=True)
        print(f"raw state {value!r}", flush=True)
        if not isinstance(value, str):
            finish(False, f"state unavailable for {expected_mode}")
            return
        state = json.loads(value)
        if not interaction_checked:
            interaction_checked = True
            if int(state.get("skeletonBoneSegmentCount", 0)) < 14:
                finish(False, f"solid skeleton bone segments were not created: {state}")
                return
            if int(state.get("skeletonJointHaloCount", 0)) < len((
                "nose", "left_eye", "right_eye", "left_ear", "right_ear",
                "left_shoulder", "right_shoulder", "left_elbow", "right_elbow",
                "left_wrist", "right_wrist", "left_hip", "right_hip",
                "left_knee", "right_knee", "left_ankle", "right_ankle",
            )):
                finish(False, f"joint halos were not created for the full body: {state}")
                return
            if int(state.get("renderedTriangles", 0)) < 1:
                finish(False, f"renderer produced no visible triangles: {state}")
                return
            if abs(float(state.get("cameraTheta", 0.0))) < 0.05:
                finish(False, f"left-drag rotation did not change the camera: {state}")
                return
            target = state.get("cameraTarget", {})
            if abs(float(target.get("x", 0.0))) < 0.03:
                finish(False, f"right-drag pan did not move the camera target: {state}")
                return
            if float(state.get("cameraRadius", 0.0)) > 4.7:
                finish(False, f"mouse-wheel zoom did not change the camera: {state}")
                return
            if state.get("robotModelDriveReady") and not state.get("skeletonModelAnchored"):
                finish(False, f"robot skeleton is not anchored to the model rig: {state}")
                return
            hand_visible = state.get("handRigVisible", {})
            if not (hand_visible.get("left") and hand_visible.get("right")):
                finish(False, f"21-point hand rig was not rendered: {state}")
                return
            palm_visible = state.get("solidPalmVisible", {})
            needs_overlay_palm = int(state.get("robotFingerBoneCount", 0)) < 5
            if needs_overlay_palm and not (
                palm_visible.get("left") and palm_visible.get("right")
            ):
                finish(False, f"replacement model did not show its palm overlay: {state}")
                return
            if not needs_overlay_palm and (
                palm_visible.get("left") or palm_visible.get("right")
            ):
                finish(False, f"native finger rig incorrectly used the palm overlay: {state}")
                return
        if state.get("canvasCount", 0) < 1:
            finish(False, "Three.js canvas was not created")
            return
        if state.get("modelMode") != expected_mode:
            finish(False, f"model mode mismatch: {state}")
            return
        if int(state.get("actorCount", 0)) != 1:
            finish(False, f"single-actor contract failed: {state}")
            return
        if model_override:
            if not state.get("robotModelAvailable"):
                finish(False, f"override model was not loaded: {state}")
                return
            if not state.get("robotModelDriveReady"):
                finish(False, f"override model has no usable humanoid rig: {state}")
                return
            if int(state.get("robotBoneCount", 0)) < 8:
                finish(False, f"override model exposes too few driven bones: {state}")
                return
        skeleton_visible = bool(state.get("robotSkeletonVisible"))
        body_visible = bool(state.get("robotBodyVisible"))
        if not skeleton_visible:
            finish(False, f"robot skeleton must remain visible: {state}")
            return
        if state.get("rootMotionMode") not in {"none", "sway", "planar"}:
            finish(False, f"root motion mode is invalid: {state}")
            return
        if expected_mode == "skeleton" and (not skeleton_visible or body_visible):
            finish(False, f"invalid skeleton visibility: {state}")
            return
        if expected_mode == "body" and (not skeleton_visible or not body_visible):
            finish(False, f"invalid body visibility: {state}")
            return
        if expected_mode == "overlay" and (not skeleton_visible or not body_visible):
            finish(False, f"invalid overlay visibility: {state}")
            return
        try:
            next_mode = next(checks)
        except StopIteration:
            if screenshot_path and not screenshot_saved:
                screenshot_saved = True
                view.page().runJavaScript(
                    "window.resetRobotCamera();",
                    lambda _value: QTimer.singleShot(
                        500,
                        lambda: finish(
                            save_screenshot(), json.dumps(state, ensure_ascii=False)
                        ),
                    ),
                )
                return
            finish(True, json.dumps(state, ensure_ascii=False))
            return
        widget.set_model_mode(next_mode)
        QTimer.singleShot(120, lambda: inspect(next_mode))

    def run_camera_interaction() -> None:
        script = """
        (() => {
          const canvas = document.querySelector("canvas");
          if (!canvas) return false;
          const pointer = (type, options) => canvas.dispatchEvent(
            new PointerEvent(type, { bubbles: true, pointerId: 11, ...options })
          );
          pointer("pointerdown", { button: 0, clientX: 100, clientY: 100 });
          pointer("pointermove", { button: 0, clientX: 160, clientY: 124 });
          pointer("pointerup", { button: 0, clientX: 160, clientY: 124 });
          pointer("pointerdown", { button: 2, clientX: 100, clientY: 100 });
          pointer("pointermove", { button: 2, clientX: 145, clientY: 100 });
          pointer("pointerup", { button: 2, clientX: 145, clientY: 100 });
          canvas.dispatchEvent(new WheelEvent("wheel", {
            bubbles: true, deltaY: -180, clientX: 100, clientY: 100
          }));
          const hand = Array.from({ length: 21 }, (_value, index) => [
            (index % 5) * 0.012 - 0.024, Math.floor(index / 5) * 0.025, 0
          ]);
          const joints = {
            nose: [0, 1.70, 0], left_eye: [0.04, 1.72, 0], right_eye: [-0.04, 1.72, 0],
            left_ear: [0.10, 1.69, 0], right_ear: [-0.10, 1.69, 0],
            left_shoulder: [0.24, 1.50, 0], right_shoulder: [-0.24, 1.50, 0],
            left_elbow: [0.45, 1.25, 0], right_elbow: [-0.45, 1.25, 0],
            left_wrist: [0.58, 1.00, 0], right_wrist: [-0.58, 1.00, 0],
            left_hip: [0.13, 0.92, 0], right_hip: [-0.13, 0.92, 0],
            left_knee: [0.14, 0.48, 0], right_knee: [-0.14, 0.48, 0],
            left_ankle: [0.14, 0.08, 0], right_ankle: [-0.14, 0.08, 0]
          };
          window.updateRobot({
            joints, hands: { left: hand, right: hand }, scores: {}, edges: []
          });
          return true;
        })()
        """
        view.page().runJavaScript(
            script,
            lambda _value: QTimer.singleShot(120, lambda: inspect("overlay")),
        )

    def on_loaded(ok: bool) -> None:
        nonlocal inspection_started
        print(f"loadFinished={ok}", flush=True)
        if not ok:
            finish(False, "QWebEngine loadFinished reported failure")
            return
        if inspection_started:
            return
        inspection_started = True
        QTimer.singleShot(500, run_camera_interaction)

    view.loadFinished.connect(on_loaded)
    QTimer.singleShot(20000, lambda: finish(False, "timeout"))
    app.exec()
    widget.stop()
    print(("PASS: " if result["ok"] else "FAIL: ") + str(result["message"]))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
