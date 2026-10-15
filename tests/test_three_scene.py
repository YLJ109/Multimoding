"""Static contracts for the single-robot Three.js document."""

from __future__ import annotations

import json

from dance_mirror.motion.retarget import RetargetedSkeleton
from dance_mirror.renderer.three_scene import (
    build_three_scene_html,
    payload_as_javascript,
    skeleton_payload,
)


def test_scene_document_has_one_actor_skeleton_and_root_motion_controls() -> None:
    html = build_three_scene_html()
    assert "actorCount: 1" in html
    assert "robotSkeletonVisible" in html
    assert "skeletonBoneSegmentCount" in html
    assert "skeletonJointHaloCount" in html
    assert "skeletonModelAnchored" in html
    assert "function modelJointPoints" in html
    assert "renderPoints = modelJointPoints(points)" in html
    assert "new THREE.CylinderGeometry(0.0042, 0.0060, 1, 8, 1, false)" in html
    assert "new THREE.CylinderGeometry(0.011, 0.015, 1, 10, 1, false)" in html
    assert "worldPointForRole(role, jointName.endsWith(\"_ankle\"))" in html
    assert "depthTest: false, depthWrite: false" in html
    assert "robotBodyVisible" in html
    assert "window.setRootMotion" in html
    assert "window.setRobotModelUrl" in html
    assert "rootMotionMode" in html
    assert "function hideHandRigs" in html
    assert "updateHands(payload, points)" in html
    assert "Array.isArray(raw)" in html  # hands payload is normalised defensively
    assert "showSolidPalm" in html
    assert "renderer.domElement.addEventListener(\"pointerdown\"" in html
    assert "cameraPointer.button === 1 || cameraPointer.button === 2" in html
    assert "skeletonarmjointl4" in html
    assert "window.setMotionPreset" in html
    assert "window.setInterfaceTheme" in html
    assert "measuredFps" in html
    assert "window.setSceneActive" in html
    assert "window.setRenderFps" in html
    assert "targetRenderFps" in html
    assert "window.resetRobotCamera" in html
    assert "referenceSkeletonVisible" not in html
    assert "referenceBodyVisible" not in html
    assert "SMPL" not in html
    assert "userAvatar" not in html


def _skeleton_with_hands() -> RetargetedSkeleton:
    hands = {"left": tuple((float(index), 0.0, 0.0) for index in range(21))}
    return RetargetedSkeleton(
        joints={"left_wrist": (0.0, 0.0, 0.0)},
        scores={"left_wrist": 1.0},
        edges=(),
        timestamp_s=0.0,
        frame_index=0,
        hands=hands,
    )


def test_hands_payload_is_a_positional_array_not_an_index_object() -> None:
    """The browser reads hands via index access and `.slice()`.

    Serialising each side as an index-keyed object made `mapHandPoints` throw
    ``source.slice is not a function`` on every frame, which aborted the whole
    render update.
    """
    payload = skeleton_payload(_skeleton_with_hands())
    left = payload["hands"]["left"]

    assert isinstance(left, list)
    assert len(left) == 21
    assert left[0] == [0.0, 0.0, 0.0]
    assert left[9] == [9.0, 0.0, 0.0]

    script = payload_as_javascript("updateRobot", _skeleton_with_hands())
    assert '"hands":{"left":[[0.0,0.0,0.0]' in script


def test_hands_payload_survives_json_round_trip_as_arrays() -> None:
    encoded = json.loads(json.dumps(skeleton_payload(_skeleton_with_hands())))
    left = encoded["hands"]["left"]

    assert isinstance(left, list)  # JS Array -> `.slice` exists
    assert len(left) == 21
    assert left[20] == [20.0, 0.0, 0.0]


def test_skeleton_payload_tolerates_missing_hands() -> None:
    skeleton = RetargetedSkeleton(
        joints={"left_wrist": (0.0, 0.0, 0.0)},
        scores={"left_wrist": 1.0},
        edges=(),
        timestamp_s=0.0,
        frame_index=0,
        hands=None,
    )
    assert skeleton_payload(skeleton)["hands"] == {}

