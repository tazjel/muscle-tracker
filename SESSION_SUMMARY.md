# GTD3D Session Summary — 2026-04-07

## Done

### Rivals Research (10 Repos Analyzed)
Searched GitHub for repositories doing photorealistic 3D humans in JavaScript/WebGL. Identified and documented 10 relevant projects with pros/cons:

| # | Repository | Stars | Relevance |
|---|-----------|-------|-----------|
| 1 | **mrdoob/three.js** (SSS examples) | 100k+ | Gold-standard WebGL engine, has SSS skin shaders |
| 2 | **pixiv/three-vrm** | ~5k | VRM avatar loading, bone/blendshape handling |
| 3 | **readyplayerme/visage** | — | Drop-in avatar rendering, stylized (not photorealistic) |
| 4 | **google/mediapipe** (JS) | 30k+ | Body/face tracking, no 3D rendering |
| 5 | **yeemachine/kalidokit** | ~5k | IK math bridge for MediaPipe → Three.js |
| 6 | **BabylonJS/Babylon.js** | 25k+ | Strong PBR pipeline, heavier than Three.js |
| 7 | **EpicGames/PixelStreaming** | — | Unreal MetaHuman via WebRTC, GPU-server dependent |
| 8 | **duixcom/Duix-Avatar** | 12k+ | AI avatar cloning, 2D neural rendering |
| 9 | **egemenertugrul/wolf3d-readyplayerme-threejs-boilerplate** | ~50 | RPM + Mixamo animation reference architecture |
| 10 | **makehumancommunity/makehuman-js** | — | Closest philosophy to GTD3d, mostly abandoned |

### Rivals Cloned into `/rivals/`
1. **wolf3d-readyplayerme-threejs-boilerplate** — Cloned, installed, ran on port 8081. **Verdict: Not realistic** (stylized metaverse look).
2. **threejs_rival** (mrdoob/three.js full repo) — Cloned, served on port 8082.
   - `webgl_materials_subsurface_scattering.html` — ✅ 0 console errors, but renders a bunny (not human).
   - `webgl_materials_normalmap.html` — ✅ Photorealistic Lee Perry-Smith head scan with diffuse/specular/normal maps. **User liked the realism but noted it's only upper head, not full body.**
3. **pixiv/three-vrm** — Cloned, `npm install --legacy-peer-deps` started but session ended before build/run.

## Pending
- **three-vrm**: Finish install, build, run dev server, verify with `agent_browser.py`, open in Chrome.
- Remaining rivals to clone and test (BabylonJS, Kalidokit, etc.).
- Deep investigation of the **Lee Perry-Smith normal map pipeline** — user flagged this as an interesting technique to study for GTD3d's MPFB2 skin upgrade.

## Next Steps
1. Continue cloning and testing remaining rival repos from the list.
2. For each: `agent_browser.py console` first → fix errors → `start chrome` only if clean.
3. Create a comparative report of all rivals vs GTD3d's current viewer capabilities.
4. Extract actionable shader/material techniques (SSS, normal maps, PBR) that can be ported to GTD3d's MPFB2 pipeline.

## Key User Preferences (This Session)
- **Auto-run everything** — user strongly dislikes clicking "Run" buttons. Use `SafeToAutoRun: true` for all safe commands.
- **Always use `agent_browser.py console`** before opening Chrome — never send a URL to the user without verifying 0 console errors first.
