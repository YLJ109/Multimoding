"""Single-robot Three.js scene document and renderer payload helpers."""

from __future__ import annotations

import json
from pathlib import Path

from dance_mirror.motion.retarget import RetargetedSkeleton

THREE_CDN = "https://cdn.jsdelivr.net/npm/three@0.180.0/build/three.module.min.js"
RESOURCE_DIR = Path(__file__).resolve().parents[1] / "resources"
THREE_LOCAL_FILE = RESOURCE_DIR / "three.module.min.js"
GLTF_LOADER_LOCAL_FILE = RESOURCE_DIR / "loaders" / "GLTFLoader.js"
ROBOT_MODEL_LOCAL_FILE = RESOURCE_DIR / "dance_robot_cyber.glb"


def skeleton_payload(skeleton: RetargetedSkeleton) -> dict[str, object]:
    """Convert a retargeted skeleton into a JSON-safe browser payload."""
    return {
        "joints": {name: list(point) for name, point in skeleton.joints.items()},
        "scores": dict(skeleton.scores),
        "edges": [list(edge) for edge in skeleton.edges],
        "timestamp_s": skeleton.timestamp_s,
        "frame_index": skeleton.frame_index,
        # The browser side (`mapHandPoints`) indexes and `.slice()`s this value,
        # so it must be a positional ARRAY of 21 [x, y, z] points, not an
        # index-keyed object (an object has no `.slice`).
        "hands": {
            side: [list(point) for point in points]
            for side, points in (skeleton.hands or {}).items()
        },
    }


def payload_as_javascript(variable: str, skeleton: RetargetedSkeleton) -> str:
    """Create a JavaScript call without serializing arbitrary Python objects."""
    payload = json.dumps(
        skeleton_payload(skeleton),
        ensure_ascii=False,
        separators=(",", ":"),
    )
    return f"window.{variable}({payload});"


def build_three_scene_html() -> str:
    """Return the scene HTML used by QWebEngineView.

    The vendored Three.js module and GLTFLoader are preferred so a competition
    machine can run offline. The pinned CDN remains a development fallback.
    """
    import_source = "./three.module.min.js" if THREE_LOCAL_FILE.is_file() else THREE_CDN
    return HTML_TEMPLATE.replace("__THREE_IMPORT__", import_source)


HTML_TEMPLATE = r"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <style>
    html, body {
      margin: 0; width: 100%; height: 100%; overflow: hidden;
      background: #0c1117; color: #eef6fb;
      font-family: "Microsoft YaHei UI", "Segoe UI", sans-serif;
    }
    canvas {
      display: block; width: 100%; height: 100%; touch-action: none;
      user-select: none; cursor: grab;
    }
    canvas.dragging { cursor: grabbing; }
    #stage-label {
      position: absolute; left: 18px; top: 14px; z-index: 3;
      padding: 6px 10px; border: 1px solid rgba(108, 207, 246, .36);
      border-radius: 5px; background: rgba(7, 13, 19, .72);
      color: #d9f5ff; font-size: 13px; font-weight: 650;
      text-shadow: 0 1px 5px #000;
    }
    #status {
      position: absolute; left: 18px; bottom: 14px; z-index: 3;
      max-width: 65%; padding: 5px 9px; border-radius: 4px;
      background: rgba(7, 13, 19, .72); color: #aebdca; font-size: 12px;
    }
    #quality {
      position: absolute; right: 18px; bottom: 14px; z-index: 3;
      padding: 5px 9px; border-radius: 4px; color: #8fdfb4;
      background: rgba(7, 13, 19, .72); font-size: 12px;
    }
    body[data-interface-theme="light"] #stage-label,
    body[data-interface-theme="light"] #status,
    body[data-interface-theme="light"] #quality {
      color: #1b2a35;
      background: rgba(246, 250, 253, .90);
      border-color: rgba(42, 126, 170, .34);
      text-shadow: none;
    }
  </style>
