import * as THREE from "three";

const DT = 1 / 30;
const DURATION_S = 4.0;
const FRAME_COUNT = Math.round(DURATION_S / DT);
const GROUND_MARGIN = 0.02;

const el = (id) => document.getElementById(id);
const clamp = (v, a, b) => Math.min(b, Math.max(a, v));
const clamp01 = (v) => clamp(v, 0, 1);
const smoothstep = (a, b, x) => {
  const t = clamp01((x - a) / (b - a));
  return t * t * (3 - 2 * t);
};
const v3 = (x, y, z) => new THREE.Vector3(x, y, z);

const JOINTS = [
  "hips", "nose",
  "leftShoulder", "rightShoulder", "leftElbow", "rightElbow",
  "leftWrist", "rightWrist",
  "leftHip", "rightHip", "leftKnee", "rightKnee", "leftAnkle", "rightAnkle",
];

const LOWERED = { leftWrist: v3(0.30, 1.04, 0.05), rightWrist: v3(-0.30, 1.04, 0.05) };
const RAISED = { leftWrist: v3(0.36, 1.63, 0.06), rightWrist: v3(-0.36, 1.63, 0.06) };

function liftArc(p, start, end) {
  if (p < start || p > end) return 0;
  return Math.sin(Math.PI * ((p - start) / (end - start)));
}

function makeFrame(index) {
  const t = index * DT;
  const p = (t / DURATION_S) % 1;

  const rightLift = liftArc(p, 0.10, 0.30);
  const leftLift = liftArc(p, 0.60, 0.80);
  const rightPlanted = rightLift <= 1e-6;
  const leftPlanted = leftLift <= 1e-6;

  const jitter = 0.012 * Math.sin(2 * Math.PI * 7 * t);
  const drift = 0.018 * Math.sin(2 * Math.PI * 0.5 * t);
  const sink = 0.045 * Math.pow(Math.max(0, Math.sin(2 * Math.PI * 2.5 * t)), 1.6);

  const hips = v3(
    0.055 * Math.sin(2 * Math.PI * p) + 0.012 * Math.sin(6 * Math.PI * p),
    0.92 + 0.02 * Math.sin(4 * Math.PI * p),
    0,
  );

  const leftHip = v3(hips.x + 0.085, hips.y - 0.045, 0);
  const rightHip = v3(hips.x - 0.085, hips.y - 0.045, 0);

  const baseLeftX = 0.115 + (leftPlanted ? jitter + drift : 0);
  const baseRightX = -0.115 + (rightPlanted ? -jitter - drift : 0);
  const leftAnkle = v3(baseLeftX, 0.02 + 0.058 * leftLift - (leftPlanted ? sink : 0), 0);
  const rightAnkle = v3(baseRightX, 0.02 + 0.058 * rightLift - (rightPlanted ? sink : 0), 0);

  const bend = (lift) => 0.032 + 0.055 * lift;
  const leftKnee = leftHip.clone().lerp(leftAnkle, 0.5).add(v3(0.02, 0, bend(leftLift)));
  const rightKnee = rightHip.clone().lerp(rightAnkle, 0.5).add(v3(-0.02, 0, bend(rightLift)));

  const shoulderCenter = v3(hips.x * 0.55 + 0.02 * Math.sin(2 * Math.PI * p), 1.44, 0);
  const leftShoulder = v3(shoulderCenter.x + 0.17, 1.43, 0);
  const rightShoulder = v3(shoulderCenter.x - 0.17, 1.43, 0);

  const waveLeft = 0.5 + 0.5 * Math.sin(2 * Math.PI * p);
  const waveRight = 0.5 + 0.5 * Math.sin(2 * Math.PI * p + Math.PI);

  const placeArm = (shoulder, wrist) =>
    shoulder.clone().lerp(wrist, 0.52).add(
      v3(Math.sign(shoulder.x) * 0.055, 0, 0.07),
    );
  const leftWrist = LOWERED.leftWrist.clone().lerp(RAISED.leftWrist, smoothstep(0.1, 0.9, waveLeft));
  const rightWrist = LOWERED.rightWrist.clone().lerp(RAISED.rightWrist, smoothstep(0.1, 0.9, waveRight));
  const leftElbow = placeArm(leftShoulder, leftWrist);
  const rightElbow = placeArm(rightShoulder, rightWrist);

  const nose = v3(shoulderCenter.x + 0.04 * Math.sin(2 * Math.PI * p), 1.68, 0);

  return {
    t,
    joints: {
      hips, nose,
      leftShoulder, rightShoulder, leftElbow, rightElbow, leftWrist, rightWrist,
      leftHip, rightHip, leftKnee, rightKnee, leftAnkle, rightAnkle,
    },
    truth: { leftPlanted, rightPlanted },
  };
}

