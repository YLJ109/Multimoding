"""Headless diagnostics and reference-video analysis entry point."""

from __future__ import annotations

import argparse
import importlib.util
import sys
from pathlib import Path

from dance_mirror.config import AppPaths
from dance_mirror.logging_setup import configure_logging
from dance_mirror.pose2d.yolo_pose import YoloPoseConfig
from dance_mirror.services.reference import analyze_reference_video
from dance_mirror.storage.motion_package import save_motion_package


def _package_state(name: str) -> str:
    return "available" if importlib.util.find_spec(name) is not None else "missing"


def doctor() -> int:
    """Print environment checks without importing heavyweight packages."""
    print("DanceMirror environment doctor")
    print(f"python: {sys.executable}")
    print(f"python version: {sys.version.split()[0]}")
    print(f"user-site disabled: {bool(sys.flags.no_user_site)}")
    for name in (
        "numpy",
        "cv2",
        "scipy",
        "einops",
        "torch",
        "torchvision",
        "ultralytics",
        "onnxruntime",
        "PyQt6",
        "PyQt6.QtWebEngineWidgets",
        "qfluentwidgets",
    ):
        print(f"{name}: {_package_state(name)}")
    try:
        import torch

        print(f"torch: {torch.__version__}")
        print(f"cuda available: {torch.cuda.is_available()}")
        if torch.cuda.is_available():
            print(f"gpu: {torch.cuda.get_device_name(0)}")
            print(f"cuda: {torch.version.cuda}")
            properties = torch.cuda.get_device_properties(0)
            print(f"vram: {properties.total_memory / (1024 ** 2):.0f} MiB")
    except ImportError:
        print("torch runtime: unavailable")
    paths = AppPaths.discover()
    print(f"app home: {paths.root}")
    model_path = paths.models / "yolo11n-pose.pt"
    print(f"pose model: {model_path} ({'present' if model_path.is_file() else 'missing'})")
    return 0


def analyze(video: str, output: str | None, model: str | None, device: str) -> int:
    """Run reference analysis without a GUI and write a motion package."""
    paths = AppPaths.discover()
    paths.ensure()
    if not model:
        model = str(paths.models / "yolo11n-pose.pt")
    configure_logging(paths.logs)
    result = analyze_reference_video(
        video,
        pose_config=YoloPoseConfig(model_path=model, device=device),
        progress=lambda value: print(f"progress: {value}%", flush=True),
    )
    destination = Path(output) if output else paths.motion_packages / "reference.dmotion.json"
    saved = save_motion_package(result.sequence, destination)
    print(f"frames: {result.total_frames}, detected: {result.detected_frames}")
    print(f"motion package: {saved}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="dance-mirror")
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("doctor", help="check the runtime environment")
    analyze_parser = subparsers.add_parser("analyze", help="analyze a reference video")
    analyze_parser.add_argument("video", help="path to a single-person dance video")
    analyze_parser.add_argument("--output", default=None, help="output motion package path")
    analyze_parser.add_argument("--model", default=None)
    analyze_parser.add_argument("--device", default="cuda:0")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "doctor":
        return doctor()
    if args.command == "analyze":
        return analyze(args.video, args.output, args.model, args.device)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