</head>
<body>
  <div id="stage-label">3D 机器人舞台</div>
  <div id="quality">骨架：标准</div>
  <div id="status">等待动作数据</div>
  <script type="importmap">
    {"imports": {"three": "__THREE_IMPORT__"}}
  </script>
  <script type="module">
    import * as THREE from "three";

    const scene = new THREE.Scene();
    scene.background = new THREE.Color(0x0c1117);
    scene.fog = new THREE.Fog(0x0c1117, 7.0, 15.0);

    const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: false });
    renderer.setPixelRatio(1.0);
    renderer.shadowMap.enabled = false;
    renderer.shadowMap.type = THREE.PCFSoftShadowMap;
    document.body.appendChild(renderer.domElement);

    const camera = new THREE.PerspectiveCamera(35, 1, 0.05, 100);
    camera.position.set(0, 1.32, 4.9);
    camera.lookAt(0, 0.90, 0);

    const cameraTarget = new THREE.Vector3(0, 0.90, 0);
    const cameraHome = {
      target: new THREE.Vector3(0, 0.90, 0),
      position: new THREE.Vector3(0, 1.32, 4.9)
    };
    const orbit = new THREE.Spherical().setFromVector3(
      camera.position.clone().sub(cameraTarget)
    );
    let cameraRadius = orbit.radius;
    let cameraTheta = orbit.theta;
    let cameraPhi = orbit.phi;
    let cameraPointer = null;
    const pointerOrigin = new THREE.Vector2();

    function applyOrbitCamera() {
      cameraRadius = THREE.MathUtils.clamp(cameraRadius, 2.2, 10.0);
      cameraPhi = THREE.MathUtils.clamp(cameraPhi, 0.42, 1.54);
      const offset = new THREE.Vector3().setFromSpherical(
        new THREE.Spherical(cameraRadius, cameraPhi, cameraTheta)
      );
      camera.position.copy(cameraTarget).add(offset);
      camera.lookAt(cameraTarget);
    }

    function resetOrbitCamera() {
      cameraTarget.copy(cameraHome.target);
      const home = new THREE.Spherical().setFromVector3(
        cameraHome.position.clone().sub(cameraHome.target)
      );
      cameraRadius = home.radius;
      cameraTheta = home.theta;
      cameraPhi = home.phi;
      applyOrbitCamera();
    }

    renderer.domElement.addEventListener("contextmenu", (event) => event.preventDefault());
    renderer.domElement.addEventListener("pointerdown", (event) => {
      event.preventDefault();
      cameraPointer = { button: event.button, x: event.clientX, y: event.clientY };
      renderer.domElement.classList.add("dragging");
      renderer.domElement.setPointerCapture?.(event.pointerId);
    });
    renderer.domElement.addEventListener("pointermove", (event) => {
      if (!cameraPointer) return;
      const dx = event.clientX - cameraPointer.x;
      const dy = event.clientY - cameraPointer.y;
      cameraPointer.x = event.clientX;
      cameraPointer.y = event.clientY;
      if (cameraPointer.button === 0) {
        cameraTheta -= dx * 0.006;
        cameraPhi -= dy * 0.005;
      } else if (cameraPointer.button === 1 || cameraPointer.button === 2) {
        const right = new THREE.Vector3(1, 0, 0).applyQuaternion(camera.quaternion);
        const up = new THREE.Vector3(0, 1, 0).applyQuaternion(camera.quaternion);
        cameraTarget.addScaledVector(right, -dx * cameraRadius * 0.0012);
        cameraTarget.addScaledVector(up, dy * cameraRadius * 0.0012);
        cameraTarget.x = THREE.MathUtils.clamp(cameraTarget.x, -2.2, 2.2);
        cameraTarget.y = THREE.MathUtils.clamp(cameraTarget.y, 0.15, 2.2);
        cameraTarget.z = THREE.MathUtils.clamp(cameraTarget.z, -2.2, 2.2);
      }
      applyOrbitCamera();
    });
    function endCameraPointer(event) {
      if (cameraPointer) renderer.domElement.releasePointerCapture?.(event.pointerId);
      cameraPointer = null;
      renderer.domElement.classList.remove("dragging");
    }
    renderer.domElement.addEventListener("pointerup", endCameraPointer);
    renderer.domElement.addEventListener("pointercancel", endCameraPointer);
    renderer.domElement.addEventListener("wheel", (event) => {
      event.preventDefault();
      cameraRadius *= Math.exp(event.deltaY * 0.0009);
      applyOrbitCamera();
    }, { passive: false });
    renderer.domElement.addEventListener("dblclick", resetOrbitCamera);
    applyOrbitCamera();

    const stage = new THREE.Group();
    scene.add(stage);
    const floorMaterial = new THREE.MeshStandardMaterial({
      color: 0x17212a, roughness: 0.72, metalness: 0.24
    });
    const floor = new THREE.Mesh(new THREE.CylinderGeometry(2.7, 2.9, 0.10, 64), floorMaterial);
    floor.position.y = -0.055;
    floor.receiveShadow = true;
    stage.add(floor);

    const ringMaterial = new THREE.MeshBasicMaterial({
      color: 0x37bfe8, transparent: true, opacity: 0.52
    });
    const ring = new THREE.Mesh(new THREE.TorusGeometry(2.42, 0.018, 8, 96), ringMaterial);
    ring.rotation.x = Math.PI / 2;
    ring.position.y = 0.012;
    stage.add(ring);

    const grid = new THREE.GridHelper(7.0, 28, 0x315263, 0x1a2833);
    grid.position.y = 0.006;
    stage.add(grid);

    for (let index = 0; index < 16; index += 1) {
      const angle = (index / 16) * Math.PI * 2;
      const marker = new THREE.Mesh(
        new THREE.BoxGeometry(0.035, 0.012, 0.18),
        new THREE.MeshBasicMaterial({ color: index % 4 === 0 ? 0x7be0ad : 0x37bfe8 })
      );
      marker.position.set(Math.cos(angle) * 2.42, 0.02, Math.sin(angle) * 2.42);
      marker.rotation.y = -angle;
      stage.add(marker);
    }

    scene.add(new THREE.HemisphereLight(0xccecff, 0x18212a, 1.7));
    const keyLight = new THREE.DirectionalLight(0xffffff, 2.5);
    keyLight.position.set(3.0, 5.0, 3.6);
    keyLight.castShadow = true;
    keyLight.shadow.mapSize.set(1024, 1024);
    scene.add(keyLight);
    const rimLight = new THREE.PointLight(0x41c9f4, 4.0, 8.0, 2.0);
    rimLight.position.set(-2.3, 1.8, -2.0);
    scene.add(rimLight);

    const world = new THREE.Group();
    scene.add(world);
    const robotRoot = new THREE.Group();
    world.add(robotRoot);

    const jointNames = [
      "nose", "left_eye", "right_eye", "left_ear", "right_ear",
      "left_shoulder", "right_shoulder", "left_elbow", "right_elbow",
      "left_wrist", "right_wrist", "left_hip", "right_hip",
      "left_knee", "right_knee", "left_ankle", "right_ankle"
    ];
    const up = new THREE.Vector3(0, 1, 0);
    const skinColors = {
      default: 0x63d5ff,
      cyber: 0x34f0d0,
      gold: 0xffc95c,
      azure: 0x5a9dff,
      crimson: 0xff6770
    };
    const themeColors = {
      studio: { background: 0x0c1117, floor: 0x17212a, ring: 0x37bfe8, fog: 0x0c1117 },
      dorm: { background: 0x181716, floor: 0x28241f, ring: 0xd1a76d, fog: 0x181716 },
      neon: { background: 0x080c18, floor: 0x151a36, ring: 0xff49c8, fog: 0x080c18 }
    };

    const skeletonEdges = [
      ["nose", "left_eye"], ["nose", "right_eye"], ["left_eye", "left_ear"],
      ["right_eye", "right_ear"], ["left_shoulder", "right_shoulder"],
      ["left_shoulder", "left_elbow"], ["left_elbow", "left_wrist"],
      ["right_shoulder", "right_elbow"], ["right_elbow", "right_wrist"],
      ["shoulder_center", "hip_center"], ["shoulder_center", "nose"],
      ["left_hip", "right_hip"], ["left_hip", "left_knee"],
      ["left_knee", "left_ankle"], ["right_hip", "right_knee"],
      ["right_knee", "right_ankle"]
    ];
    const skeletonMaterial = new THREE.LineBasicMaterial({
      color: skinColors.default, transparent: true, opacity: 0.48,
      depthTest: false, depthWrite: false
    });
    const skeletonGeometry = new THREE.BufferGeometry();
    skeletonGeometry.setAttribute(
      "position",
      new THREE.Float32BufferAttribute(new Float32Array(skeletonEdges.length * 6), 3)
    );
    const skeletonLines = new THREE.LineSegments(skeletonGeometry, skeletonMaterial);
    skeletonLines.renderOrder = 24;
    robotRoot.add(skeletonLines);
    function sideForJointName(name) {
      if (String(name).startsWith("left_")) return "left";
      if (String(name).startsWith("right_")) return "right";
      return "center";
    }
    const boneMaterialBySide = {
      center: new THREE.MeshBasicMaterial({
        color: skinColors.default, transparent: true, opacity: 0.54,
        depthTest: false, depthWrite: false
      }),
      left: new THREE.MeshBasicMaterial({
        color: 0xe3a75c, transparent: true, opacity: 0.68,
        depthTest: false, depthWrite: false
      }),
      right: new THREE.MeshBasicMaterial({
        color: 0x58bdd4, transparent: true, opacity: 0.68,
        depthTest: false, depthWrite: false
      })
    };
    const boneGlowMaterialBySide = {
      center: new THREE.MeshBasicMaterial({
        color: skinColors.default, transparent: true, opacity: 0.09,
        depthTest: false, depthWrite: false
      }),
      left: new THREE.MeshBasicMaterial({
        color: 0xe3a75c, transparent: true, opacity: 0.12,
        depthTest: false, depthWrite: false
      }),
      right: new THREE.MeshBasicMaterial({
        color: 0x58bdd4, transparent: true, opacity: 0.12,
        depthTest: false, depthWrite: false
      })
    };
    const boneGeometry = new THREE.CylinderGeometry(0.0042, 0.0060, 1, 8, 1, false);
    const boneGlowGeometry = new THREE.CylinderGeometry(0.011, 0.015, 1, 10, 1, false);
    const boneSegments = skeletonEdges.map((edge) => {
      const side = sideForJointName(edge[0]);
      const glow = new THREE.Mesh(boneGlowGeometry, boneGlowMaterialBySide[side]);
      glow.renderOrder = 25;
      glow.position.set(0, -100, 0);
      robotRoot.add(glow);
      const mesh = new THREE.Mesh(boneGeometry, boneMaterialBySide[side]);
      mesh.renderOrder = 26;
      mesh.position.set(0, -100, 0);
      robotRoot.add(mesh);
      return { edge, mesh, glow };
    });
    const jointMaterials = {
      center: new THREE.MeshBasicMaterial({ color: skinColors.default, depthTest: false }),
      left: new THREE.MeshBasicMaterial({ color: 0xe3a75c, depthTest: false, depthWrite: false }),
      right: new THREE.MeshBasicMaterial({ color: 0x58bdd4, depthTest: false, depthWrite: false })
    };
    const haloMaterials = {
      center: new THREE.MeshBasicMaterial({
        color: skinColors.default, transparent: true, opacity: 0.08,
        depthTest: false, depthWrite: false
      }),
      left: new THREE.MeshBasicMaterial({
        color: 0xe3a75c, transparent: true, opacity: 0.10,
        depthTest: false, depthWrite: false
      }),
      right: new THREE.MeshBasicMaterial({
        color: 0x58bdd4, transparent: true, opacity: 0.10,
        depthTest: false, depthWrite: false
      })
    };
    const jointGeometry = new THREE.SphereGeometry(0.015, 16, 12);
    const haloGeometry = new THREE.SphereGeometry(0.028, 16, 12);
    const jointMarkers = [];
    const jointHalos = [];
    for (const name of jointNames) {
      const side = sideForJointName(name);
      const marker = new THREE.Mesh(jointGeometry, jointMaterials[side]);
      marker.renderOrder = 28;
      marker.position.set(0, -100, 0);
      robotRoot.add(marker);
      jointMarkers.push(marker);
      const halo = new THREE.Mesh(haloGeometry, haloMaterials[side]);
      halo.renderOrder = 27;
      halo.position.set(0, -100, 0);
      robotRoot.add(halo);
      jointHalos.push(halo);
    }

    const handEdges = [
      [0, 1], [1, 2], [2, 3], [3, 4], [0, 5], [5, 6], [6, 7], [7, 8],
      [5, 9], [9, 10], [10, 11], [11, 12], [9, 13], [13, 14], [14, 15],
      [15, 16], [13, 17], [17, 18], [18, 19], [19, 20], [0, 17]
    ];
    const handRigs = {};
    for (const side of ["left", "right"]) {
      const color = side === "left" ? 0xe3a75c : 0x58bdd4;
      const geometry = new THREE.BufferGeometry();
      geometry.setAttribute(
        "position",
        new THREE.Float32BufferAttribute(new Float32Array(handEdges.length * 6), 3)
      );
      const material = new THREE.LineBasicMaterial({
        color, transparent: true, opacity: 0.68, depthTest: false, depthWrite: false
      });
      const lines = new THREE.LineSegments(geometry, material);
      lines.renderOrder = 30;
      lines.visible = false;
      robotRoot.add(lines);
      const markerMaterial = new THREE.MeshBasicMaterial({ color, depthTest: false, depthWrite: false });
      const markerGeometry = new THREE.SphereGeometry(0.0072, 10, 8);
      const markers = [];
      for (let index = 0; index < 21; index += 1) {
        const marker = new THREE.Mesh(markerGeometry, markerMaterial);
        marker.renderOrder = 31;
        marker.visible = false;
        robotRoot.add(marker);
        markers.push(marker);
      }
      const palm = new THREE.Mesh(
        new THREE.BoxGeometry(0.064, 0.010, 0.076),
        new THREE.MeshBasicMaterial({
          color, transparent: true, opacity: 0.26, depthTest: false, depthWrite: false
        })
      );
      palm.renderOrder = 29;
      palm.visible = false;
      robotRoot.add(palm);
      handRigs[side] = { lines, markers, geometry, palm, visible: false };
    }

    function hideHandRigs() {
      Object.values(handRigs).forEach((rig) => {
        rig.lines.visible = false;
        rig.palm.visible = false;
        rig.markers.forEach((marker) => { marker.visible = false; });
      });
    }

    function skinColor() {
      return skinColors[activeSkin] || skinColors.default;
    }

    const bodyRoot = new THREE.Group();
    robotRoot.add(bodyRoot);
    const bodyMaterial = new THREE.MeshStandardMaterial({
      color: skinColors.default, metalness: 0.18, roughness: 0.58
    });
    const bodyDarkMaterial = new THREE.MeshStandardMaterial({
      color: 0x22384a, metalness: 0.22, roughness: 0.62
    });
    const warmSkinMaterial = new THREE.MeshStandardMaterial({
      color: 0xd6a17e, metalness: 0.02, roughness: 0.72
    });
    const accentMaterial = new THREE.MeshStandardMaterial({
      color: 0x95efff, emissive: 0x1f6576, emissiveIntensity: 0.72,
      metalness: 0.10, roughness: 0.36
    });
    const bodyParts = {
      head: new THREE.Mesh(new THREE.SphereGeometry(0.115, 24, 18), warmSkinMaterial),
      neck: new THREE.Mesh(new THREE.CapsuleGeometry(0.043, 0.085, 6, 12), warmSkinMaterial),
      torso: new THREE.Mesh(new THREE.CapsuleGeometry(0.142, 0.305, 8, 16), bodyMaterial),
      waist: new THREE.Mesh(new THREE.CapsuleGeometry(0.092, 0.095, 6, 14), bodyDarkMaterial),
      left_shoulder: new THREE.Mesh(new THREE.SphereGeometry(0.072, 14, 10), bodyMaterial),
      right_shoulder: new THREE.Mesh(new THREE.SphereGeometry(0.072, 14, 10), bodyMaterial),
      left_elbow: new THREE.Mesh(new THREE.SphereGeometry(0.052, 12, 9), bodyDarkMaterial),
      right_elbow: new THREE.Mesh(new THREE.SphereGeometry(0.052, 12, 9), bodyDarkMaterial),
      left_upper_arm: new THREE.Mesh(new THREE.CapsuleGeometry(0.051, 0.205, 6, 12), bodyMaterial),
      left_forearm: new THREE.Mesh(new THREE.CapsuleGeometry(0.043, 0.19, 6, 12), warmSkinMaterial),
      right_upper_arm: new THREE.Mesh(new THREE.CapsuleGeometry(0.051, 0.205, 6, 12), bodyMaterial),
      right_forearm: new THREE.Mesh(new THREE.CapsuleGeometry(0.043, 0.19, 6, 12), warmSkinMaterial),
      left_hand: new THREE.Mesh(new THREE.SphereGeometry(0.052, 12, 9), warmSkinMaterial),
      right_hand: new THREE.Mesh(new THREE.SphereGeometry(0.052, 12, 9), warmSkinMaterial),
      pelvis: new THREE.Mesh(new THREE.CapsuleGeometry(0.11, 0.075, 7, 16), bodyDarkMaterial),
      left_thigh: new THREE.Mesh(new THREE.CapsuleGeometry(0.066, 0.22, 6, 12), bodyDarkMaterial),
      left_shin: new THREE.Mesh(new THREE.CapsuleGeometry(0.052, 0.235, 6, 12), bodyMaterial),
      right_thigh: new THREE.Mesh(new THREE.CapsuleGeometry(0.066, 0.22, 6, 12), bodyDarkMaterial),
      right_shin: new THREE.Mesh(new THREE.CapsuleGeometry(0.052, 0.235, 6, 12), bodyMaterial),
      left_foot: new THREE.Mesh(new THREE.BoxGeometry(0.115, 0.058, 0.205), bodyDarkMaterial),
      right_foot: new THREE.Mesh(new THREE.BoxGeometry(0.115, 0.058, 0.205), bodyDarkMaterial),
      chest_mark: new THREE.Mesh(new THREE.BoxGeometry(0.07, 0.035, 0.012), accentMaterial)
    };
    for (const part of Object.values(bodyParts)) {
      part.castShadow = true;
      part.receiveShadow = true;
      bodyRoot.add(part);
    }
    bodyParts.head.scale.set(0.90, 1.13, 0.92);

    const modelRoot = new THREE.Group();
    robotRoot.add(modelRoot);
    let modelMixer = null;
    let modelAction = null;
    let modelAvailable = false;
    let modelRig = null;
    let modelDriveReady = false;
    let modelPoseDriven = false;
    let skeletonModelAnchored = false;
    let modelLoadGeneration = 0;
    let activeSkin = "default";
    let activeTheme = "studio";
    let actionName = "idle";
    let actionPaused = false;
    let modelMode = "overlay";
    let lowPower = true;
    let sceneActive = false;
    let targetRenderFps = 45;
    let renderIntervalMs = 1000 / targetRenderFps;
    let interfaceTheme = "dark";
    let fpsWindowStartedAt = performance.now();
    let fpsWindowFrames = 0;
    let measuredFps = 0;

    function updateQualityLabel() {
      const mode = lowPower ? "低功耗" : "标准";
      const fps = measuredFps > 0 ? ` · ${measuredFps.toFixed(0)} 帧/秒` : "";
      document.getElementById("quality").textContent = `性能：${mode}${fps}`;
    }
    let imitationScope = "full_body";
    let rootMotionMode = "none";
    let poseActive = false;
    let lastPayload = null;
    let lastPayloadAt = 0;
    let targetPoints = null;
    let displayPoints = null;
    let targetHandPoints = { left: null, right: null };
    let displayHandPoints = { left: null, right: null };
    let motionSmoothing = 0.32;
    let motionPreset = "balanced";

    const boneAliasGroups = {
      hips: ["hips", "pelvis", "hip", "torsojoint1", "skeletontorsojoint1"],
      spine: ["abdomen", "spine1", "spine", "torsojoint2", "skeletontorsojoint2"],
      chest: [
        "torso", "chest", "spine2", "upperchest",
        "torsojoint3", "skeletontorsojoint3"
      ],
      neck: ["neck", "neckjoint1", "skeletonneckjoint1"],
      head: ["head", "neckjoint2", "skeletonneckjoint2"],
      leftUpperArm: [
        "upperarml", "leftupperarm", "upperarmleft", "leftarm", "arml",
        "armjointl1", "skeletonarmjointl4"
      ],
      leftLowerArm: [
        "lowerarml", "leftlowerarm", "leftforearm", "lowerarmleft", "forearml",
        "armjointl2", "skeletonarmjointl3"
      ],
      leftHand: [
        "palm1l", "handl", "lefthand", "handleft", "wristl",
        "armjointl3", "skeletonarmjointl2"
      ],
      rightUpperArm: [
        "upperarmr", "rightupperarm", "upperarmright", "rightarm", "armr",
        "armjointr1", "skeletonarmjointr"
      ],
      rightLowerArm: [
        "lowerarmr", "rightlowerarm", "rightforearm", "lowerarmright", "forearmr",
        "armjointr2", "skeletonarmjointr2"
      ],
      rightHand: [
        "palm1r", "handr", "righthand", "handright", "wristr",
        "armjointr3", "skeletonarmjointr3"
      ],
      leftUpperLeg: [
        "upperlegl", "leftupleg", "thighl", "leftupperleg", "upleftleg", "legjointl1"
      ],
      leftLowerLeg: [
        "lowerlegl", "leftleg", "shinl", "leftlowerleg", "lowleftleg", "legjointl2"
      ],
      leftFoot: ["footl", "leftfoot", "legjointl3"],
      rightUpperLeg: [
        "upperlegr", "rightupleg", "thighr", "rightupperleg", "uprightleg", "legjointr1"
      ],
      rightLowerLeg: [
        "lowerlegr", "rightleg", "shinr", "rightlowerleg", "lowrightleg", "legjointr2"
      ],
      rightFoot: ["footr", "rightfoot", "legjointr3"]
    };
    const fingerAliasGroups = {
      thumb: ["thumb"],
      index: ["index"],
      middle: ["middle"],
      ring: ["ring"],
      pinky: ["pinky", "little"]
    };
    const boneDriveDefinitions = [
      { role: "spine", start: "hip_center", end: "shoulder_center" },
      { role: "chest", start: "hip_center", end: "shoulder_center" },
      { role: "neck", start: "shoulder_center", end: "nose" },
      { role: "head", start: "nose", end: "nose_up" },
      { role: "leftUpperArm", start: "left_shoulder", end: "left_elbow" },
      { role: "leftLowerArm", start: "left_elbow", end: "left_wrist" },
      { role: "leftHand", start: "left_wrist", end: "left_hand_target" },
      { role: "rightUpperArm", start: "right_shoulder", end: "right_elbow" },
      { role: "rightLowerArm", start: "right_elbow", end: "right_wrist" },
      { role: "rightHand", start: "right_wrist", end: "right_hand_target" },
      { role: "leftUpperLeg", start: "left_hip", end: "left_knee" },
      { role: "leftLowerLeg", start: "left_knee", end: "left_ankle" },
      { role: "rightUpperLeg", start: "right_hip", end: "right_knee" },
      { role: "rightLowerLeg", start: "right_knee", end: "right_ankle" }
    ];

    function colorVector(value) {
      return new THREE.Color(value || skinColors.default);
    }

    function applySkin(name) {
      activeSkin = skinColors[name] ? name : "default";
      const color = skinColor();
      bodyMaterial.color.setHex(color);
      bodyDarkMaterial.color.copy(colorVector(color).multiplyScalar(0.34));
      skeletonMaterial.color.setHex(color);
      jointMaterials.center.color.setHex(color);
      haloMaterials.center.color.setHex(color);
      boneMaterialBySide.center.color.setHex(color);
      boneGlowMaterialBySide.center.color.setHex(color);
      rimLight.color.setHex(color);
      accentMaterial.emissive.setHex(color);
      modelRoot.traverse((child) => {
        if (!child.isMesh) return;
        const materials = Array.isArray(child.material) ? child.material : [child.material];
        materials.forEach((material) => {
          if (!material || !material.color) return;
          if (!material.userData.originalColor) {
            material.userData.originalColor = material.color.clone();
          }
          material.color.copy(material.userData.originalColor);
          if (material.userData.humanoidShell) {
            material.color.lerp(colorVector(color), 0.30);
            material.emissive.copy(colorVector(color).multiplyScalar(0.18));
          }
        });
      });
    }

    function applyTheme(name) {
      activeTheme = themeColors[name] ? name : "studio";
      const theme = themeColors[activeTheme];
      scene.background.setHex(theme.background);
      scene.fog.color.setHex(theme.fog);
      floorMaterial.color.setHex(theme.floor);
      ringMaterial.color.setHex(theme.ring);
      ringMaterial.opacity = activeTheme === "neon" ? 0.82 : 0.52;
      rimLight.intensity = activeTheme === "neon" ? 6.5 : 4.0;
    }

    function setSkeletonVisibility() {
      skeletonLines.visible = true;
      jointMarkers.forEach((marker) => { marker.visible = true; });
      const showModel = modelAvailable && modelMode !== "skeleton";
      bodyRoot.visible = modelMode !== "skeleton" && (!showModel || (poseActive && !modelDriveReady));
      modelRoot.visible = showModel && (!poseActive || modelDriveReady);
    }

    function setLowPower(enabled) {
      lowPower = Boolean(enabled);
      renderer.setPixelRatio(lowPower ? 1.0 : Math.min(window.devicePixelRatio || 1, 1.5));
      renderer.shadowMap.enabled = !lowPower && targetRenderFps >= 55;
      keyLight.castShadow = renderer.shadowMap.enabled;
      floor.receiveShadow = renderer.shadowMap.enabled;
      modelRoot.traverse((child) => {
        if (child.isMesh) child.castShadow = renderer.shadowMap.enabled;
      });
      floor.castShadow = false;
      updateQualityLabel();
    }

    function pointMap(payload) {
      const points = {};
      for (const name of jointNames) {
        const point = payload.joints[name] || [0, 0, 0];
        points[name] = new THREE.Vector3(
          Number(point[0]) || 0,
          Number(point[1]) || 0,
          Number(point[2]) || 0
        );
      }
      points.hip_center = points.left_hip.clone().add(points.right_hip).multiplyScalar(0.5);
      points.shoulder_center = points.left_shoulder.clone().add(points.right_shoulder).multiplyScalar(0.5);
      return points;
    }

    let poseWorldScale = null;

    function pointIsUsable(payload, point, name) {
      if (!point || !Number.isFinite(point.x) || !Number.isFinite(point.y) || !Number.isFinite(point.z)) return false;
      if (payload.scores && Number(payload.scores[name] ?? 1) < 0.12) return false;
      return Math.abs(point.x) + Math.abs(point.y) + Math.abs(point.z) > 1e-5;
    }

    function toWorldPoints(payload, rawPoints = null) {
      const raw = rawPoints || pointMap(payload);
      const hip = raw.hip_center;
      const shoulder = raw.shoulder_center;
      const upper = pointIsUsable(payload, raw.nose, "nose")
        ? raw.nose
        : shoulder.clone().add(new THREE.Vector3(0, 0.72, 0));
      const ankleCandidates = [
        pointIsUsable(payload, raw.left_ankle, "left_ankle") ? raw.left_ankle : null,
        pointIsUsable(payload, raw.right_ankle, "right_ankle") ? raw.right_ankle : null
      ].filter(Boolean);
      const lower = ankleCandidates.length
        ? ankleCandidates.reduce((sum, point) => sum.add(point), new THREE.Vector3()).multiplyScalar(1 / ankleCandidates.length)
        : hip.clone().add(new THREE.Vector3(0, -0.86, 0));
      for (const side of ["left", "right"]) {
        const hipName = `${side}_hip`;
        const kneeName = `${side}_knee`;
        const ankleName = `${side}_ankle`;
        const hipUsable = pointIsUsable(payload, raw[hipName], hipName);
        const kneeUsable = pointIsUsable(payload, raw[kneeName], kneeName);
        const ankleUsable = pointIsUsable(payload, raw[ankleName], ankleName);
        if (kneeUsable && ankleUsable) continue;
        const sideHip = hipUsable ? raw[hipName] : hip;
        const footY = ankleUsable ? raw[ankleName].y : lower.y;
        if (!kneeUsable) {
          raw[kneeName] = new THREE.Vector3(
            sideHip.x,
            sideHip.y + (footY - sideHip.y) * 0.52,
            sideHip.z
          );
        }
        if (!ankleUsable) {
          const knee = raw[kneeName];
          raw[ankleName] = new THREE.Vector3(knee.x, footY, knee.z);
        }
      }
      const rawHeight = Math.max(0.75, Math.min(12.0, upper.y - lower.y || 5.5));
      const targetScale = 1.72 / rawHeight;
      poseWorldScale = poseWorldScale === null
        ? targetScale
        : THREE.MathUtils.lerp(poseWorldScale, targetScale, 0.18);
      const scale = THREE.MathUtils.clamp(poseWorldScale, 0.10, 2.2);
      const center = Math.abs(hip.x) + Math.abs(hip.y) + Math.abs(hip.z) > 1e-5
        ? hip
        : shoulder;
      const world = {};
      for (const name of jointNames) {
        const source = raw[name];
        world[name] = new THREE.Vector3(
          (source.x - center.x) * scale,
          (source.y - lower.y) * scale,
          (source.z - center.z) * scale
        );
      }
      world.hip_center = world.left_hip.clone().add(world.right_hip).multiplyScalar(0.5);
      world.shoulder_center = world.left_shoulder.clone().add(world.right_shoulder).multiplyScalar(0.5);
      return world;
    }

    function placeLimb(mesh, first, second, radiusScale) {
      const length = first.distanceTo(second);
      if (length < 0.001) {
        mesh.visible = false;
        return;
      }
      const direction = second.clone().sub(first).normalize();
      mesh.visible = true;
      mesh.position.copy(first).add(second).multiplyScalar(0.5);
      mesh.quaternion.setFromUnitVectors(up, direction);
      const parameters = mesh.geometry.parameters || {};
      const capsuleLength = Number(parameters.height) || 0;
      const capsuleRadius = Number(parameters.radius) || 0;
      const baseLength = mesh.geometry.type === "CapsuleGeometry"
        ? capsuleLength + capsuleRadius * 2
        : Math.max(capsuleLength, 0.01);
      mesh.scale.set(radiusScale || 1, Math.max(0.04, length / baseLength), radiusScale || 1);
    }

    function updateSkeletonMeshes(points) {
      for (const segment of boneSegments) {
        const first = points[segment.edge[0]];
        const second = points[segment.edge[1]];
        if (!first || !second) {
          segment.mesh.visible = false;
          segment.glow.visible = false;
          continue;
        }
        placeLimb(segment.mesh, first, second, 1);
        placeLimb(segment.glow, first, second, 1);
      }
      for (let index = 0; index < jointMarkers.length; index += 1) {
        jointHalos[index].position.copy(jointMarkers[index].position);
        jointHalos[index].visible = jointMarkers[index].visible;
      }
    }

    function updateBody(points) {
      bodyParts.head.position.copy(points.nose).add(new THREE.Vector3(0, 0.055, 0));
      const neckEnd = points.shoulder_center.clone().lerp(points.nose, 0.40);
      placeLimb(bodyParts.neck, points.shoulder_center, neckEnd, 1);
      placeLimb(bodyParts.torso, points.hip_center, points.shoulder_center, 1);
      const waistTop = points.hip_center.clone().lerp(points.shoulder_center, 0.34);
      placeLimb(bodyParts.waist, points.hip_center, waistTop, 1);
      bodyParts.pelvis.position.copy(points.hip_center);
      bodyParts.chest_mark.position.copy(points.hip_center).lerp(points.shoulder_center, 0.70);
      bodyParts.chest_mark.position.z -= 0.145;
      bodyParts.left_shoulder.position.copy(points.left_shoulder);
      bodyParts.right_shoulder.position.copy(points.right_shoulder);
      placeLimb(bodyParts.left_upper_arm, points.left_shoulder, points.left_elbow, 1);
      bodyParts.left_elbow.position.copy(points.left_elbow);
      placeLimb(bodyParts.left_forearm, points.left_elbow, points.left_wrist, 1);
      bodyParts.left_hand.position.copy(points.left_wrist);
      placeLimb(bodyParts.right_upper_arm, points.right_shoulder, points.right_elbow, 1);
      bodyParts.right_elbow.position.copy(points.right_elbow);
      placeLimb(bodyParts.right_forearm, points.right_elbow, points.right_wrist, 1);
      bodyParts.right_hand.position.copy(points.right_wrist);
      placeLimb(bodyParts.left_thigh, points.left_hip, points.left_knee, 1);
      placeLimb(bodyParts.left_shin, points.left_knee, points.left_ankle, 1);
      placeLimb(bodyParts.right_thigh, points.right_hip, points.right_knee, 1);
      placeLimb(bodyParts.right_shin, points.right_knee, points.right_ankle, 1);
      bodyParts.left_foot.position.copy(points.left_ankle).add(new THREE.Vector3(0, -0.027, 0.045));
      bodyParts.right_foot.position.copy(points.right_ankle).add(new THREE.Vector3(0, -0.027, 0.045));
    }

    function mapHandPoints(side, payload, bodyPoints) {
      const raw = payload?.hands?.[side];
      const anchor = bodyPoints?.[`${side}_wrist`];
      // Accept a positional array (current contract) or an index-keyed object
      // (legacy) so a payload change can never throw mid-render again.
      const source = Array.isArray(raw)
        ? raw
        : (
          raw && typeof raw === "object"
            ? Object.keys(raw)
              .sort((first, second) => Number(first) - Number(second))
              .map((key) => raw[key])
            : null
        );
      if (!source || source.length < 21 || !anchor) return null;
      const wrist = source[0];
      const palmDistance = Math.hypot(
        Number(source[9][0]) - Number(wrist[0]),
        Number(source[9][1]) - Number(wrist[1])
      );
      const scale = 0.092 / Math.max(0.015, palmDistance);
      return source.slice(0, 21).map((point) => new THREE.Vector3(
        anchor.x + (Number(point[0]) - Number(wrist[0])) * scale,
        anchor.y - (Number(point[1]) - Number(wrist[1])) * scale,
        anchor.z + (Number(point[2]) - Number(wrist[2])) * scale * 0.65
      ));
    }

    function updateHandRig(side, mapped = null) {
      const rig = handRigs[side];
      if (!rig || !mapped || mapped.length < 21) {
        if (rig) {
          rig.lines.visible = false;
          rig.palm.visible = false;
          rig.markers.forEach((marker) => { marker.visible = false; });
        }
        return;
      }
      const positions = rig.geometry.attributes.position.array;
      let cursor = 0;
      for (const edge of handEdges) {
        const first = mapped[edge[0]];
        const second = mapped[edge[1]];
        positions[cursor++] = first.x;
        positions[cursor++] = first.y;
        positions[cursor++] = first.z;
        positions[cursor++] = second.x;
        positions[cursor++] = second.y;
        positions[cursor++] = second.z;
      }
      rig.geometry.attributes.position.needsUpdate = true;
      rig.lines.visible = true;
      rig.markers.forEach((marker, index) => {
        marker.position.copy(mapped[index]);
        marker.visible = true;
      });
      const showSolidPalm = !modelDriveReady || (modelRig?.fingerDrives.length || 0) < 5;
      rig.palm.visible = showSolidPalm;
      if (showSolidPalm) {
        const wrist = mapped[0];
        const middleBase = mapped[9];
        const forward = middleBase.clone().sub(wrist);
        if (forward.lengthSq() > 1e-8) {
          forward.normalize();
          let across = mapped[17].clone().sub(mapped[5]);
          if (across.lengthSq() < 1e-8) across.set(1, 0, 0);
          across.normalize();
          const normal = new THREE.Vector3().crossVectors(forward, across);
          if (normal.lengthSq() < 1e-8) normal.set(0, 1, 0);
          normal.normalize();
          across.crossVectors(normal, forward).normalize();
          rig.palm.quaternion.setFromRotationMatrix(
            new THREE.Matrix4().makeBasis(across, normal, forward)
          );
          rig.palm.position.copy(wrist).lerp(middleBase, 0.52);
          rig.palm.scale.set(1, 1, THREE.MathUtils.clamp(wrist.distanceTo(middleBase) / 0.092, 0.72, 1.35));
        }
      }
    }

    function updateHands(payload, points) {
      for (const side of ["left", "right"]) {
        targetHandPoints[side] = mapHandPoints(side, payload, points);
        if (!displayHandPoints[side] || !targetHandPoints[side]) {
          displayHandPoints[side] = targetHandPoints[side]
            ? targetHandPoints[side].map((point) => point.clone())
            : null;
        }
      }
    }

    function rebaseHandPoints(handPoints, anchor) {
      if (!handPoints?.length || !anchor) return handPoints;
      const delta = anchor.clone().sub(handPoints[0]);
      return handPoints.map((point) => point.clone().add(delta));
    }

    function clonePoints(points) {
      const output = {};
      for (const [name, point] of Object.entries(points)) {
        if (point?.isVector3) output[name] = point.clone();
      }
      return output;
    }

    function smoothPoints(current, target, alpha) {
      if (!current) return clonePoints(target);
      for (const [name, point] of Object.entries(target)) {
        if (!point?.isVector3) continue;
        if (!current[name]) current[name] = point.clone();
        else current[name].lerp(point, alpha);
      }
      return current;
    }

    function smoothHands(current, target, alpha) {
      const output = { left: null, right: null };
      for (const side of ["left", "right"]) {
        if (!target[side]) {
          output[side] = null;
          continue;
        }
        if (!current[side] || current[side].length !== target[side].length) {
          output[side] = target[side].map((point) => point.clone());
          continue;
        }
        output[side] = current[side].map((point, index) => point.clone().lerp(target[side][index], alpha));
      }
      return output;
    }

    function normalizedBoneName(name) {
      return String(name || "").toLowerCase().replace(/[^a-z0-9]/g, "");
    }

    function findAliasedBone(model, aliases) {
      let best = null;
      model.traverse((child) => {
        if (best || !child.isBone) return;
        const name = normalizedBoneName(child.name);
        if (aliases.some((alias) => name === alias || name.endsWith(alias))) best = child;
      });
      return best;
    }

    function captureBoneDrive(bone) {
      if (!bone) return null;
      const restPosition = new THREE.Vector3();
      const restQuaternion = new THREE.Quaternion();
      bone.getWorldPosition(restPosition);
      bone.getWorldQuaternion(restQuaternion);
      const restLocalPosition = bone.position.clone();
      const restLocalQuaternion = bone.quaternion.clone();
      const childBone = bone.children.find((child) => child.isBone);
      const restDirection = new THREE.Vector3();
      if (childBone) {
        childBone.getWorldPosition(restDirection);
        restDirection.sub(restPosition);
      }
      if (restDirection.lengthSq() < 1e-8) {
        restDirection.set(0, 1, 0).applyQuaternion(restQuaternion);
      }
      return {
        bone,
        restPosition,
        restQuaternion,
        restLocalPosition,
        restLocalQuaternion,
        restDirection: restDirection.normalize(),
        depth: boneDepth(bone)
      };
    }

    function boneDepth(bone) {
      let depth = 0;
      let current = bone;
      while (current?.parent) {
        depth += 1;
        current = current.parent;
      }
      return depth;
    }

    function captureModelRig(model) {
      model.updateMatrixWorld(true);
      const roles = {};
      for (const [role, aliases] of Object.entries(boneAliasGroups)) {
        roles[role] = findAliasedBone(model, aliases);
      }
      const drives = boneDriveDefinitions
        .map((definition) => ({ ...definition, ...captureBoneDrive(roles[definition.role]) }))
        .filter((definition) => definition.bone);

      const fingerPairs = {
        thumb: [[1, 2], [2, 3], [3, 4]],
        index: [[5, 6], [6, 7], [7, 8]],
        middle: [[9, 10], [10, 11], [11, 12]],
        ring: [[13, 14], [14, 15], [15, 16]],
        pinky: [[17, 18], [18, 19], [19, 20]]
      };
      const fingerDrives = [];
      for (const side of ["left", "right"]) {
        const candidates = [];
        model.traverse((child) => {
          if (child.isBone) candidates.push(child);
        });
        for (const [finger, aliases] of Object.entries(fingerAliasGroups)) {
          const matches = candidates.filter((bone) => {
            const name = normalizedBoneName(bone.name);
            const sideMatch = side === "left"
              ? (name.startsWith("left") || name.endsWith("l"))
              : (name.startsWith("right") || name.endsWith("r"));
            return sideMatch && aliases.some((alias) => name.includes(alias));
          }).sort((first, second) => boneDepth(first) - boneDepth(second));
          matches.forEach((bone, index) => {
            const state = captureBoneDrive(bone);
            if (state) fingerDrives.push({
              ...state,
              side,
              finger,
              pair: fingerPairs[finger][Math.min(index, fingerPairs[finger].length - 1)]
            });
          });
        }
      }
      const restHips = roles.hips
        ? new THREE.Vector3().setFromMatrixPosition(roles.hips.matrixWorld)
        : new THREE.Vector3(0, 0.9, 0);
      return {
        model,
        roles,
        drives,
        fingerDrives,
        restHips,
        basePosition: model.position.clone()
      };
    }

    function resetModelRig() {
      if (!modelRig) return;
      modelRig.model.position.copy(modelRig.basePosition);
      for (const drive of [...modelRig.drives, ...modelRig.fingerDrives]) {
        drive.bone.position.copy(drive.restLocalPosition);
        drive.bone.quaternion.copy(drive.restLocalQuaternion);
        drive.bone.updateMatrix();
      }
      modelRig.model.updateMatrixWorld(true);
      modelPoseDriven = false;
    }

    function driveTargetForRole(role, points, hands) {
      if (role === "head") {
        const direction = points.nose.clone().sub(points.shoulder_center);
        if (direction.lengthSq() < 1e-6) direction.set(0, 1, 0);
        direction.normalize().multiplyScalar(0.26);
        return points.nose.clone().add(direction);
      }
      if (role === "leftHand" || role === "rightHand") {
        const side = role === "leftHand" ? "left" : "right";
        if (hands[side]?.[9]) return hands[side][9].clone();
        const wrist = points[`${side}_wrist`];
        const elbow = points[`${side}_elbow`];
        return wrist.clone().add(wrist.clone().sub(elbow).normalize().multiplyScalar(0.11));
      }
      return null;
    }

    function buildBoneTarget(targets, drive, start, end) {
      if (!drive || !start || !end) return;
      const desiredDirection = end.clone().sub(start);
      if (desiredDirection.lengthSq() < 1e-8 || drive.restDirection.lengthSq() < 1e-8) return;
      desiredDirection.normalize();
      const delta = new THREE.Quaternion().setFromUnitVectors(
        drive.restDirection,
        desiredDirection
      );
      targets.set(drive.bone, delta.multiply(drive.restQuaternion.clone()));
    }

    function driveModelRig(points, hands) {
      if (!modelRig || !modelDriveReady) return;
      modelPoseDriven = true;
      const model = modelRig.model;
      const delta = points.hip_center.clone().sub(modelRig.restHips);
      delta.x = THREE.MathUtils.clamp(delta.x, -0.65, 0.65);
      delta.y = THREE.MathUtils.clamp(delta.y, -0.40, 0.40);
      delta.z = THREE.MathUtils.clamp(delta.z, -0.65, 0.65);
      model.position.copy(modelRig.basePosition).add(delta);
      model.updateMatrixWorld(true);

      const targets = new Map();
      for (const drive of modelRig.drives) {
        let start = points[drive.start];
        let end = points[drive.end];
        if (drive.role === "leftHand" || drive.role === "rightHand") {
          end = driveTargetForRole(drive.role, points, hands);
        } else if (drive.role === "head") {
          end = driveTargetForRole(drive.role, points, hands);
        }
        buildBoneTarget(targets, drive, start, end);
      }
      for (const drive of modelRig.fingerDrives) {
        const hand = hands[drive.side];
        if (!hand) continue;
        buildBoneTarget(targets, drive, hand[drive.pair[0]], hand[drive.pair[1]]);
      }

      const ordered = [...modelRig.drives, ...modelRig.fingerDrives]
        .sort((first, second) => first.depth - second.depth);
      const parentWorld = new THREE.Quaternion();
      const inverseParent = new THREE.Quaternion();
      for (const drive of ordered) {
        const target = targets.get(drive.bone);
        if (!target) continue;
        if (drive.bone.parent) {
          drive.bone.parent.getWorldQuaternion(parentWorld);
          inverseParent.copy(parentWorld).invert();
          drive.bone.quaternion.copy(inverseParent.multiply(target));
        } else {
          drive.bone.quaternion.copy(target);
        }
        drive.bone.updateMatrix();
        drive.bone.updateWorldMatrix(false, false);
      }
    }

    function worldPointForRole(role, atBoneEnd = false) {
      const bone = modelRig?.roles?.[role];
      if (!bone) return null;
      const target = atBoneEnd
        ? bone.children.find((child) => child.isBone) || bone
        : bone;
      const point = new THREE.Vector3();
      target.getWorldPosition(point);
      return point;
    }

    function modelJointPoints(fallbackPoints) {
      const points = clonePoints(fallbackPoints);
      const roleToJoint = {
        left_shoulder: "leftUpperArm",
        left_elbow: "leftLowerArm",
        left_wrist: "leftHand",
        right_shoulder: "rightUpperArm",
        right_elbow: "rightLowerArm",
        right_wrist: "rightHand",
        left_hip: "leftUpperLeg",
        left_knee: "leftLowerLeg",
        left_ankle: "leftLowerLeg",
        right_hip: "rightUpperLeg",
        right_knee: "rightLowerLeg",
        right_ankle: "rightLowerLeg"
      };
      for (const [jointName, role] of Object.entries(roleToJoint)) {
        const point = worldPointForRole(role, jointName.endsWith("_ankle"));
        if (point) points[jointName] = point;
      }
      points.hip_center = points.left_hip.clone().add(points.right_hip).multiplyScalar(0.5);
      points.shoulder_center = points.left_shoulder.clone().add(points.right_shoulder).multiplyScalar(0.5);
      const headBone = modelRig?.roles?.head;
      if (headBone) {
        const headPoint = new THREE.Vector3();
        headBone.getWorldPosition(headPoint);
        const childHead = headBone.children.find((child) => child.isBone);
        if (childHead) {
          points.nose = childHead.getWorldPosition(new THREE.Vector3());
        } else {
          points.nose = headPoint.clone().add(new THREE.Vector3(0, 0.11, 0));
        }
        points.left_eye = points.nose.clone().add(new THREE.Vector3(0.035, 0.015, -0.02));
        points.right_eye = points.nose.clone().add(new THREE.Vector3(-0.035, 0.015, -0.02));
        points.left_ear = points.nose.clone().add(new THREE.Vector3(0.09, 0, 0));
        points.right_ear = points.nose.clone().add(new THREE.Vector3(-0.09, 0, 0));
      }
      return points;
    }

    function applyScope(points) {
      if (imitationScope === "full_body" || !lastPayload) return points;
      const base = pointMap(lastPayload);
      if (imitationScope === "upper_body") {
        for (const name of ["left_hip", "right_hip", "left_knee", "right_knee", "left_ankle", "right_ankle"]) {
          points[name].copy(base[name]);
        }
      } else if (imitationScope === "lower_body") {
        for (const name of ["nose", "left_shoulder", "right_shoulder", "left_elbow", "right_elbow", "left_wrist", "right_wrist"]) {
          points[name].copy(base[name]);
        }
      } else if (imitationScope === "hands") {
        points.left_wrist.copy(base.left_wrist);
        points.right_wrist.copy(base.right_wrist);
      } else if (imitationScope === "head") {
        points.nose.copy(base.nose);
      }
      return points;
    }

    function applyRootMotion(points) {
      const hip = points.hip_center;
      if (!hip) return points;
      let deltaX = 0;
      let deltaZ = 0;
      if (rootMotionMode === "none") {
        deltaX = -hip.x;
        deltaZ = -hip.z;
      } else if (rootMotionMode === "sway") {
        deltaX = THREE.MathUtils.clamp(hip.x, -0.12, 0.12) - hip.x;
        deltaZ = -hip.z;
      } else if (rootMotionMode === "planar") {
        deltaX = THREE.MathUtils.clamp(hip.x, -0.30, 0.30) - hip.x;
        deltaZ = THREE.MathUtils.clamp(hip.z, -0.30, 0.30) - hip.z;
      }
      if (Math.abs(deltaX) > 1e-6 || Math.abs(deltaZ) > 1e-6) {
        Object.values(points).forEach((point) => {
          point.x += deltaX;
          point.z += deltaZ;
        });
      }
      return points;
    }

    function updateSkeleton(payload) {
      if (!payload || !payload.joints) return;
      const scopedRaw = applyScope(pointMap(payload));
      const points = applyRootMotion(toWorldPoints(payload, scopedRaw));
      lastPayload = payload;
      targetPoints = points;
      if (!displayPoints) displayPoints = clonePoints(points);
      updateHands(payload, targetPoints);
      poseActive = true;
      lastPayloadAt = performance.now();
      setSkeletonVisibility();
    }

    function renderSkeletonGeometry(points) {
      const positions = skeletonGeometry.attributes.position.array;
      let cursor = 0;
      for (const edge of skeletonEdges) {
        const first = points[edge[0]];
        const second = points[edge[1]];
        if (!first || !second) continue;
        positions[cursor++] = first.x;
        positions[cursor++] = first.y;
        positions[cursor++] = first.z;
        positions[cursor++] = second.x;
        positions[cursor++] = second.y;
        positions[cursor++] = second.z;
      }
      while (cursor < positions.length) positions[cursor++] = 0;
      skeletonGeometry.attributes.position.needsUpdate = true;
      for (let index = 0; index < jointNames.length; index += 1) {
        if (points[jointNames[index]]) jointMarkers[index].position.copy(points[jointNames[index]]);
      }
      updateSkeletonMeshes(points);
    }

    function renderPose(payload, points, driveModel = true) {
      if (!payload || !points) return;
      if (driveModel) driveModelRig(points, displayHandPoints);

      let renderPoints = points;
      let handPoints = displayHandPoints;
      if (driveModel && modelRig && modelDriveReady) {
        modelRig.model.updateMatrixWorld(true);
        renderPoints = modelJointPoints(points);
        skeletonModelAnchored = true;
        handPoints = {
          left: rebaseHandPoints(displayHandPoints.left, renderPoints.left_wrist),
          right: rebaseHandPoints(displayHandPoints.right, renderPoints.right_wrist)
        };
      } else {
        skeletonModelAnchored = false;
      }

      updateBody(points);
      renderSkeletonGeometry(renderPoints);
      updateHandRig("left", handPoints.left);
      updateHandRig("right", handPoints.right);
    }

    function clearRobot() {
      poseActive = false;
      lastPayload = null;
      targetPoints = null;
      displayPoints = null;
      targetHandPoints = { left: null, right: null };
      displayHandPoints = { left: null, right: null };
      skeletonModelAnchored = false;
      resetModelRig();
      poseWorldScale = null;
      skeletonLines.visible = false;
      jointMarkers.forEach((marker) => { marker.visible = false; });
      jointHalos.forEach((halo) => { halo.visible = false; });
      boneSegments.forEach((segment) => {
        segment.mesh.visible = false;
        segment.glow.visible = false;
      });
      hideHandRigs();
      bodyRoot.visible = false;
      modelRoot.visible = false;
      document.getElementById("status").textContent = "等待动作数据";
      window.setTimeout(() => {
        skeletonLines.visible = true;
        jointMarkers.forEach((marker) => { marker.visible = true; });
        jointHalos.forEach((halo) => { halo.visible = true; });
        boneSegments.forEach((segment) => {
          segment.mesh.visible = true;
          segment.glow.visible = true;
        });
        setSkeletonVisibility();
      }, 30);
    }

    const actionAliases = {
      idle: ["Idle", "Standing"],
      dance: ["Dance", "Dancing"],
      walk: ["Walking", "Walk"],
      run: ["Running", "Run"],
      jump: ["Jump", "Jumping"],
      wave: ["Wave", "Waving"],
      thumbs_up: ["ThumbsUp", "Yes"],
      reset: ["Idle", "Standing"]
    };

    function playModelClip(name) {
      if (!modelMixer) return;
      const candidates = actionAliases[name] || actionAliases.idle;
      const clip = modelRoot.userData.clips?.find((item) =>
        candidates.some((candidate) => item.name.toLowerCase().includes(candidate.toLowerCase()))
      );
      if (!clip) return;
      if (modelAction) modelAction.stop();
      modelAction = modelMixer.clipAction(clip);
      modelAction.reset();
      modelAction.setLoop(THREE.LoopRepeat, Infinity);
      modelAction.paused = actionPaused;
      modelAction.play();
    }

    function playAction(name) {
      actionName = String(name || "idle").toLowerCase();
      playModelClip(actionName);
      document.getElementById("status").textContent = "动作：" + actionName;
    }

    function clearModelRoot() {
      modelMixer = null;
      modelAction = null;
      modelAvailable = false;
      modelRig = null;
      modelDriveReady = false;
      modelPoseDriven = false;
      skeletonModelAnchored = false;
      modelRoot.userData.clips = [];
      while (modelRoot.children.length) {
        const child = modelRoot.children.pop();
        modelRoot.remove(child);
        child.traverse((node) => {
          if (node.geometry) node.geometry.dispose();
          const materials = Array.isArray(node.material) ? node.material : [node.material];
          materials.forEach((material) => material?.dispose?.());
        });
      }
    }

    async function loadRobotModel(url = "") {
      const generation = ++modelLoadGeneration;
      const sourceUrl = String(url || "").trim();
      clearModelRoot();
      if (!sourceUrl) {
        setSkeletonVisibility();
        return;
      }
      try {
        const { GLTFLoader } = await import("./loaders/GLTFLoader.js");
        if (generation !== modelLoadGeneration) return;
        const loader = new GLTFLoader();
        loader.load(sourceUrl, (gltf) => {
          if (generation !== modelLoadGeneration) {
            gltf.scene.traverse((node) => {
              if (node.geometry) node.geometry.dispose();
              const materials = Array.isArray(node.material) ? node.material : [node.material];
              materials.forEach((material) => material?.dispose?.());
            });
            return;
          }
          const model = gltf.scene;
          model.traverse((child) => {
            if (!child.isMesh) return;
            if (sourceUrl.includes("dance_robot_cyber")) {
              const materials = Array.isArray(child.material) ? child.material : [child.material];
              materials.forEach((material) => {
                if (!material) return;
                material.metalness = Math.max(Number(material.metalness) || 0, 0.48);
                material.roughness = Math.min(Number(material.roughness) || 0.5, 0.42);
                material.envMapIntensity = 1.15;
                material.needsUpdate = true;
              });
            }
            child.castShadow = !lowPower;
            child.receiveShadow = true;
          });
          if (sourceUrl.includes("dance_robot_cyber")) {
            const hiddenParts = ["Sword"];
            model.traverse((child) => {
              if (hiddenParts.some((name) => String(child.name).startsWith(name))) {
                child.visible = false;
              }
            });
          }
          const bounds = new THREE.Box3().setFromObject(model);
          const size = bounds.getSize(new THREE.Vector3());
          const targetHeight = 1.72;
          const scale = targetHeight / Math.max(size.y, 0.001);
          model.scale.setScalar(scale);
          const scaledBounds = new THREE.Box3().setFromObject(model);
          model.position.y -= scaledBounds.min.y;
          model.position.x -= (scaledBounds.min.x + scaledBounds.max.x) * 0.5;
          model.position.z -= (scaledBounds.min.z + scaledBounds.max.z) * 0.5;
          modelRoot.add(model);
          modelRoot.userData.clips = gltf.animations || [];
          modelMixer = new THREE.AnimationMixer(model);
          modelAvailable = true;
          modelRig = captureModelRig(model);
          modelPoseDriven = false;
          modelDriveReady = Boolean(
            modelRig.drives.length >= 8 &&
            (modelRig.roles.leftUpperArm || modelRig.roles.rightUpperArm)
          );
          applySkin(activeSkin);
          window.updateSceneStatus(
            modelDriveReady
              ? `角色已就绪：${modelRig.drives.length} 个主骨骼，${modelRig.fingerDrives.length} 个手指骨骼`
              : "模型已加载，但未识别到足够的人形骨骼；已回退到程序化人体"
          );
          setSkeletonVisibility();
          playModelClip(actionName);
          window.updateSceneStatus("机器人模型已就绪，骨架保持显示");
        }, undefined, () => {
          if (generation !== modelLoadGeneration) return;
          modelAvailable = false;
          setSkeletonVisibility();
        });
      } catch (_error) {
        modelAvailable = false;
        setSkeletonVisibility();
      }
    }

    window.updateRobot = (payload) => updateSkeleton(payload);
    window.updateReference = (payload) => updateSkeleton(payload);
    window.clearRobot = clearRobot;
    window.clearReference = clearRobot;
    window.updateSceneStatus = (text) => {
      document.getElementById("status").textContent = String(text || "");
    };
    window.setModelMode = (mode) => {
      modelMode = ["skeleton", "body", "overlay"].includes(mode) ? mode : "overlay";
      setSkeletonVisibility();
    };
    window.setSkin = (name) => applySkin(String(name || "default").toLowerCase());
    window.setSceneTheme = (name) => applyTheme(String(name || "studio").toLowerCase());
    window.playAction = (name) => playAction(name);
    window.setActionPaused = (paused) => {
      actionPaused = Boolean(paused);
      if (modelAction) modelAction.paused = actionPaused;
    };
    window.setImitationScope = (scope) => {
      const allowed = ["full_body", "upper_body", "lower_body", "hands", "head"];
      imitationScope = allowed.includes(scope) ? scope : "full_body";
    };
    window.setRootMotion = (mode) => {
      const allowed = ["none", "sway", "planar"];
      rootMotionMode = allowed.includes(mode) ? mode : "none";
    };
    window.setRobotModelUrl = (url) => { void loadRobotModel(String(url || "")); };
    window.setMotionSmoothing = (value) => {
      motionSmoothing = THREE.MathUtils.clamp(Number(value) || 0.32, 0.08, 0.75);
    };
    window.setMotionPreset = (name) => {
      const presets = { low_latency: 0.62, balanced: 0.32, smooth: 0.18 };
      motionPreset = presets[name] ? name : "balanced";
      motionSmoothing = presets[motionPreset];
    };
    window.resetRobotCamera = resetOrbitCamera;
    window.setLowPower = (enabled) => setLowPower(enabled);
    window.setRenderFps = (fps) => {
      targetRenderFps = Math.round(THREE.MathUtils.clamp(Number(fps) || 45, 30, 60));
      renderIntervalMs = 1000 / targetRenderFps;
      setLowPower(lowPower);
    };
    window.setSceneActive = (active) => {
      sceneActive = Boolean(active);
      if (sceneActive) {
        const now = performance.now();
        lastFrameTime = now;
        lastRenderAt = 0;
        fpsWindowStartedAt = now;
        fpsWindowFrames = 0;
      }
    };
    window.setInterfaceTheme = (theme) => {
      interfaceTheme = String(theme || "dark").toLowerCase() === "light" ? "light" : "dark";
      document.body.dataset.interfaceTheme = interfaceTheme;
    };
    window.getSceneState = () => ({
      interfaceTheme,
      measuredFps,
      sceneActive,
      targetRenderFps,
      pixelRatio: renderer.getPixelRatio(),
      modelMode,
      canvasCount: document.querySelectorAll("canvas").length,
      actorCount: 1,
      robotRootVisible: robotRoot.visible,
      robotSkeletonVisible: skeletonLines.visible,
      skeletonBoneSegmentCount: boneSegments.length,
      skeletonJointHaloCount: jointHalos.length,
      robotBodyVisible: bodyRoot.visible || modelRoot.visible,
      robotProceduralBodyVisible: bodyRoot.visible,
      robotModelRootVisible: modelRoot.visible,
      robotModelAvailable: modelAvailable,
      robotModelDriveReady: modelDriveReady,
      skeletonModelAnchored,
      robotBoneCount: modelRig?.drives.length || 0,
      robotFingerBoneCount: modelRig?.fingerDrives.length || 0,
      handRigVisible: {
        left: handRigs.left.lines.visible,
        right: handRigs.right.lines.visible
      },
      solidPalmVisible: {
        left: handRigs.left.palm.visible,
        right: handRigs.right.palm.visible
      },
      activeSkin,
      activeTheme,
      actionName,
      actionPaused,
      motionSmoothing,
      motionPreset,
      imitationScope,
      rootMotionMode,
      cameraRadius,
      cameraTheta,
      cameraPhi,
      cameraTarget: { x: cameraTarget.x, y: cameraTarget.y, z: cameraTarget.z },
      renderedTriangles: renderer.info.render.triangles,
      lowPower
    });

    function resize() {
      const width = Math.max(window.innerWidth, 1);
      const height = Math.max(window.innerHeight, 1);
      renderer.setSize(width, height, false);
      camera.aspect = width / height;
      camera.updateProjectionMatrix();
    }
    window.addEventListener("resize", resize);
    resize();

    function idlePose(time) {
      const rise = Math.sin(time * 1.7) * 0.012;
      return {
        nose: [0, 1.68 + rise, 0],
        left_eye: [0.035, 1.70 + rise, -0.10],
        right_eye: [-0.035, 1.70 + rise, -0.10],
        left_ear: [0.10, 1.68 + rise, -0.04],
        right_ear: [-0.10, 1.68 + rise, -0.04],
        left_shoulder: [0.23, 1.48 + rise, 0],
        right_shoulder: [-0.23, 1.48 + rise, 0],
        left_elbow: [0.42, 1.23 + rise, 0],
        right_elbow: [-0.42, 1.23 + rise, 0],
        left_wrist: [0.49, 0.98 + rise, 0.02],
        right_wrist: [-0.49, 0.98 + rise, 0.02],
        left_hip: [0.12, 0.92, 0],
        right_hip: [-0.12, 0.92, 0],
        left_knee: [0.13, 0.49, 0.01],
        right_knee: [-0.13, 0.49, 0.01],
        left_ankle: [0.13, 0.08, 0],
        right_ankle: [-0.13, 0.08, 0]
      };
    }

    let lastFrameTime = performance.now();
    let lastRenderAt = 0;
    function animate(now) {
      requestAnimationFrame(animate);
      const elapsedMs = Math.max(0, now - lastFrameTime);
      lastFrameTime = now;
      if (!sceneActive || now - lastRenderAt < renderIntervalMs - 0.25) return;
      lastRenderAt = now;
      fpsWindowFrames += 1;
      if (now - fpsWindowStartedAt >= 1000) {
        measuredFps = fpsWindowFrames * 1000 / Math.max(1, now - fpsWindowStartedAt);
        fpsWindowFrames = 0;
        fpsWindowStartedAt = now;
        updateQualityLabel();
      }
      const delta = Math.min(elapsedMs / 1000, 0.10);
      if (modelMixer) modelMixer.update(actionPaused ? 0 : delta);
      const poseStale = poseActive && now - lastPayloadAt > 900;
      if (poseStale) {
        poseActive = false;
        if (modelPoseDriven) resetModelRig();
      }
      if (!poseActive) {
        const idle = idlePose(now / 1000);
        const payload = {
          joints: idle,
          hands: {},
          edges: [
            ["nose", "left_eye"], ["nose", "right_eye"], ["left_eye", "left_ear"],
            ["right_eye", "right_ear"], ["left_shoulder", "right_shoulder"],
            ["left_shoulder", "left_elbow"], ["left_elbow", "left_wrist"],
            ["right_shoulder", "right_elbow"], ["right_elbow", "right_wrist"],
            ["left_shoulder", "left_hip"], ["right_shoulder", "right_hip"],
            ["left_hip", "right_hip"], ["left_hip", "left_knee"],
            ["left_knee", "left_ankle"], ["right_hip", "right_knee"],
            ["right_knee", "right_ankle"]
          ]
        };
        const points = applyRootMotion(toWorldPoints(payload));
        displayHandPoints = { left: null, right: null };
        renderPose(payload, points, modelDriveReady);
        setSkeletonVisibility();
      } else if (targetPoints) {
        const alpha = THREE.MathUtils.clamp(
          1 - Math.pow(1 - motionSmoothing, delta * 60),
          0.02,
          1.0
        );
        displayPoints = smoothPoints(displayPoints, targetPoints, alpha);
        displayHandPoints = smoothHands(displayHandPoints, targetHandPoints, alpha);
        renderPose(lastPayload, displayPoints, true);
      }
      ring.rotation.z += lowPower ? 0.02 * delta : 0.12 * delta;
      renderer.render(scene, camera);
    }

    applySkin("default");
    applyTheme("studio");
    window.setInterfaceTheme(interfaceTheme);
    setSkeletonVisibility();
    loadRobotModel();
    requestAnimationFrame(animate);
  </script>
</body>
</html>"""