function buildInput() {
  const frames = [];
  for (let i = 0; i < FRAME_COUNT; i += 1) frames.push(makeFrame(i));
  return frames;
}

function detectContacts(frames) {
  const contacts = [];
  const anchors = { left: null, right: null };
  const state = { left: false, right: false };
  let prev = null;

  frames.forEach((frame) => {
    const entry = { left: state.left, right: state.right };
    for (const side of ["left", "right"]) {
      const ankle = frame.joints[`${side}Ankle`];
      const previous = prev ? prev.joints[`${side}Ankle`] : ankle;
      const speed = ankle.distanceTo(previous) / DT;
      const grounded = ankle.y < 0.045;
      const slow = speed < 0.45;
      if (!state[side]) {
        if (grounded && slow) {
          state[side] = true;
          anchors[side] = { x: ankle.x, z: ankle.z };
        }
      } else if (ankle.y > 0.065 || speed > 0.9) {
        state[side] = false;
        anchors[side] = null;
      }
      entry[side] = state[side];
      entry[`${side}Anchor`] = anchors[side] ? { ...anchors[side] } : null;
    }
    contacts.push(entry);
    prev = frame;
  });
  return contacts;
}

function cloneJointMap(joints) {
  const out = {};
  for (const key of JOINTS) out[key] = joints[key].clone();
  return out;
}

function shiftUpperBody(joints, dx) {
  if (Math.abs(dx) < 1e-6) return;
  for (const key of [
    "hips", "nose", "leftShoulder", "rightShoulder", "leftElbow", "rightElbow",
    "leftWrist", "rightWrist", "leftHip", "rightHip", "leftKnee", "rightKnee",
  ]) {
    joints[key].x += dx;
  }
}

function supportRange(joints, truth) {
  const xs = [];
  if (truth.leftPlanted) xs.push(joints.leftAnkle.x);
  if (truth.rightPlanted) xs.push(joints.rightAnkle.x);
  if (!xs.length) return null;
  if (xs.length === 1) return [xs[0] - 0.07, xs[0] + 0.07];
  return [Math.min(...xs) - 0.05, Math.max(...xs) + 0.05];
}

function retargetGeometric(frames) {
  return frames.map((frame) => ({
    joints: cloneJointMap(frame.joints),
    truth: frame.truth,
  }));
}

function retargetContactAware(frames, contacts) {
  const out = [];
  frames.forEach((frame, index) => {
    const joints = cloneJointMap(frame.joints);
    const contact = contacts[index];

    for (const side of ["left", "right"]) {
      const key = `${side}Ankle`;
      if (contact[side] && contact[`${side}Anchor`]) {
        joints[key].x = contact[`${side}Anchor`].x;
        joints[key].z = contact[`${side}Anchor`].z;
        joints[key].y = GROUND_MARGIN;
      }
      const hipKey = `${side}Hip`;
      const kneeKey = `${side}Knee`;
      joints[kneeKey] = joints[hipKey]
        .clone()
        .lerp(joints[key], 0.5)
        .add(v3(side === "left" ? 0.02 : -0.02, 0, 0.032));
    }

    const range = supportRange(joints, frame.truth);
    if (range) {
      const com = joints.hips.x;
      const lo = range[0];
      const hi = range[1];
      if (com < lo) shiftUpperBody(joints, lo - com);
      else if (com > hi) shiftUpperBody(joints, hi - com);
      const shift = clamp(joints.hips.x - frame.joints.hips.x, -0.09, 0.09);
      if (shift !== joints.hips.x - frame.joints.hips.x) {
        shiftUpperBody(joints, (frame.joints.hips.x + shift) - joints.hips.x);
      }
    }

    out.push({ joints, truth: frame.truth });
  });
  return out;
}

