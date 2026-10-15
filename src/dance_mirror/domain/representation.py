"""Hard representation rules for the V9 learning and command-center workspaces."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from dance_mirror.domain.quality import MotionQualityLevel, MotionQualityProfile


class WorkspaceKind(StrEnum):
    """The two product workflows that may occupy a renderer."""

    LEARNING_DANCE = "learning_dance"
    ROBOT_COMMAND_CENTER = "robot_command_center"


class UserRepresentation(StrEnum):
    """How the user is represented in a workspace."""

    CAMERA_2D_SKELETON = "camera_2d_skeleton"
    USER_3D = "user_3d"


class RobotRepresentation(StrEnum):
    """How the robot is represented in a workspace."""

    ROBOT_3D = "robot_3d"


class RootMotionMode(StrEnum):
    """How much root translation the renderer may apply."""

    NONE = "none"
    SWAY = "sway"
    PLANAR = "planar"


@dataclass(frozen=True, slots=True)
class RootMotionPolicy:
    """Conservative root-motion limits for low-end and dormitory setups."""

    mode: RootMotionMode = RootMotionMode.NONE
    max_lateral_m: float = 0.12
    max_planar_m: float = 0.30

    def __post_init__(self) -> None:
        if self.max_lateral_m < 0.0 or self.max_planar_m < 0.0:
            raise ValueError("root-motion limits cannot be negative")
        if self.max_planar_m < self.max_lateral_m:
            raise ValueError("max_planar_m must be at least max_lateral_m")

    def validate_quality(self, quality: MotionQualityLevel | MotionQualityProfile) -> None:
        """Reject unrestricted root motion without trustworthy 3D evidence."""
        level = quality.level if isinstance(quality, MotionQualityProfile) else quality
        if self.mode is RootMotionMode.PLANAR and level is not MotionQualityLevel.VERIFIED_3D:
            raise ValueError("PLANAR root motion requires VERIFIED_3D quality")

    @property
    def allows_translation(self) -> bool:
        return self.mode is RootMotionMode.PLANAR

    @property
    def allows_lateral_sway(self) -> bool:
        return self.mode in {RootMotionMode.SWAY, RootMotionMode.PLANAR}


@dataclass(frozen=True, slots=True)
class ActorCapabilityMatrix:
    """Capabilities used by the character loader and renderer."""

    fingers: bool = False
    face: bool = False
    morph_targets: bool = False
    transparency: bool = True
    emissive: bool = True
    accessories: bool = True
    max_active_actors: int = 1

    def __post_init__(self) -> None:
        if self.max_active_actors != 1:
            raise ValueError("the current 6GB runtime budget allows one 3D actor")


@dataclass(frozen=True, slots=True)
class RepresentationDecision:
    """Resolved representation for one workspace."""

    workspace: WorkspaceKind
    user: UserRepresentation
    robot: RobotRepresentation
    camera_overlay_required: bool = True
    robot_skeleton_required: bool = True

    @property
    def user_3d_allowed(self) -> bool:
        return self.user is UserRepresentation.USER_3D

    @property
    def robot_3d_allowed(self) -> bool:
        return self.robot is RobotRepresentation.ROBOT_3D


class RepresentationViolation(ValueError):
    """Raised when a feature request violates the V9/V10 runtime contract."""


class RepresentationPolicy:
    """Central policy that prevents accidental user-3D reintroduction."""

    @staticmethod
    def decide(workspace: WorkspaceKind) -> RepresentationDecision:
        if workspace not in {WorkspaceKind.LEARNING_DANCE, WorkspaceKind.ROBOT_COMMAND_CENTER}:
            raise RepresentationViolation(f"unsupported workspace: {workspace}")
        return RepresentationDecision(
            workspace=workspace,
            user=UserRepresentation.CAMERA_2D_SKELETON,
            robot=RobotRepresentation.ROBOT_3D,
            camera_overlay_required=True,
            robot_skeleton_required=True,
        )

    @staticmethod
    def validate_mesh_request(
        workspace: WorkspaceKind,
        *,
        user_3d_requested: bool = False,
        actor_count: int = 1,
    ) -> None:
        if user_3d_requested:
            raise RepresentationViolation(
                f"{workspace.value} must not create a user 3D mesh or SMPL avatar"
            )
        if actor_count != 1:
            raise RepresentationViolation(
                f"{workspace.value} supports exactly one 3D robot actor"
            )

    @staticmethod
    def default_root_motion_policy() -> RootMotionPolicy:
        return RootMotionPolicy(mode=RootMotionMode.NONE)
