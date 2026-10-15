"""Tests for the V9/V10 representation hard constraints."""

from __future__ import annotations

import pytest

from dance_mirror.domain.quality import MotionQualityLevel
from dance_mirror.domain.representation import (
    ActorCapabilityMatrix,
    RepresentationPolicy,
    RepresentationViolation,
    RootMotionMode,
    RootMotionPolicy,
    UserRepresentation,
    WorkspaceKind,
)


def test_both_workspaces_use_camera_skeleton_and_one_robot() -> None:
    for workspace in WorkspaceKind:
        decision = RepresentationPolicy.decide(workspace)
        assert decision.user is UserRepresentation.CAMERA_2D_SKELETON
        assert not decision.user_3d_allowed
        assert decision.robot_3d_allowed
        assert decision.camera_overlay_required
        assert decision.robot_skeleton_required


def test_user_3d_request_is_rejected() -> None:
    with pytest.raises(RepresentationViolation):
        RepresentationPolicy.validate_mesh_request(
            WorkspaceKind.LEARNING_DANCE,
            user_3d_requested=True,
        )


def test_root_motion_defaults_to_none_and_planar_requires_verified_quality() -> None:
    policy = RepresentationPolicy.default_root_motion_policy()
    assert policy.mode is RootMotionMode.NONE
    assert not policy.allows_translation

    planar = RootMotionPolicy(mode=RootMotionMode.PLANAR)
    with pytest.raises(ValueError):
        planar.validate_quality(MotionQualityLevel.HYBRID_3D)
    planar.validate_quality(MotionQualityLevel.VERIFIED_3D)


def test_actor_budget_is_limited_to_one() -> None:
    with pytest.raises(ValueError):
        ActorCapabilityMatrix(max_active_actors=2)