function computeMetrics(result) {
  let slideSum = 0;
  let slideCount = 0;
  let penSum = 0;
  let penCount = 0;
  let comBad = 0;
  let comCount = 0;

  result.forEach((frame, index) => {
    const joints = frame.joints;
    const previous = index > 0 ? result[index - 1].joints : null;

    for (const side of ["left", "right"]) {
      const key = `${side}Ankle`;
      const planted = side === "left" ? frame.truth.leftPlanted : frame.truth.rightPlanted;
      penSum += Math.max(0, GROUND_MARGIN - joints[key].y) * 100;
      penCount += 1;
      if (planted && previous) {
        const dx = joints[key].x - previous[key].x;
        const dz = joints[key].z - previous[key].z;
        slideSum += Math.hypot(dx, dz) * 100;
        slideCount += 1;
      }
    }

    const range = supportRange(joints, frame.truth);
    if (range) {
      comCount += 1;
      if (joints.hips.x < range[0] || joints.hips.x > range[1]) comBad += 1;
    }
  });

  return {
    slide: slideCount ? slideSum / slideCount : 0,
    penetration: penCount ? penSum / penCount : 0,
    comViolation: comCount ? (100 * comBad) / comCount : 0,
  };
}

const BONE_ROLES = {
  hips: ["hips"],
  spine: ["abdomen", "spine1", "spine"],
  chest: ["torso", "chest", "spine2", "upperchest"],
  neck: ["neck"],
  head: ["head"],
  leftUpperArm: ["upperarml"],
  leftLowerArm: ["lowerarml"],
  leftHand: ["handl", "wristl"],
  rightUpperArm: ["upperarmr"],
  rightLowerArm: ["lowerarmr"],
  rightHand: ["handr", "wristr"],
  leftUpperLeg: ["upperlegl"],
  leftLowerLeg: ["lowerlegl"],
  leftFoot: ["footl"],
  rightUpperLeg: ["upperlegr"],
  rightLowerLeg: ["lowerlegr"],
  rightFoot: ["footr"],
};

const norm = (name) => name.toLowerCase().replace(/[^a-z0-9]/g, "");

function findBone(root, aliases) {
  let best = null;
  root.traverse((child) => {
    if (best || !child.isBone) return;
    const name = norm(child.name);
    if (aliases.some((alias) => name.endsWith(alias))) best = child;
  });
  return best;
}

function boneDepth(bone) {
  let depth = 0;
  let current = bone;
  while (current && current.parent) {
    depth += 1;
    current = current.parent;
  }
  return depth;
}

function captureRest(bone) {
  if (!bone) return null;
  const worldPosition = new THREE.Vector3();
  const worldQuaternion = new THREE.Quaternion();
  bone.getWorldPosition(worldPosition);
  bone.getWorldQuaternion(worldQuaternion);
  const child = bone.children.find((c) => c.isBone);
  const direction = new THREE.Vector3(0, 1, 0).applyQuaternion(worldQuaternion);
  if (child) {
    child.getWorldPosition(direction);
    direction.sub(worldPosition);
  }
  if (direction.lengthSq() < 1e-10) direction.set(0, 1, 0).applyQuaternion(worldQuaternion);
  return {
    bone,
    restWorldQuaternion: worldQuaternion,
    restDirection: direction.normalize(),
    restLocalPosition: bone.position.clone(),
    depth: boneDepth(bone),
  };
}

class RobotRig {
  constructor(gltf, initialJoints) {
    this.group = gltf.scene;
    this.group.traverse((child) => {
      if (child.isMesh) {
        child.castShadow = false;
        child.receiveShadow = false;
      }
    });
    this.group.updateMatrixWorld(true);
    this.roles = {};
    for (const [role, aliases] of Object.entries(BONE_ROLES)) {
      this.roles[role] = findBone(this.group, aliases);
    }
    this.drives = Object.entries(this.roles)
      .filter(([role]) => role !== "hips")
      .map(([, bone]) => captureRest(bone))
      .filter(Boolean)
      .sort((a, b) => a.depth - b.depth);

    this.feet = { left: this.roles.leftFoot || this.roles.leftLowerLeg, right: this.roles.rightFoot || this.roles.rightLowerLeg };
    this.hipsBone = this.roles.hips;

    const hipsWorld = new THREE.Vector3();
    if (this.hipsBone) this.hipsBone.getWorldPosition(hipsWorld);
    const footWorld = new THREE.Vector3();
    if (this.feet.left) this.feet.left.getWorldPosition(footWorld);
    this.restHipsWorld = hipsWorld.clone();
    this.groundY = footWorld.y;
    this.scale = (hipsWorld.y - footWorld.y) / (initialJoints.hips.y - 0.02);
    this.hipsRest = initialJoints.hips.clone();
    this.hipsParentInverse = new THREE.Matrix4();
  }

