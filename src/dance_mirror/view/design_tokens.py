"""Semantic visual tokens shared by Qt widgets, canvases, and HUDs."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class UiPalette:
    """One resolved light or dark palette."""

    background: str
    surface: str
    surface_alt: str
    surface_raised: str
    border: str
    border_strong: str
    text: str
    text_soft: str
    muted: str
    primary: str
    primary_hover: str
    primary_pressed: str
    primary_soft: str
    focus: str
    success: str
    warning: str
    danger: str
    danger_hover: str
    camera_background: str
    camera_border: str
    camera_placeholder: str
    hud_background: str
    hud_text: str
    # overlay / HUD semantic tokens (rendered on top of the camera feed)
    hud_badge_bg: str
    hud_badge_text: str
    hud_bone_shadow: str
    hud_joint_outline: str
    hud_joint_left: str
    hud_joint_right: str
    hud_joint_empty: str
    hud_hand_left: str
    hud_hand_right: str
    hud_hand_unknown: str
    hud_face_edge: str
    hud_face_dot: str
    hud_bbox_person: str
    hud_bbox_face: str
    hud_privacy_fill: str
    hud_privacy_stroke: str
    skeleton_left: str
    skeleton_right: str
    skeleton_empty: str


LIGHT_PALETTE = UiPalette(
    background="#f1f4f7",
    surface="#ffffff",
    surface_alt="#f7f9fb",
    surface_raised="#ffffff",
    border="#d9e1e8",
    border_strong="#c4d0da",
    text="#18252f",
    text_soft="#334552",
    muted="#687986",
    primary="#0f7fa4",
    primary_hover="#0b6e91",
    primary_pressed="#095b78",
    primary_soft="#e3f4f9",
    focus="#1d9bc0",
    success="#18835f",
    warning="#a96c0a",
    danger="#c7444f",
    danger_hover="#ad3540",
    camera_background="#0d1319",
    camera_border="#34434f",
    camera_placeholder="#9fb0bc",
    hud_background="#080d12",
    hud_text="#edf6fa",
    hud_badge_bg="#080e14cd",
    hud_badge_text="#071018",
    hud_bone_shadow="#050c1296",
    hud_joint_outline="#081116",
    hud_joint_left="#66c8ff",
    hud_joint_right="#ffad66",
    hud_joint_empty="#eef6fb",
    hud_hand_left="#62c8ff",
    hud_hand_right="#ffb05f",
    hud_hand_unknown="#b8c6d2",
    hud_face_edge="#5bdaffbe",
    hud_face_dot="#dbf7ffb4",
    hud_bbox_person="#7be0ad",
    hud_bbox_face="#61dcff",
    hud_privacy_fill="#bc41412a",
    hud_privacy_stroke="#ff8181",
    skeleton_left="#5bc9ef",
    skeleton_right="#e5ae59",
    skeleton_empty="#74848e",
)

DARK_PALETTE = UiPalette(
    background="#0d1116",
    surface="#141a21",
    surface_alt="#171e26",
    surface_raised="#1c242d",
    border="#29333d",
    border_strong="#3b4854",
    text="#e7eef4",
    text_soft="#c6d1d9",
    muted="#8c9aa7",
    primary="#32b5d6",
    primary_hover="#45c6e4",
    primary_pressed="#2495b3",
    primary_soft="#123743",
    focus="#68d7ef",
    success="#55c793",
    warning="#e0aa55",
    danger="#e66770",
    danger_hover="#f07880",
    camera_background="#080d12",
    camera_border="#35434e",
    camera_placeholder="#9badb9",
    hud_background="#070b0f",
    hud_text="#edf7fb",
    hud_badge_bg="#080e14cd",
    hud_badge_text="#071018",
    hud_bone_shadow="#050c1296",
    hud_joint_outline="#081116",
    hud_joint_left="#66c8ff",
    hud_joint_right="#ffad66",
    hud_joint_empty="#eef6fb",
    hud_hand_left="#62c8ff",
    hud_hand_right="#ffb05f",
    hud_hand_unknown="#b8c6d2",
    hud_face_edge="#5bdaffbe",
    hud_face_dot="#dbf7ffb4",
    hud_bbox_person="#7be0ad",
    hud_bbox_face="#61dcff",
    hud_privacy_fill="#bc41412a",
    hud_privacy_stroke="#ff8181",
    skeleton_left="#67d5f2",
    skeleton_right="#efb865",
    skeleton_empty="#6f7f89",
)


def palette_for(theme: str) -> UiPalette:
    """Resolve a saved theme name to one stable semantic palette."""
    return DARK_PALETTE if str(theme).strip().lower() == "dark" else LIGHT_PALETTE
