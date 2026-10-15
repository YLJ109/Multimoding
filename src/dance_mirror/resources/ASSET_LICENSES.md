# Bundled Visual Asset Licenses

## Bundled cybernetic humanoid

File: `src/dance_mirror/resources/dance_robot_cyber.glb`

The bundled default is Quaternius' adult-proportioned cyberpunk character,
with a full-body rig and Idle, Walk, Run, Wave, Punch, Kick, and Sword
animation clips. DanceMirror hides the optional sword prop at runtime and
adds its own 21-landmark hand overlay.

Source:
- <https://quaternius.com/packs/animatedcyberpunk.html>
- Author: Quaternius
- License: CC0 1.0 <https://creativecommons.org/publicdomain/zero/1.0/>
- Verified mirror: <https://github.com/trebeljahr/quaternius-showcase>

No Spider-Man, Ultraman, or other protected character IP is bundled. Users may
import their own licensed GLB/GLTF assets locally.

## Curated downloadable humanoid references

The application can download the following Khronos glTF Sample Asset on
demand. It is cached under the user's local application data directory and is
not distributed in this repository.

- `RiggedFigure.glb`: Rigged Figure, Cesium, CC BY 4.0.
  - Source: <https://github.com/KhronosGroup/glTF-Sample-Assets/tree/main/Models/RiggedFigure>
  - License: <https://creativecommons.org/licenses/by/4.0/>

These assets expose body and limb joints but no articulated finger bones.
DanceMirror therefore overlays its 21-landmark hand rig and a visible palm mesh.

## Three.js and GLTFLoader

Files:
- `src/dance_mirror/resources/three.module.min.js`
- `src/dance_mirror/resources/three.core.min.js`
- `src/dance_mirror/resources/loaders/GLTFLoader.js`
- `src/dance_mirror/resources/utils/BufferGeometryUtils.js`

Three.js and its example loaders are distributed under the MIT License.
Version: `0.180.0`.

## Python runtime dependencies

The release package must retain the upstream license and notice files for installed
Python distributions. The main runtime components are:

| Component | Distribution | License boundary |
|---|---|---|
| PyQt6, Qt6, QtWebEngine | Riverbank / Qt | GPL or commercial terms depending on distribution |
| PyQt6-Fluent-Widgets | qfluentwidgets | GPL-3.0 project license; review before proprietary distribution |
| Ultralytics and YOLO weights | Ultralytics | AGPL-3.0 or separate commercial license |
| PyTorch and torchvision | PyTorch Foundation | BSD-style licenses |
| MediaPipe | Google | Apache-2.0 |
| OpenCV Python wheels | OpenCV | Apache-2.0; bundled codecs may have additional terms |
| httpx, NumPy, SciPy, einops | respective projects | permissive open-source licenses |

This table is an engineering checklist, not a substitute for the exact license
files installed in the selected environment. A release must not bundle YOLO
weights or media unless the corresponding distribution right has been confirmed.