  setVisible(visible) {
    this.group.visible = visible;
  }

  apply(joints, contact, driveFeet) {
    const group = this.group;
    const targets = new Map();

    const dir = (fromKey, toKey) => joints[toKey].clone().sub(joints[fromKey]).normalize();
    const setDir = (role, desired) => {
      const drive = this.drives.find((d) => d.bone === this.roles[role]);
      if (!drive || desired.lengthSq() < 1e-10) return;
      const delta = new THREE.Quaternion().setFromUnitVectors(drive.restDirection, desired.clone().normalize());
      targets.set(drive.bone, delta.multiply(drive.restWorldQuaternion.clone()));
    };

    const shoulderCenter = joints.leftShoulder.clone().add(joints.rightShoulder).multiplyScalar(0.5);
    const torsoDir = shoulderCenter.clone().sub(joints.hips).normalize();

    setDir("spine", torsoDir);
    setDir("chest", torsoDir);
    setDir("neck", joints.nose.clone().sub(shoulderCenter));
    setDir("head", v3(joints.nose.x, joints.nose.y + 0.1, joints.nose.z).sub(joints.nose));
    setDir("leftUpperArm", dir("leftShoulder", "leftElbow"));
    setDir("leftLowerArm", dir("leftElbow", "leftWrist"));
    setDir("leftHand", joints.leftWrist.clone().add(joints.leftWrist.clone().sub(joints.leftElbow).multiplyScalar(0.8)).sub(joints.leftWrist));
    setDir("rightUpperArm", dir("rightShoulder", "rightElbow"));
    setDir("rightLowerArm", dir("rightElbow", "rightWrist"));
    setDir("rightHand", joints.rightWrist.clone().add(joints.rightWrist.clone().sub(joints.rightElbow).multiplyScalar(0.8)).sub(joints.rightWrist));
    setDir("leftUpperLeg", dir("leftHip", "leftKnee"));
    setDir("leftLowerLeg", dir("leftKnee", "leftAnkle"));
    setDir("rightUpperLeg", dir("rightHip", "rightKnee"));
    setDir("rightLowerLeg", dir("rightKnee", "rightAnkle"));

    if (driveFeet) {
      setDir("leftFoot", v3(0, -0.01, 0.14));
      setDir("rightFoot", v3(0, -0.01, 0.14));
    }

    if (this.hipsBone) {
      const parent = this.hipsBone.parent;
      if (parent) parent.updateWorldMatrix(true, false);
      this.hipsParentInverse.copy(parent.matrixWorld).invert();
      const offset = joints.hips.clone().sub(this.hipsRest).multiplyScalar(this.scale);
      const targetWorld = this.restHipsWorld.clone().add(offset);
      this.hipsBone.position.copy(targetWorld.applyMatrix4(this.hipsParentInverse));
      this.hipsBone.updateMatrix();
    }

    group.updateMatrixWorld(true);

    const parentWorld = new THREE.Quaternion();
    const inverseParent = new THREE.Quaternion();
    for (const drive of this.drives) {
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
    group.updateMatrixWorld(true);
  }

  footWorld(side, target) {
    const bone = this.feet[side];
    if (!bone) return target.set(0, 0, 0);
    return bone.getWorldPosition(target);
  }
}

function buildStage() {
  const scene = new THREE.Scene();
  scene.background = new THREE.Color(0x0d0f11);
  scene.fog = new THREE.Fog(0x0d0f11, 5.5, 11);

  scene.add(new THREE.HemisphereLight(0xcfe6ff, 0x0a0d10, 1.05));
  const key = new THREE.DirectionalLight(0xffffff, 1.5);
  key.position.set(2.4, 4.2, 3.4);
  scene.add(key);
  const rim = new THREE.DirectionalLight(0x34d399, 0.85);
  rim.position.set(-2.6, 1.8, -2.4);
  scene.add(rim);

  const ground = new THREE.Mesh(
    new THREE.PlaneGeometry(14, 14),
    new THREE.MeshStandardMaterial({ color: 0x12161a, roughness: 0.95, metalness: 0 }),
  );
  ground.rotation.x = -Math.PI / 2;
  ground.position.y = 0.014;
  scene.add(ground);

  const grid = new THREE.GridHelper(14, 28, 0x2a3138, 0x1b2025);
  grid.position.y = 0.016;
  scene.add(grid);

  return { scene, ground, grid };
}

function makeContactRing(color) {
  const ring = new THREE.Mesh(
    new THREE.RingGeometry(0.05, 0.075, 28),
    new THREE.MeshBasicMaterial({ color, transparent: true, opacity: 0.85, side: THREE.DoubleSide }),
  );
  ring.rotation.x = -Math.PI / 2;
  return ring;
}

function makeComMarker() {
  const group = new THREE.Group();
  const ball = new THREE.Mesh(
    new THREE.SphereGeometry(0.032, 16, 16),
    new THREE.MeshBasicMaterial({ color: 0xfacc15 }),
  );
  group.add(ball);
  const line = new THREE.Mesh(
    new THREE.CylinderGeometry(0.004, 0.004, 1, 6),
    new THREE.MeshBasicMaterial({ color: 0x8a93a0, transparent: true, opacity: 0.6 }),
  );
  group.add(line);
  group.userData = { ball, line };
  return group;
}

function makeSupportBar() {
  const bar = new THREE.Mesh(
    new THREE.BoxGeometry(1, 1, 1),
    new THREE.MeshBasicMaterial({ color: 0x34d399, transparent: true, opacity: 0.35 }),
  );
  bar.visible = false;
  return bar;
}

async function loadRobot(url) {
  const { GLTFLoader } = await import("./loaders/GLTFLoader.js");
  const loader = new GLTFLoader();
  return new Promise((resolve, reject) => {
    loader.load(url, (gltf) => resolve(gltf), undefined, reject);
  });
}

const state = {
  playing: true,
  speed: 1,
  index: 0,
  contacts: [],
  results: { geo: [], contact: [] },
  metrics: null,
  yaw: 0,
  pitch: 0.06,
};

function fmt(value, digits = 2) {
  return Number.isFinite(value) ? value.toFixed(digits) : "--";
}

function renderMetrics() {
  const { geo, contact } = state.metrics;
  el("m-slide-geo").textContent = fmt(geo.slide);
  el("m-slide-new").textContent = fmt(contact.slide);
  el("m-pen-geo").textContent = fmt(geo.penetration);
  el("m-pen-new").textContent = fmt(contact.penetration);
  el("m-com-geo").textContent = fmt(geo.comViolation, 1);
  el("m-com-new").textContent = fmt(contact.comViolation, 1);

  const pct = (a, b) => (a <= 1e-6 ? (b <= 1e-6 ? "0%" : "-") : `${Math.round((1 - b / a) * 100)}%`);
  el("d-slide").textContent = pct(geo.slide, contact.slide);
  el("d-pen").textContent = pct(geo.penetration, contact.penetration);
  el("d-com").textContent = pct(geo.comViolation, contact.comViolation);
}

function bindControls() {
  el("btn-play").addEventListener("click", () => {
    state.playing = !state.playing;
    el("btn-play").textContent = state.playing ? "暂停" : "播放";
  });
  el("btn-reset").addEventListener("click", () => {
    state.index = 0;
  });
  el("btn-speed").addEventListener("click", () => {
    state.speed = state.speed === 1 ? 0.35 : 1;
    el("btn-speed").textContent = state.speed === 1 ? "1.0×" : "0.35× 慢放";
  });
  const scrub = el("scrub");
  const seek = (event) => {
    const rect = scrub.getBoundingClientRect();
    const ratio = clamp01((event.clientX - rect.left) / rect.width);
    state.index = Math.round(ratio * (FRAME_COUNT - 1));
  };
  scrub.addEventListener("pointerdown", (event) => {
    seek(event);
    scrub.setPointerCapture(event.pointerId);
  });
  scrub.addEventListener("pointermove", (event) => {
    if (scrub.hasPointerCapture(event.pointerId)) seek(event);
  });
}

function bindOrbit(canvas) {
  let dragging = false;
  let lastX = 0;
  let lastY = 0;
  canvas.addEventListener("pointerdown", (event) => {
    dragging = true;
    lastX = event.clientX;
    lastY = event.clientY;
    canvas.setPointerCapture(event.pointerId);
  });
  canvas.addEventListener("pointermove", (event) => {
    if (!dragging) return;
    state.yaw = clamp(state.yaw + (event.clientX - lastX) * 0.006, -0.9, 0.9);
    state.pitch = clamp(state.pitch + (event.clientY - lastY) * 0.004, -0.25, 0.5);
    lastX = event.clientX;
    lastY = event.clientY;
  });
  const stop = () => {
    dragging = false;
  };
  canvas.addEventListener("pointerup", stop);
  canvas.addEventListener("pointercancel", stop);
}

async function main() {
  const canvas = el("scene");
  const renderer = new THREE.WebGLRenderer({ canvas, antialias: true });
  renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
  renderer.setScissorTest(true);
  const { scene } = buildStage();

  const input = buildInput();
  state.contacts = detectContacts(input);
  const geoFrames = retargetGeometric(input);
  const contactFrames = retargetContactAware(input, state.contacts);
  state.results = { geo: geoFrames, contact: contactFrames };
  state.metrics = {
    geo: computeMetrics(geoFrames),
    contact: computeMetrics(contactFrames),
  };
  renderMetrics();
  el("frame-read").textContent = `帧 0 / ${FRAME_COUNT}`;

  let gltf;
  try {
    gltf = await loadRobot("./dance_robot_cyber.glb");
    el("model-chip").textContent = "机器人已就绪";
  } catch (error) {
    el("model-chip").textContent = "模型加载失败";
    console.error(error);
  }

  const leftRig = new RobotRig(gltf, input[0].joints);
  leftRig.group.position.x = -0.82;
  scene.add(leftRig.group);

  const gltf2 = await loadRobot("./dance_robot_cyber.glb");
  const rightRig = new RobotRig(gltf2, input[0].joints);
  rightRig.group.position.x = 0.82;
  scene.add(rightRig.group);

  const stage = new THREE.Group();
  scene.add(stage);

  const rings = {
    left: { geo: makeContactRing(0x9aa3ad), contact: makeContactRing(0x34d399) },
    right: { geo: makeContactRing(0x9aa3ad), contact: makeContactRing(0x34d399) },
  };
  const coms = { geo: makeComMarker(), contact: makeComMarker() };
  const bars = { geo: makeSupportBar(), contact: makeSupportBar() };
  const objects = [];
  const mk = (label) => {
    const group = new THREE.Group();
    group.add(rings.left[label], rings.right[label], coms[label], bars[label]);
    return group;
  };
  const geoOverlay = mk("geo");
  const contactOverlay = mk("contact");
  geoOverlay.position.set(leftRig.group.position.x, 0, 0);
  contactOverlay.position.set(rightRig.group.position.x, 0, 0);
  scene.add(geoOverlay, contactOverlay);

  const camL = new THREE.PerspectiveCamera(30, 1, 0.1, 40);
  const camR = new THREE.PerspectiveCamera(30, 1, 0.1, 40);

  function layout() {
    const rect = canvas.getBoundingClientRect();
    const width = Math.max(1, Math.floor(rect.width));
    const height = Math.max(1, Math.floor(rect.height));
    renderer.setSize(width, height, false);
    camL.aspect = width / 2 / height;
    camR.aspect = width / 2 / height;
    camL.updateProjectionMatrix();
    camR.updateProjectionMatrix();
  }
  window.addEventListener("resize", layout);
  layout();

  const tmp = new THREE.Vector3();

  function placeOverlay(overlay, rig, frame, label, baseX) {
    const joints = frame.joints;
    for (const side of ["left", "right"]) {
      rig.footWorld(side, tmp);
      const ring = rings[side][label];
      ring.position.set(tmp.x - baseX, rig.groundY + 0.002, tmp.z);
      const touching = side === "left" ? state.contacts[state.index]?.left : state.contacts[state.index]?.right;
      ring.material.opacity = touching ? 0.95 : 0.18;
      ring.material.color.setHex(touching ? 0x34d399 : 0x9aa3ad);
    }
    const com = coms[label];
    com.userData.ball.position.set(joints.hips.x, joints.hips.y, joints.hips.z);
    com.userData.line.position.set(joints.hips.x, joints.hips.y / 2, joints.hips.z);
    com.userData.line.scale.y = Math.max(0.01, joints.hips.y);
    const range = supportRange(joints, frame.truth);
    const bar = bars[label];
    if (range) {
      bar.visible = true;
      const width = Math.max(0.04, range[1] - range[0]);
      bar.position.set((range[0] + range[1]) / 2, rig.groundY + 0.001, 0.02);
      bar.scale.set(width, 0.004, 0.3);
      const inside = joints.hips.x >= range[0] && joints.hips.x <= range[1];
      bar.material.color.setHex(inside ? 0x34d399 : 0xf97362);
    } else {
      bar.visible = false;
    }
  }

  const clock = new THREE.Clock();
  let accumulator = 0;
  let fpsFrames = 0;
  let fpsAt = performance.now();

  function cameraFor(camera, rig, baseX) {
    const target = v3(baseX, 0.85, 0);
    const radius = 3.0;
    const yaw = state.yaw;
    const pitch = state.pitch;
    camera.position.set(
      baseX + Math.sin(yaw) * radius,
      0.85 + radius * (0.22 + pitch * 0.8),
      Math.cos(yaw) * radius,
    );
    camera.lookAt(target);
  }

  function tick() {
    requestAnimationFrame(tick);
    const dt = Math.min(clock.getDelta(), 0.1);

    if (state.playing) {
      accumulator += dt * state.speed;
      while (accumulator >= DT) {
        accumulator -= DT;
        state.index = (state.index + 1) % FRAME_COUNT;
      }
    }

    const index = state.index;
    const frameGeo = state.results.geo[index];
    const frameContact = state.results.contact[index];
    const contact = state.contacts[index];

    leftRig.apply(frameGeo.joints, contact, false);
    rightRig.apply(frameContact.joints, contact, true);

    placeOverlay(geoOverlay, leftRig, frameGeo, "geo", leftRig.group.position.x);
    placeOverlay(contactOverlay, rightRig, frameContact, "contact", rightRig.group.position.x);

    const rect = canvas.getBoundingClientRect();
    const width = Math.max(1, Math.floor(rect.width));
    const height = Math.max(1, Math.floor(rect.height));
    const half = Math.floor(width / 2);

    cameraFor(camL, leftRig, leftRig.group.position.x);
    cameraFor(camR, rightRig, rightRig.group.position.x);

    rightRig.setVisible(false);
    contactOverlay.visible = false;
    renderer.setViewport(0, 0, half, height);
    renderer.setScissor(0, 0, half, height);
    renderer.render(scene, camL);

    rightRig.setVisible(true);
    contactOverlay.visible = true;
    leftRig.setVisible(false);
    geoOverlay.visible = false;
    renderer.setViewport(half, 0, width - half, height);
    renderer.setScissor(half, 0, width - half, height);
    renderer.render(scene, camR);

    leftRig.setVisible(true);
    geoOverlay.visible = true;

    const ratio = index / (FRAME_COUNT - 1);
    el("scrub-fill").style.width = `${ratio * 100}%`;
    el("scrub-head").style.left = `${ratio * 100}%`;
    el("time-read").textContent = `t = ${(index * DT).toFixed(2)}s`;
    el("frame-read").textContent = `帧 ${index} / ${FRAME_COUNT - 1}`;

    fpsFrames += 1;
    const now = performance.now();
    if (now - fpsAt >= 500) {
      el("fps-chip").textContent = `${Math.round((fpsFrames * 1000) / (now - fpsAt))} FPS`;
      fpsFrames = 0;
      fpsAt = now;
    }
  }

  bindControls();
  bindOrbit(canvas);
  tick();
}

main().catch((error) => {
  el("model-chip").textContent = "初始化失败";
  console.error(error);
});
