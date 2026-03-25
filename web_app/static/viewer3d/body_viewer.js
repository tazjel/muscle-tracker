/**
 * body_viewer.js — Muscle Tracker 3D Viewer (Three.js r160+)
 * ─────────────────────────────────────────────────────────────
 * Supports:
 *   ?model=path.glb   — load GLB / glTF
 *   ?obj=path.obj     — load legacy OBJ (fallback)
 *
 * Exposes window.bodyViewer for MeasurementOverlay integration.
 */

import * as THREE from 'https://cdn.jsdelivr.net/npm/three@0.160.0/build/three.module.js';
import { OrbitControls }      from 'https://cdn.jsdelivr.net/npm/three@0.160.0/examples/jsm/controls/OrbitControls.js';
import { PointerLockControls } from 'https://cdn.jsdelivr.net/npm/three@0.160.0/examples/jsm/controls/PointerLockControls.js';
import { GLTFLoader }    from 'https://cdn.jsdelivr.net/npm/three@0.160.0/examples/jsm/loaders/GLTFLoader.js';
import { OBJLoader }     from 'https://cdn.jsdelivr.net/npm/three@0.160.0/examples/jsm/loaders/OBJLoader.js';
import { DRACOLoader }   from 'https://cdn.jsdelivr.net/npm/three@0.160.0/examples/jsm/loaders/DRACOLoader.js';
import { RGBELoader }    from 'https://cdn.jsdelivr.net/npm/three@0.160.0/examples/jsm/loaders/RGBELoader.js';
import { MuscleHighlighter, buildMusclePanel, buildSkinUploadPanel } from './muscle_highlighter.js';
import { EffectComposer } from 'https://cdn.jsdelivr.net/npm/three@0.160.0/examples/jsm/postprocessing/EffectComposer.js';
import { RenderPass }     from 'https://cdn.jsdelivr.net/npm/three@0.160.0/examples/jsm/postprocessing/RenderPass.js';
import { SSAOPass }       from 'https://cdn.jsdelivr.net/npm/three@0.160.0/examples/jsm/postprocessing/SSAOPass.js';
import { OutputPass }     from 'https://cdn.jsdelivr.net/npm/three@0.160.0/examples/jsm/postprocessing/OutputPass.js';

// ── Pro-Photo Shader Extensions ──────────────────────────────────────────────
const _VIGNETTE_SHADER = {
    uniforms: {
        "tDiffuse": { value: null },
        "offset":   { value: 1.0 },
        "darkness": { value: 1.5 }
    },
    vertexShader: `
        varying vec2 vUv;
        void main() {
            vUv = uv;
            gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0);
        }`,
    fragmentShader: `
        uniform sampler2D tDiffuse;
        uniform float offset;
        uniform float darkness;
        varying vec2 vUv;
        void main() {
            vec4 texel = texture2D(tDiffuse, vUv);
            vec2 uv = (vUv - 0.5) * 2.0;
            float dist = length(uv);
            float vigor = smoothstep(offset, offset - 0.8, dist * darkness);
            gl_FragColor = vec4(texel.rgb * vigor, texel.a);
            
            // Subtle Film Grain
            float x = (vUv.x + 4.0 ) * (vUv.y + 4.0 ) * 10.0;
            float grain = mod((mod(x, 13.0) + 1.0) * (mod(x, 123.0) + 1.0), 0.01) - 0.005;
            gl_FragColor.rgb += grain * 0.12;
        }`
};

import { ShaderPass } from 'https://cdn.jsdelivr.net/npm/three@0.160.0/examples/jsm/postprocessing/ShaderPass.js';
import { UnrealBloomPass } from 'https://cdn.jsdelivr.net/npm/three@0.160.0/examples/jsm/postprocessing/UnrealBloomPass.js';

// ── Scene globals ─────────────────────────────────────────────────────────────
let scene, camera, renderer, controls;
let bodyMesh      = null;   // the loaded mesh object
let heatmapOn     = false;
const _muscleHL   = new MuscleHighlighter();  // muscle group highlighter
let origMaterials = [];     // stored to restore after heatmap
const _originalMaterials = new Map();  // mesh → original loaded material (for texture toggle)
const raycaster  = new THREE.Raycaster();
const _mouse     = new THREE.Vector2();

// ── SSAO post-processing globals ──────────────────────────────────────────────
let _composer = null;
let _ssaoPass = null;
let _ssaoEnabled = true;  // default on for Studio/Outdoor, toggled off for Clinical

// ── Measure mode globals ───────────────────────────────────────────────────────
let _measureMode   = false;
let _measurePoints = [];   // [{point: THREE.Vector3, marker: THREE.Mesh}]
let _measureLines  = [];   // THREE.Line objects in scene
let _measureLabels = [];   // DOM div elements

// ── Cross-section globals ──────────────────────────────────────────────────────
let _sectionPlane   = null;
let _sectionOutline = null;

// ── Room globals ─────────────────────────────────────────────────────────────
let _roomGroup   = null;
let _roomOn      = false;
let _contactShadow = null;
const _ROOM_W = 714;    // 4m in scene units
const _ROOM_H = 536;    // 3m
const _ROOM_D = 1071;   // 6m
const _roomWalls = {};   // name → THREE.Mesh

// ── Mirror globals ───────────────────────────────────────────────────────────
let _cubeCamera       = null;
let _cubeRenderTarget = null;
let _mirrorWallIndex  = -1;  // -1=off, 0=back, 1=left, 2=right, 3=front
const _MIRROR_WALLS   = ['back', 'left', 'right', 'front'];
let _mirrorWallMesh   = null;
let _preMirrorMat     = null;

// ── Walk mode globals ────────────────────────────────────────────────────────
let _walkMode        = false;
let _pointerControls = null;
const _moveState     = { forward: false, backward: false, left: false, right: false, zoomIn: false, zoomOut: false };
const _moveDirection = new THREE.Vector3();
const _WALK_SPEED    = 200;
const _EYE_HEIGHT    = 300;
let _walkClock       = new THREE.Clock(false);

// ── Props globals ────────────────────────────────────────────────────────────
let _propsGroup = null;
let _propsOn    = false;

// ── Light groups ─────────────────────────────────────────────────────────────
let _studioLightObjs    = [];
let _roomLightObjs      = [];
let _currentLightPreset = 'clinical';

// ── V8 globals ───────────────────────────────────────────────────────────────
let _meshList    = [];
let _ghostMesh   = null;
let _autoRotate  = false;
let _gridHelper  = null;
let _camTransition = null;
let _timelineTimer = null;
let _cachedProfile = null;       // Cached body profile for live deformation calls
let _deformDebounceTimer = null; // Debounce timer for update_deformation endpoint

// ── V12 globals ──────────────────────────────────────────────────────────────
let _ringGroup      = null;
let _ghostRingGroup = null;
let _ringsVisible   = false;
let _ringLabels     = [];  // DOM elements for ring labels

// ── V14 globals ──────────────────────────────────────────────────────────────
let _growthMode  = false;
let _sliceMode   = false;
let _sliceGroup  = null;

// ── V15 globals ──────────────────────────────────────────────────────────────
let _axisGroup      = null;
let _axisVisible    = false;
let _profileVisible = false;
let _ghostRich      = {};

// ── Auth ──────────────────────────────────────────────────────────────────────
let _viewerToken    = null;
let _currentMeshId  = null;

async function _autoLogin() {
  try {
    const r = await fetch('/web_app/api/login', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ email: 'demo@muscle.com' }),
    });
    const d = await r.json();
    if (d.token) _viewerToken = d.token;
  } catch (e) {
    console.warn('Viewer auto-login failed:', e);
  }
}

function _authHeaders() {
  return _viewerToken
    ? { 'Content-Type': 'application/json', 'Authorization': `Bearer ${_viewerToken}` }
    : { 'Content-Type': 'application/json' };
}

function _customerId() {
  return new URLSearchParams(window.location.search).get('customer') || '1';
}

// ── Procedural skin texture — multi-layer photorealistic skin ──────────────────
function _createSkinColorMap(size = 1024) {
  const canvas = document.createElement('canvas');
  canvas.width = canvas.height = size;
  const ctx = canvas.getContext('2d');

  // Base skin tone — warm mid-tone
  ctx.fillStyle = '#D4A373';
  ctx.fillRect(0, 0, size, size);

  // Layer 0: Vertical warmth gradient (top=warmer/redder, bottom=slightly paler)
  // Simulates real skin: face/chest is warmer, legs are cooler
  const warmGrad = ctx.createLinearGradient(0, 0, 0, size);
  warmGrad.addColorStop(0, 'rgba(210,110,80,0.12)');   // warm red for head/chest
  warmGrad.addColorStop(0.35, 'rgba(200,130,90,0.06)');  // mid warmth
  warmGrad.addColorStop(0.65, 'rgba(180,140,110,0.0)');  // neutral torso
  warmGrad.addColorStop(1, 'rgba(160,135,120,0.05)');    // slightly cooler legs
  ctx.fillStyle = warmGrad;
  ctx.fillRect(0, 0, size, size);

  // Layer 1: Subsurface color zones — stronger for visible warmth variation
  const zones = [
    { color: 'rgba(200,85,70,0.14)',   count: 12, rMin: 250, rMax: 500 },  // blood flush (cheeks, chest)
    { color: 'rgba(185,100,65,0.12)',  count: 18, rMin: 200, rMax: 400 },  // warm undertone
    { color: 'rgba(210,145,95,0.10)',  count: 15, rMin: 60, rMax: 110 },  // golden highlights
    { color: 'rgba(150,90,70,0.09)',   count: 12, rMin: 40, rMax: 100 },  // shadow warmth
    { color: 'rgba(180,125,100,0.07)', count: 20, rMin: 25, rMax: 80 },   // subtle tone variation
  ];
  for (const zone of zones) {
    for (let i = 0; i < zone.count; i++) {
      const x = Math.random() * size;
      const y = Math.random() * size;
      const r = zone.rMin + Math.random() * (zone.rMax - zone.rMin);
      const grad = ctx.createRadialGradient(x, y, 0, x, y, r);
      grad.addColorStop(0, zone.color);
      grad.addColorStop(0.5, zone.color.replace(/[\d.]+\)$/, '0.04)'));
      grad.addColorStop(1, 'rgba(200,153,110,0)');
      ctx.fillStyle = grad;
      ctx.fillRect(0, 0, size, size);
    }
  }

  // Layer 2: Visible vein network (forearms, inner wrists)
  ctx.globalAlpha = 0.06;
  ctx.strokeStyle = 'rgba(100,70,120,1)';
  ctx.lineWidth = 1.8;
  for (let i = 0; i < 35; i++) {
    ctx.beginPath();
    let cx = Math.random() * size, cy = Math.random() * size;
    ctx.moveTo(cx, cy);
    for (let s = 0; s < 6; s++) {
      cx += (Math.random() - 0.5) * 70;
      cy += (Math.random() - 0.5) * 50;
      ctx.quadraticCurveTo(
        cx + (Math.random() - 0.5) * 30,
        cy + (Math.random() - 0.5) * 30,
        cx, cy
      );
    }
    ctx.stroke();
  }
  // Finer capillary network
  ctx.globalAlpha = 0.035;
  ctx.strokeStyle = 'rgba(170,90,90,1)';
  ctx.lineWidth = 0.8;
  for (let i = 0; i < 50; i++) {
    ctx.beginPath();
    let cx = Math.random() * size, cy = Math.random() * size;
    ctx.moveTo(cx, cy);
    for (let s = 0; s < 4; s++) {
      cx += (Math.random() - 0.5) * 40;
      cy += (Math.random() - 0.5) * 40;
      ctx.lineTo(cx, cy);
    }
    ctx.stroke();
  }
  ctx.globalAlpha = 1.0;

  // Layer 3: Organic speckle noise (per-pixel color jitter)
  const imgData = ctx.getImageData(0, 0, size, size);
  const d = imgData.data;
  for (let i = 0; i < d.length; i += 4) {
    const vary = (Math.random() - 0.5) * 18;
    d[i]     = Math.max(0, Math.min(255, d[i] + vary));          // R — strongest variation
    d[i + 1] = Math.max(0, Math.min(255, d[i + 1] + vary * 0.6)); // G — less variation
    d[i + 2] = Math.max(0, Math.min(255, d[i + 2] + vary * 0.3)); // B — least (warm bias)
  }

  // Layer 4: Scattered freckles/moles — more variety
  for (let n = 0; n < 120; n++) {
    const px = Math.floor(Math.random() * size);
    const py = Math.floor(Math.random() * size);
    const r = 1 + Math.floor(Math.random() * 4);
    const darken = 12 + Math.random() * 25;
    for (let dy = -r; dy <= r; dy++) {
      for (let dx = -r; dx <= r; dx++) {
        if (dx * dx + dy * dy > r * r) continue;
        const fx = ((px + dx) % size + size) % size;
        const fy = ((py + dy) % size + size) % size;
        const idx = (fy * size + fx) * 4;
        const falloff = 1 - Math.sqrt(dx * dx + dy * dy) / r;
        d[idx]     = Math.max(0, d[idx] - darken * falloff);
        d[idx + 1] = Math.max(0, d[idx + 1] - darken * falloff * 0.7);
        d[idx + 2] = Math.max(0, d[idx + 2] - darken * falloff * 0.5);
      }
    }
  }

  // Layer 5: Subtle warm patches (simulate blood proximity areas)
  for (let n = 0; n < 30; n++) {
    const px = Math.floor(Math.random() * size);
    const py = Math.floor(Math.random() * size);
    const r = 150 + Math.floor(Math.random() * 200);
    for (let dy = -r; dy <= r; dy++) {
      for (let dx = -r; dx <= r; dx++) {
        const dist2 = dx * dx + dy * dy;
        if (dist2 > r * r) continue;
        const fx = ((px + dx) % size + size) % size;
        const fy = ((py + dy) % size + size) % size;
        const idx = (fy * size + fx) * 4;
        const falloff = 1 - Math.sqrt(dist2) / r;
        const warm = falloff * (4 + Math.random() * 6);
        d[idx]     = Math.min(255, d[idx] + warm);       // add red
        d[idx + 1] = Math.max(0, d[idx + 1] - warm * 0.3); // subtract green slightly
      }
    }
  }
  
  // Layer 6: Large-scale anatomical variation (Macro-Veins & Skin Elasticity)
  for (let n = 0; n < 8; n++) {
    const px = Math.floor(Math.random() * size);
    const py = Math.floor(Math.random() * size);
    const r = 100 + Math.floor(Math.random() * 200);
    const grad = ctx.createRadialGradient(px, py, 0, px, py, r);
    grad.addColorStop(0, 'rgba(100,120,180,0.08)'); // deep blue veins
    grad.addColorStop(1, 'rgba(0,0,0,0)');
    ctx.fillStyle = grad;
    ctx.fillRect(0, 0, size, size);
  }

  ctx.putImageData(imgData, 0, 0);

  const tex = new THREE.CanvasTexture(canvas);
  tex.wrapS = tex.wrapT = THREE.RepeatWrapping;
  tex.repeat.set(3, 3);
  tex.colorSpace = THREE.SRGBColorSpace;
  return tex;
}

// ── Skin normal map — multi-scale anatomical detail ──────────────────────────
function _createSkinNormalMap(size = 1024) {
  const canvas = document.createElement('canvas');
  canvas.width = canvas.height = size;
  const ctx = canvas.getContext('2d');
  ctx.fillStyle = 'rgb(128,128,255)';
  ctx.fillRect(0, 0, size, size);
  const imgData = ctx.getImageData(0, 0, size, size);
  const d = imgData.data;

  // Pass 1: Fine pore noise (micro-scale skin texture)
  for (let i = 0; i < d.length; i += 4) {
    d[i]     = 128 + (Math.random() - 0.5) * 20;
    d[i + 1] = 128 + (Math.random() - 0.5) * 20;
  }

  // Pass 2: Medium-scale skin bumps (follicles, pores)
  for (let n = 0; n < 400; n++) {
    const cx = Math.floor(Math.random() * size);
    const cy = Math.floor(Math.random() * size);
    const r = 2 + Math.floor(Math.random() * 6);
    const strength = 12 + Math.random() * 20;
    const dirX = (Math.random() - 0.5) * 2;
    const dirY = (Math.random() - 0.5) * 2;
    for (let dy = -r; dy <= r; dy++) {
      for (let dx = -r; dx <= r; dx++) {
        if (dx * dx + dy * dy > r * r) continue;
        const px = ((cx + dx) % size + size) % size;
        const py = ((cy + dy) % size + size) % size;
        const idx = (py * size + px) * 4;
        const falloff = 1 - Math.sqrt(dx * dx + dy * dy) / r;
        d[idx]     = Math.max(0, Math.min(255, d[idx] + dirX * strength * falloff));
        d[idx + 1] = Math.max(0, Math.min(255, d[idx + 1] + dirY * strength * falloff));
      }
    }
  }

  // Pass 3: Large muscle/tendon ridges (anatomy detail)
  for (let n = 0; n < 60; n++) {
    const cx = Math.floor(Math.random() * size);
    const cy = Math.floor(Math.random() * size);
    const r = 15 + Math.floor(Math.random() * 30);
    const strength = 8 + Math.random() * 12;
    const angle = Math.random() * Math.PI * 2;
    const dirX = Math.cos(angle);
    const dirY = Math.sin(angle);
    for (let dy = -r; dy <= r; dy++) {
      for (let dx = -r; dx <= r; dx++) {
        if (dx * dx + dy * dy > r * r) continue;
        const px = ((cx + dx) % size + size) % size;
        const py = ((cy + dy) % size + size) % size;
        const idx = (py * size + px) * 4;
        const dist = Math.sqrt(dx * dx + dy * dy);
        const falloff = Math.cos(dist / r * Math.PI * 0.5);
        d[idx]     = Math.max(0, Math.min(255, d[idx] + dirX * strength * falloff));
        d[idx + 1] = Math.max(0, Math.min(255, d[idx + 1] + dirY * strength * falloff));
      }
    }
  }

  // Pass 4: Fine wrinkle/crease lines (skin folds)
  for (let n = 0; n < 100; n++) {
    const horizontal = Math.random() > 0.5;
    const pos = Math.floor(Math.random() * size);
    const len = 15 + Math.floor(Math.random() * 50);
    const start = Math.floor(Math.random() * (size - len));
    const str = 15 + Math.random() * 12;
    const width = 1 + Math.floor(Math.random() * 2);
    for (let t = 0; t < len; t++) {
      for (let w = -width; w <= width; w++) {
        const x = horizontal ? start + t : ((pos + w) % size + size) % size;
        const y = horizontal ? ((pos + w) % size + size) % size : start + t;
        if (x < 0 || x >= size || y < 0 || y >= size) continue;
        const idx = (y * size + x) * 4;
        const ch = horizontal ? 1 : 0;
        const wFalloff = 1 - Math.abs(w) / (width + 1);
        d[idx + ch] = Math.max(0, Math.min(255, d[idx + ch] + str * wFalloff));
      }
    }
  }

  // Pass 5: Cross-hatched micro-texture (diamond skin pattern)
  for (let n = 0; n < 40; n++) {
    const cx = Math.floor(Math.random() * size);
    const cy = Math.floor(Math.random() * size);
    const len = 8 + Math.floor(Math.random() * 15);
    const str = 8 + Math.random() * 8;
    // Diagonal line pair
    for (const angle of [0.78, -0.78]) { // ~45 degrees
      const dx = Math.cos(angle);
      const dy = Math.sin(angle);
      for (let t = -len; t <= len; t++) {
        const px = ((cx + Math.round(dx * t)) % size + size) % size;
        const py = ((cy + Math.round(dy * t)) % size + size) % size;
        const idx = (py * size + px) * 4;
        d[idx]     = Math.max(0, Math.min(255, d[idx] + str * 0.5));
        d[idx + 1] = Math.max(0, Math.min(255, d[idx + 1] + str * 0.5));
      }
    }
  }

  
  // Layer 6: Large-scale anatomical variation (Macro-Veins & Skin Elasticity)
  for (let n = 0; n < 8; n++) {
    const px = Math.floor(Math.random() * size);
    const py = Math.floor(Math.random() * size);
    const r = 100 + Math.floor(Math.random() * 200);
    const grad = ctx.createRadialGradient(px, py, 0, px, py, r);
    grad.addColorStop(0, 'rgba(100,120,180,0.08)'); // deep blue veins
    grad.addColorStop(1, 'rgba(0,0,0,0)');
    ctx.fillStyle = grad;
    ctx.fillRect(0, 0, size, size);
  }

  ctx.putImageData(imgData, 0, 0);
  const tex = new THREE.CanvasTexture(canvas);
  tex.wrapS = tex.wrapT = THREE.RepeatWrapping;
  tex.repeat.set(5, 5);
  return tex;
}

// ── Skin roughness map — slight variation (oilier on forehead, drier on limbs)
function _createSkinRoughnessMap(size = 256) {
  const canvas = document.createElement('canvas');
  canvas.width = canvas.height = size;
  const ctx = canvas.getContext('2d');
  // Base roughness ~0.6 (153/255)
  ctx.fillStyle = 'rgb(153,153,153)';
  ctx.fillRect(0, 0, size, size);
  const imgData = ctx.getImageData(0, 0, size, size);
  const d = imgData.data;
  for (let i = 0; i < d.length; i += 4) {
    const v = 140 + Math.random() * 30;  // 0.55–0.67 roughness range
    d[i] = d[i + 1] = d[i + 2] = v;
  }
  
  // Layer 6: Large-scale anatomical variation (Macro-Veins & Skin Elasticity)
  for (let n = 0; n < 8; n++) {
    const px = Math.floor(Math.random() * size);
    const py = Math.floor(Math.random() * size);
    const r = 100 + Math.floor(Math.random() * 200);
    const grad = ctx.createRadialGradient(px, py, 0, px, py, r);
    grad.addColorStop(0, 'rgba(100,120,180,0.08)'); // deep blue veins
    grad.addColorStop(1, 'rgba(0,0,0,0)');
    ctx.fillStyle = grad;
    ctx.fillRect(0, 0, size, size);
  }

  ctx.putImageData(imgData, 0, 0);
  const tex = new THREE.CanvasTexture(canvas);
  tex.wrapS = tex.wrapT = THREE.RepeatWrapping;
  tex.repeat.set(4, 4);
  return tex;
}

let _realSkinLoaded = false;

async function _loadRealSkinTexture() {
  const params = new URLSearchParams(location.search);
  const cid = params.get('customer') || '1';
  const loader = new THREE.TextureLoader();
  const baseUrl = `/web_app/api/customer/${cid}/skin_texture`;

  try {
    const albedo = await new Promise((resolve, reject) => {
      loader.load(baseUrl + '/albedo', resolve, undefined, reject);
    });
    albedo.wrapS = albedo.wrapT = THREE.RepeatWrapping;
    albedo.colorSpace = THREE.SRGBColorSpace;
    // ~3cm micro patch: start at realistic scale (high tiling).
    // User adjusts slider down to enlarge and see detail.
    albedo.repeat.set(22, 57);
    // Slight random offset to break grid alignment across UV seams
    albedo.offset.set(0.13, 0.07);
    // Anisotropic filtering for sharp detail at oblique angles
    albedo.anisotropy = renderer.capabilities.getMaxAnisotropy();

    let normalTex = null;
    try {
      normalTex = await new Promise((resolve, reject) => {
        loader.load(baseUrl + '/normal', resolve, undefined, reject);
      });
      normalTex.wrapS = normalTex.wrapT = THREE.RepeatWrapping;
      normalTex.repeat.set(22, 57);
      normalTex.offset.set(0.13, 0.07);
      normalTex.anisotropy = renderer.capabilities.getMaxAnisotropy();
    } catch (e) { /* use procedural fallback */ }

    let roughTex = null;
    try {
      roughTex = await new Promise((resolve, reject) => {
        loader.load(baseUrl + '/roughness', resolve, undefined, reject);
      });
      roughTex.wrapS = roughTex.wrapT = THREE.RepeatWrapping;
      roughTex.repeat.set(22, 57);
      roughTex.offset.set(0.13, 0.07);
      roughTex.anisotropy = renderer.capabilities.getMaxAnisotropy();
    } catch (e) { /* use procedural fallback */ }

    // Build a clean material from the real skin photo with SSS
    const realSkinMat = new THREE.MeshPhysicalMaterial({
      map:              albedo,
      normalMap:        normalTex || null,
      normalScale:      new THREE.Vector2(0.8, 0.8),
      roughnessMap:     roughTex || null,
      roughness:        0.42,
      metalness:        0.0,
      side:             THREE.DoubleSide,
      color:            0xffffff,
      // Sheen + clearcoat
      sheen:            0.3,
      sheenRoughness:   0.45,
      sheenColor:       new THREE.Color(0xddaa88),
      clearcoat:        0.1,
      clearcoatRoughness: 0.2,
      specularIntensity: 0.35,
      specularColor:    new THREE.Color(1.0, 1.0, 1.0),
      envMapIntensity:  0.5,
    });
    // Replace SKIN_MATERIAL properties so setSkinTiling still works
    Object.assign(SKIN_MATERIAL, {
      map: albedo, normalMap: normalTex, roughnessMap: roughTex,
      color: new THREE.Color(0xffffff),
      roughness: 0.42,
      metalness: 0.0,
      specularIntensity: 0.35,
      specularColor: new THREE.Color(1.0, 1.0, 1.0),
      // Sheen + clearcoat
      sheen: 0.3, sheenRoughness: 0.45,
      sheenColor: new THREE.Color(0xddaa88),
      clearcoat: 0.1, clearcoatRoughness: 0.2,
      envMapIntensity: 0.5,
    });
    if (normalTex) SKIN_MATERIAL.normalScale.set(0.85, 0.85);
    _applyPoreNormalPatch(SKIN_MATERIAL);
    SKIN_MATERIAL.needsUpdate = true;

    // Gemini Texture Sharpness Overdrive
    const _maxAniso = renderer.capabilities.getMaxAnisotropy();
    [SKIN_MATERIAL.map, SKIN_MATERIAL.normalMap, SKIN_MATERIAL.roughnessMap].forEach(t => {
        if (t) {
            t.anisotropy = _maxAniso;
            t.generateMipmaps = true;
            t.magFilter = THREE.LinearFilter;
            t.minFilter = THREE.LinearMipmapLinearFilter;
        }
    });


    _realSkinLoaded = true;
    console.log('Real skin texture loaded for customer', cid);

    // Apply the clean material directly
    if (bodyMesh) {
      bodyMesh.traverse(c => { if (c.isMesh) c.material = SKIN_MATERIAL; });
    }

    const btn = document.getElementById('btn-skin');
    if (btn) btn.classList.add('available');

  } catch (e) {
    console.log('No real skin texture found, using procedural');
  }
}

// ── PBR texture loading from texture_factory output ──────────────────────────
async function _loadPBRTextures() {
  const params = new URLSearchParams(location.search);
  const cid = params.get('customer') || '1';
  const loader = new THREE.TextureLoader();
  const baseUrl = `/web_app/api/customer/${cid}/pbr_textures`;

  try {
    const resp = await fetch(baseUrl, {
      headers: _viewerToken ? { 'Authorization': `Bearer ${_viewerToken}` } : {},
    });
    const data = await resp.json();
    if (data.status !== 'success' || !data.textures) return;

    const texPaths = data.textures;  // {albedo, normal, roughness, ao}
    const textures = {};

    for (const [name, url] of Object.entries(texPaths)) {
      try {
        textures[name] = await new Promise((resolve, reject) => {
          loader.load(url, resolve, undefined, reject);
        });
        textures[name].colorSpace = name === 'albedo'
          ? THREE.SRGBColorSpace : THREE.LinearSRGBColorSpace;
        textures[name].wrapS = textures[name].wrapT = THREE.ClampToEdgeWrapping;
        textures[name].anisotropy = renderer.capabilities.getMaxAnisotropy();
      } catch (e) { /* skip missing map */ }
    }

    if (!textures.albedo) return;

    // Build PBR material with SSS and regional roughness
    const pbrMat = new THREE.MeshPhysicalMaterial({
      map:              textures.albedo,
      normalMap:        textures.normal || null,
      normalScale:      new THREE.Vector2(0.85, 0.85),
      roughnessMap:     textures.roughness || null,
      roughness:        textures.roughness ? 1.0 : 0.42,
      aoMap:            textures.ao || null,
      aoMapIntensity:   0.6,
      metalness:        0.0,
      side:             THREE.DoubleSide,
      color:            0xffffff,
      // Sheen + clearcoat
      sheen:            0.3,
      sheenRoughness:   0.45,
      sheenColor:       new THREE.Color(0xcc8866),
      clearcoat:        0.1,
      clearcoatRoughness: 0.2,
      specularIntensity: 0.35,
      specularColor:    new THREE.Color(1.0, 1.0, 1.0),
      envMapIntensity:  0.5,
    });

    if (bodyMesh) {
      bodyMesh.traverse(c => {
        if (c.isMesh) {
          c.material = pbrMat;
          _originalMaterials.set(c, pbrMat);
        }
      });
    }

    console.log('PBR textures loaded:', Object.keys(textures).join(', '));
  } catch (e) {
    console.log('PBR textures not available, using defaults');
  }
}
window.loadPBRTextures = _loadPBRTextures;

// ── HDRI environment loading ─────────────────────────────────────────────────
async function _loadHDRI(url) {
  if (!url) return;
  try {
    const rgbeLoader = new RGBELoader();
    const hdrTexture = await new Promise((resolve, reject) => {
      rgbeLoader.load(url, resolve, undefined, reject);
    });
    hdrTexture.mapping = THREE.EquirectangularReflectionMapping;
    scene.environment = hdrTexture;
    // Optional: set as background too
    // scene.background = hdrTexture;
    console.log('HDRI loaded:', url);
  } catch (e) {
    console.warn('HDRI load failed:', e);
  }
}
window.loadHDRI = _loadHDRI;

// ── Room wall texturing from API ─────────────────────────────────────────────
async function _loadRoomWallTextures() {
  if (!_viewerToken) return;
  const params = new URLSearchParams(location.search);
  const cid = params.get('customer') || '1';
  const roomType = params.get('room') || 'home';

  try {
    const resp = await fetch(`/web_app/api/room_assets/${roomType}`, {
      headers: { 'Authorization': `Bearer ${_viewerToken}` },
    });
    const data = await resp.json();
    if (data.status !== 'success') return;

    const loader = new THREE.TextureLoader();

    // Apply floor texture
    if (data.floor_diff && _roomWalls.floor) {
      const floorTex = await new Promise((r, e) => loader.load(data.floor_diff, r, undefined, e));
      floorTex.wrapS = floorTex.wrapT = THREE.RepeatWrapping;
      floorTex.repeat.set(4, 6);
      _roomWalls.floor.material.map = floorTex;
      _roomWalls.floor.material.needsUpdate = true;
    }

    // Apply wall texture
    if (data.wall_diff) {
      const wallTex = await new Promise((r, e) => loader.load(data.wall_diff, r, undefined, e));
      wallTex.wrapS = wallTex.wrapT = THREE.RepeatWrapping;
      wallTex.repeat.set(3, 2);
      for (const name of ['back', 'front', 'left', 'right']) {
        if (_roomWalls[name]) {
          _roomWalls[name].material.map = wallTex.clone();
          _roomWalls[name].material.needsUpdate = true;
        }
      }
    }

    // Apply ceiling texture
    if (data.ceiling_diff && _roomWalls.ceiling) {
      const ceilTex = await new Promise((r, e) => loader.load(data.ceiling_diff, r, undefined, e));
      ceilTex.wrapS = ceilTex.wrapT = THREE.RepeatWrapping;
      ceilTex.repeat.set(3, 4);
      _roomWalls.ceiling.material.map = ceilTex;
      _roomWalls.ceiling.material.needsUpdate = true;
    }

    // Load HDRI for environment reflections
    if (data.hdri_url) {
      await _loadHDRI(data.hdri_url);
    }

    console.log('Room textures loaded for', roomType);
  } catch (e) {
    console.warn('Room wall textures not loaded:', e);
  }
}
window.loadRoomWallTextures = _loadRoomWallTextures;

function setSkinTiling(tilesX, tilesY) {
  if (!SKIN_MATERIAL.map) return;
  SKIN_MATERIAL.map.repeat.set(tilesX, tilesY);
  if (SKIN_MATERIAL.normalMap) SKIN_MATERIAL.normalMap.repeat.set(tilesX, tilesY);
  if (SKIN_MATERIAL.roughnessMap) SKIN_MATERIAL.roughnessMap.repeat.set(tilesX, tilesY);
  SKIN_MATERIAL.needsUpdate = true;

    // Gemini Texture Sharpness Overdrive
    const _maxAniso = renderer.capabilities.getMaxAnisotropy();
    [SKIN_MATERIAL.map, SKIN_MATERIAL.normalMap, SKIN_MATERIAL.roughnessMap].forEach(t => {
        if (t) {
            t.anisotropy = _maxAniso;
            t.generateMipmaps = true;
            t.magFilter = THREE.LinearFilter;
            t.minFilter = THREE.LinearMipmapLinearFilter;
        }
    });

}
window.setSkinTiling = setSkinTiling;

// Studio: uniform texture scale — independent from Fine-tune X/Y
let _studioScale = 1.0;
function setTextureScale(scale) {
  _studioScale = scale;
  _applySkinTiling();
}
// Fine-tune X/Y set their own tiling — independent from Scale
let _fineTuneX = 22, _fineTuneY = 57;
function setFineTuneX(val) {
  _fineTuneX = val;
  _applySkinTiling();
}
function setFineTuneY(val) {
  _fineTuneY = val;
  _applySkinTiling();
}
// Combined: final tiling = fineTune × scale
function _applySkinTiling() {
  const tx = _fineTuneX * _studioScale;
  const ty = _fineTuneY * _studioScale;
  setSkinTiling(tx, ty);
}
window.setTextureScale = setTextureScale;
window.setFineTuneX = setFineTuneX;
window.setFineTuneY = setFineTuneY;

function setTextureOffset(ox, oy) {
  if (!SKIN_MATERIAL.map) return;
  SKIN_MATERIAL.map.offset.set(ox, oy);
  if (SKIN_MATERIAL.normalMap) SKIN_MATERIAL.normalMap.offset.set(ox, oy);
  if (SKIN_MATERIAL.roughnessMap) SKIN_MATERIAL.roughnessMap.offset.set(ox, oy);
  SKIN_MATERIAL.needsUpdate = true;

    // Gemini Texture Sharpness Overdrive
    const _maxAniso = renderer.capabilities.getMaxAnisotropy();
    [SKIN_MATERIAL.map, SKIN_MATERIAL.normalMap, SKIN_MATERIAL.roughnessMap].forEach(t => {
        if (t) {
            t.anisotropy = _maxAniso;
            t.generateMipmaps = true;
            t.magFilter = THREE.LinearFilter;
            t.minFilter = THREE.LinearMipmapLinearFilter;
        }
    });

}
window.setTextureOffset = setTextureOffset;

function resetStudioDefaults() {
  _studioScale = 1.0; _fineTuneX = 22; _fineTuneY = 57;
  setSkinTiling(22, 57);
  setTextureOffset(0, 0);
  // Reset all sliders
  const els = {
    'studio-scale': '1.0', 'studio-tile-x': '22', 'studio-tile-y': '57',
    'studio-off-x': '0', 'studio-off-y': '0',
  };
  for (const [id, val] of Object.entries(els)) {
    const el = document.getElementById(id);
    if (el) el.value = val;
  }
  const scaleVal = document.getElementById('studio-scale-val');
  if (scaleVal) scaleVal.textContent = '1.0×';
  const xyVal = document.getElementById('studio-xy-val');
  if (xyVal) xyVal.textContent = '22×57';
  const offVal = document.getElementById('studio-off-val');
  if (offVal) offVal.textContent = '(0,0)';
}
window.resetStudioDefaults = resetStudioDefaults;

// Load real skin photo texture (tiled)
const _skinPhotoTex = new THREE.TextureLoader().load('./skin_photo.jpg', (tex) => {
  tex.wrapS = tex.wrapT = THREE.RepeatWrapping;
  tex.repeat.set(22, 57);
  tex.colorSpace = THREE.SRGBColorSpace;
  tex.needsUpdate = true;
  if (SKIN_MATERIAL) { SKIN_MATERIAL.map = tex; SKIN_MATERIAL.needsUpdate = true;

    // Gemini Texture Sharpness Overdrive
    const _maxAniso = renderer.capabilities.getMaxAnisotropy();
    [SKIN_MATERIAL.map, SKIN_MATERIAL.normalMap, SKIN_MATERIAL.roughnessMap].forEach(t => {
        if (t) {
            t.anisotropy = _maxAniso;
            t.generateMipmaps = true;
            t.magFilter = THREE.LinearFilter;
            t.minFilter = THREE.LinearMipmapLinearFilter;
        }
    });
 }
});
_skinPhotoTex.wrapS = _skinPhotoTex.wrapT = THREE.RepeatWrapping;
_skinPhotoTex.repeat.set(30, 55);
_skinPhotoTex.colorSpace = THREE.SRGBColorSpace;

const SKIN_MATERIAL = new THREE.MeshPhysicalMaterial({
    map:              _skinPhotoTex,
    roughnessMap:     _createSkinRoughnessMap(),
    roughness:        0.55,                // Real skin is rougher overall
    metalness:        0.0,
    side:             THREE.DoubleSide,
    color:            0xffffff,
    // SSS (Subsurface Scattering) — the holy grail of skin
    transmission:       0.05,              // Light enters the skin
    thickness:          4.0,               // Volume thickness for scattering
    ior:                1.38,              // Skin refractive index
    attenuationColor:   new THREE.Color(0xee6644), // Warm blood tone
    attenuationDistance: 0.8,              // Distance light travels inside
    // Sheen — peach fuzz effect
    sheen:              0.25,
    sheenRoughness:     0.4,
    sheenColor:         new THREE.Color(0xddbb99),
    // Surface oil (Sebum)
    clearcoat:          0.45,
    clearcoatRoughness: 0.12,
    // Specularity
    specularIntensity:  0.45,
    specularColor:      new THREE.Color(1.0, 1.0, 1.0),
    // Normal map
    normalMap:          _createSkinNormalMap(),
    normalScale:        new THREE.Vector2(0.9, 0.9),
    // Environment reflection
    envMapIntensity:    1.2,
    onBeforeCompile: (shader) => {
      const seamlessBlendChunk = `
    #include <map_pars_fragment>
    vec4 textureSeamlessBlend(sampler2D tex, vec2 uv) {
    // Current tile local coordinates
    vec2 tileUv = fract(uv);
    vec4 photoColor = texture2D(tex, uv);

    // Layer below the human skin: Sample the exact center of the tile
    // to get a uniform, artifact-free base skin tone.
    vec2 centerUv = floor(uv) + vec2(0.5);
    vec4 baseColor = texture2D(tex, centerUv);

    // Make the edges of the photo transparent
    float dist = distance(tileUv, vec2(0.5));
    float mask = 1.0 - smoothstep(0.25, 0.45, dist); // Soft fade

    // Connect it all smooth
    return mix(baseColor, photoColor, mask);
    }
    `;
      shader.fragmentShader = shader.fragmentShader.replace('#include <map_pars_fragment>', seamlessBlendChunk);
      shader.fragmentShader = shader.fragmentShader.replace('vec4 sampledDiffuseColor = texture2D( map, vMapUv );', 'vec4 sampledDiffuseColor = textureSeamlessBlend( map, vMapUv );');
    },    transparent: false,
  });

// ── Micro-normal (skin pore) detail ──────────────────────────────────────────
// Blends high-frequency pore detail into the material's normalMap via canvas
// compositing. This avoids onBeforeCompile which breaks MeshPhysicalMaterial's
// transmission/IOR shader code.
let _poreNormalImg = null;
let _poreNormalStrength = 0.28;

(function _initPoreNormal() {
  const img = new Image();
  img.onload = () => { _poreNormalImg = img; console.log('Pore normal texture ready'); };
  img.src = './textures/skin_pore_normal.png';
})();

function setPoreNormalStrength(val) {
  _poreNormalStrength = Math.max(0, Math.min(1, val));
  // Re-blend pore detail at new strength into all mesh materials
  if (bodyMesh) {
    bodyMesh.traverse(c => {
      if (c.isMesh && c.material && c.material.normalMap) {
        _applyPoreNormalPatch(c.material);
      }
    });
  }
}
window.setPoreNormalStrength = setPoreNormalStrength;

function _applyPoreNormalPatch(material) {
  if (!material.normalMap || !_poreNormalImg || _poreNormalStrength === 0) return;

  const baseTex = material.normalMap;
  if (baseTex.userData.isPorePatched && baseTex.userData.strength === _poreNormalStrength) return;

  // Use an offscreen canvas to blend high-frequency pore detail into the normal map
  const size = baseTex.image.width || 2048;
  const canvas = document.createElement('canvas');
  canvas.width = canvas.height = size;
  const ctx = canvas.getContext('2d');

  // 1. Draw base normal map
  ctx.drawImage(baseTex.image, 0, 0, size, size);

  // 2. Blend tiled pore normal
  // Normal map blending in 2D is tricky. A good approximation for micro-detail:
  // "Overlay" or "Soft Light" blending at low opacity, or custom math.
  // We'll use 'overlay' which preserves the 128,128,255 neutral vector.
  ctx.globalAlpha = _poreNormalStrength * 1.5;
  ctx.globalCompositeOperation = 'soft-light';

  const poreSize = 256; // typical micro-normal size
  const tilesX = Math.ceil(size / poreSize) * 2; // high density
  const tilesY = Math.ceil(size / poreSize) * 2;

  for (let y = 0; y < tilesY; y++) {
    const dy = y * poreSize;
    for (let x = 0; x < tilesX; x++) {
      const dx = x * poreSize;
      ctx.drawImage(_poreNormalImg, dx, dy, poreSize, poreSize);
    }
  }

  // 3. Update texture
  const newTex = new THREE.CanvasTexture(canvas);
  newTex.colorSpace = THREE.LinearSRGBColorSpace;
  newTex.wrapS = newTex.wrapT = THREE.RepeatWrapping;
  newTex.anisotropy = renderer.capabilities.getMaxAnisotropy();
  newTex.userData.isPorePatched = true;
  newTex.userData.strength = _poreNormalStrength;

  material.normalMap = newTex;
  material.needsUpdate = true;
}

// ── Init ──────────────────────────────────────────────────────────────────────
function init() {
  const container = document.getElementById('canvas-container');

  // Scene
  scene = new THREE.Scene();
  scene.background = new THREE.Color(0x0a0a12);

  // Camera
  camera = new THREE.PerspectiveCamera(50, window.innerWidth / window.innerHeight, 0.1, 5000);
  camera.position.set(0, 120, 17);

  // Renderer
  renderer = new THREE.WebGLRenderer({ antialias: true, preserveDrawingBuffer: true });
  renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
  renderer.setSize(window.innerWidth, window.innerHeight);
  renderer.toneMapping        = THREE.ACESFilmicToneMapping;
  renderer.toneMappingExposure = 1.0;
  renderer.shadowMap.enabled  = true;
  renderer.shadowMap.type     = THREE.PCFSoftShadowMap;
  renderer.outputColorSpace   = THREE.SRGBColorSpace;
  renderer.physicallyCorrectLights = true;
  container.appendChild(renderer.domElement);

  // Controls
  controls = new OrbitControls(camera, renderer.domElement);
  controls.enableDamping    = true;
  controls.dampingFactor    = 0.08;
  controls.minDistance      = 5;
  controls.maxDistance      = 3000;
  controls.zoomSpeed        = 0.5; // 50% smaller zoom steps

  controls.target.set(0, 80, 0);  // roughly mid-torso height
  controls.update();

  // Lights — studio default for PBR material visibility
  _setupStudioLights();
  _currentLightPreset = 'studio';

  // Environment map (PMREMGenerator gradient — no external HDR file needed)
  _setupEnvironment();

  // V7: Room, props, mirror, contact shadow
  _buildRoom();
  _buildProps();
  _createContactShadow();
  _setupMirror();
  _setupWalkControls();

  // SSAO post-processing (ambient occlusion for crevices/contact areas)
  _initSSAO();

  // Resize
  window.addEventListener('resize', _onResize);

  // Restore sidebar when exiting fullscreen via Escape
  document.addEventListener('fullscreenchange', () => {
    if (!document.fullscreenElement) {
      const overlay = document.getElementById('ui-overlay');
      if (overlay) overlay.style.display = '';
    }
  });

  // Expose for MeasurementOverlay, agent_browser, and debugging
  window.scene = scene;
  window.camera = camera;
  window.controls = controls;
  window.bodyViewer = {
    scene, camera, renderer, controls,
    get mesh() { return bodyMesh; },
    getMeshIntersection: _getMeshIntersection,
  };

  // Click-to-select body region
  renderer.domElement.addEventListener('click', _onMeshClick);
  renderer.domElement.addEventListener('mousemove', _onMeshHover);

  // Prevent browser default touch behaviors (scroll, pinch-zoom) on the 3D canvas
  renderer.domElement.addEventListener('touchstart', (e) => e.preventDefault(), { passive: false });
  renderer.domElement.addEventListener('touchmove',  (e) => e.preventDefault(), { passive: false });

  // Double-tap to reset camera (mobile convenience)
  let _lastTap = 0;
  renderer.domElement.addEventListener('touchend', (e) => {
    const now = Date.now();
    if (now - _lastTap < 300 && e.changedTouches.length === 1) {
      window.resetCamera();
    }
    _lastTap = now;
  });

  // Adjustment slider live preview
  ['adj-width', 'adj-depth', 'adj-length'].forEach(id => {
    const el = document.getElementById(id);
    if (el) el.addEventListener('input', () => {
      const val = document.getElementById(id + '-val');
      if (val) val.textContent = el.value;
    });
  });

  // Phenotype slider listeners (Server-side deform with 500ms debounce)
  let _phenotypeTimeout = null;

  window.applyPhenotype = async function() {
    try {
      const cid = _customerId();
      const mVal = document.getElementById('pheno-muscle')?.value || 50;
      const wVal = document.getElementById('pheno-weight')?.value || 50;
      const gVal = document.getElementById('pheno-gender')?.value || 100;

      const updates = {
        muscle_factor: parseInt(mVal) / 100.0,
        weight_factor: parseInt(wVal) / 100.0,
        gender_factor: parseInt(gVal) / 100.0,
        gender: parseInt(gVal) < 50 ? 'female' : 'male'
      };

      _setStatus('Applying phenotype...');

      // 1. Update profile
      const postResp = await fetch(`/web_app/api/customer/${cid}/body_profile`, {
        method: 'POST',
        headers: _authHeaders(),
        body: JSON.stringify(updates),
      });
      const result = await postResp.json();
      if (result.status !== 'success') {
        _setStatus('Phenotype update failed: ' + (result.message || '')); return;
      }

      // 2. Regenerate mesh
      const meshResp = await fetch(`/web_app/api/customer/${cid}/body_model`, {
        method: 'POST',
        headers: _authHeaders(),
        body: JSON.stringify({}),
      });
      const meshResult = await meshResp.json();
      if (meshResult.glb_url) {
        _loadGLB(meshResult.glb_url, null);
        _setStatus('');
      } else {
        _setStatus('Mesh regeneration failed');
      }
    } catch (e) {
      _setStatus('Update failed: ' + e.message);
    }
  };

  ['pheno-muscle', 'pheno-weight', 'pheno-gender'].forEach(id => {
    const el = document.getElementById(id);
    if (el) {
      el.addEventListener('input', () => {
        if (id === 'pheno-gender') {
           const v = parseInt(el.value);
           const label = document.getElementById('pheno-gender-label');
           if (label) label.textContent = v < 50 ? 'Female' : 'Male';
        } else {
           const val = document.getElementById(id + '-val');
           if (val) val.textContent = el.value;
        }

        clearTimeout(_phenotypeTimeout);
        _phenotypeTimeout = setTimeout(window.applyPhenotype, 500);
      });
    }
  });

  // Collapsible panels — click h3 to toggle
  document.querySelectorAll('.collapsible > h3').forEach(h3 => {
    h3.addEventListener('click', () => h3.parentElement.classList.toggle('collapsed'));
  });

  // ── Tab switching ──────────────────────────────────────────────────────────
  window.switchTab = function(tabName) {
    document.querySelectorAll('.tab-content').forEach(el => {
      el.classList.toggle('active', el.dataset.tab === tabName);
    });
    document.querySelectorAll('.tab-btn').forEach(btn => {
      btn.classList.toggle('active', btn.dataset.tab === tabName);
    });
    // Auto-switch to skin view when Studio tab is opened
    if (tabName === 'studio') {
      const skinBtn = document.getElementById('btn-skin');
      if (skinBtn && !skinBtn.classList.contains('active')) {
        window.setViewMode('skin');
      }
    }
    _saveViewerSettings();
  };

  const _featureTabMap = {
    'growth': 'analyze', 'slices': 'analyze', 'profile': 'analyze', 'axis': 'analyze',
    'walk': 'scene', 'room': 'scene', 'mirror': 'scene', 'props': 'scene', 'stats': 'scene',
  };
  function _autoTab(feature) {
    const tab = _featureTabMap[feature];
    if (tab) switchTab(tab);
  }

  // Authenticate for save/regenerate calls then load mesh list + room textures
  _autoLogin().then(() => { _loadMeshList(); _loadRoomTextures(); _loadBodyStats(); _loadCustomerList(); });

  // Load model from URL params
  _loadFromUrl();

  // Cross-section slider
  const secSlider = document.getElementById('section-height');
  if (secSlider) {
    secSlider.addEventListener('input', (e) => {
      document.getElementById('section-height-val').textContent = e.target.value;
      _updateCrossSection(parseInt(e.target.value) / 100);
    });
  }

  // Keyboard shortcuts
  document.addEventListener('keydown', (e) => {
    if (e.target.tagName === 'INPUT' || e.target.tagName === 'SELECT') return;
    switch (e.key) {
      
        case 'z': case 'Z': _moveState.zoomIn = true; break;
        case 'v': case 'V': _moveState.zoomOut = true; break;
        case '1': window.setViewMode('solid');     break;
      case '2': window.setViewMode('wireframe'); break;
      case '3': window.setViewMode('heatmap');   break;
      case '4': window.setViewMode('textured');  break;
      case '5': window.toggleWalkMode();         break;
      case '6': window.toggleRoom();             break;
      case '7': window.toggleMirror();           break;
      case '8': window.toggleProps();            break;
      case '9': window.toggleBodyStats();        break;
      case '0': window.toggleAutoRotate();       break;
      case 'f': case 'F': window.toggleFullscreen(); break;
      case 'l': case 'L': window.toggleLabels();  break;
      case 'c': case 'C': window.toggleRings();     break;
      case 'g': case 'G': window.toggleGrowthMap();    break;
      case 'x': case 'X': window.toggleSliceView();    break;
      case 'p': case 'P': window.toggleProfile();      break;
      case 'q': case 'Q': window.togglePostureAxis();  break;
      case 'm': case 'M': window.toggleMeasure();   break;
      case 'r': case 'R': window.resetCamera();   break;
      
      
      case 'e': case 'E': exportDataCSV();         break;
      case 's': case 'S':
        if (_walkMode) _moveState.backward = true;
        else window.setViewMode('skin');
        break;
      case 'w': case 'W': if (_walkMode) _moveState.forward  = true; break;
      case 'a': case 'A': if (_walkMode) _moveState.left     = true; break;
      case 'd': case 'D': if (_walkMode) _moveState.right    = true; break;
      case '[': {
        const tabs = ['view', 'scene', 'analyze', 'camera'];
        const active = document.querySelector('.tab-btn.active');
        const cur = active ? tabs.indexOf(active.dataset.tab) : 0;
        switchTab(tabs[(cur - 1 + tabs.length) % tabs.length]);
        break;
      }
      case ']': {
        const tabs = ['view', 'scene', 'analyze', 'camera'];
        const active = document.querySelector('.tab-btn.active');
        const cur = active ? tabs.indexOf(active.dataset.tab) : 0;
        switchTab(tabs[(cur + 1) % tabs.length]);
        break;
      }
      case 'Escape':
        if (_walkMode) { window.toggleWalkMode(); break; }
        _measureMode = false;
        document.getElementById('btn-measure')?.classList.remove('active');
        break;
    }
  });
  document.addEventListener('keyup', (e) => {
    switch (e.key) {
      
        case 'z': case 'Z': _moveState.zoomIn = false; break;
        case 'v': case 'V': _moveState.zoomOut = false; break;
        case 'w': case 'W': _moveState.forward  = false; break;
      case 'a': case 'A': _moveState.left     = false; break;
      case 's': case 'S': _moveState.backward = false; break;
      case 'd': case 'D': _moveState.right    = false; break;
    }
  });

  // Restore saved viewer settings
  _restoreViewerSettings();

  // FORCE PRO DEFAULTS (Overwrites low-quality saved settings)
  setLightPreset('studio');
  _ssaoEnabled = true;
  const chkSSAO = document.getElementById('chk-ssao');
  if (chkSSAO) chkSSAO.checked = true;

  // Start render loop
  _animate();
}

// ── Lighting ──────────────────────────────────────────────────────────────────
function _setupStudioLights() {
  // Ambient — warm, low intensity to prevent pitch black shadows
  const a = new THREE.AmbientLight(0xfff5e4, 0.15); // increased from 0.25
  scene.add(a); _studioLightObjs.push(a);

  // Hemisphere — sky/ground bounce for natural feel
  const h = new THREE.HemisphereLight(0xffeedd, 0x443322, 0.3); // increased from 0.35
  scene.add(h); _studioLightObjs.push(h);

  // Key light — main illumination, warm, high position for natural shadows
  const key = new THREE.DirectionalLight(0xffefd5, 1.8); // increased from 1.4 for punchy highlights
  key.position.set(150, 450, 250);
  key.castShadow = true;
  key.shadow.mapSize.set(2048, 2048);
  key.shadow.camera.left   = -400;
  key.shadow.camera.right  =  400;
  key.shadow.camera.top    =  400;
  key.shadow.camera.bottom = -400;
  key.shadow.bias = -0.0001;
  key.shadow.normalBias = 0.02;
  scene.add(key); _studioLightObjs.push(key);

  // Fill light — cooler, from opposite side to define muscle contours
  const fill = new THREE.DirectionalLight(0xb4e7ff, 1.0); // increased from 0.45
  fill.position.set(-350, 200, 150);
  scene.add(fill); _studioLightObjs.push(fill);

  // Rim light — back edge separation, warm glow for depth
  const rim = new THREE.PointLight(0xffd0a0, 1.8); // increased from 0.8
  rim.position.set(0, 250, -400);
  rim.distance = 1200;
  scene.add(rim); _studioLightObjs.push(rim);

  // Under-chin fill — prevents dark shadows under jaw/chin
  const underFill = new THREE.DirectionalLight(0xffe8d0, 0.5); // increased from 0.2
  underFill.position.set(0, -50, 200);
  scene.add(underFill); _studioLightObjs.push(underFill);

  // Side accent — accentuates muscle definition from the side
  const accent = new THREE.DirectionalLight(0xfff0e0, 0.8); // increased from 0.3
  accent.position.set(400, 250, -100);
  scene.add(accent); _studioLightObjs.push(accent);
}

function _setupRoomLights() {
  // Overhead point light (warm, just below ceiling)
  const overhead = new THREE.PointLight(0xffe8cc, 1.5, 0, 2);
  overhead.position.set(0, _ROOM_H - 20, 0);
  overhead.castShadow = true;
  overhead.shadow.mapSize.set(1024, 1024);
  scene.add(overhead); _roomLightObjs.push(overhead);

  const ambient = new THREE.AmbientLight(0xfff5e4, 0.25);
  scene.add(ambient); _roomLightObjs.push(ambient);

  const hemi = new THREE.HemisphereLight(0xffeedd, 0x334455, 0.15);
  scene.add(hemi); _roomLightObjs.push(hemi);
}

function _clearLights(arr) {
  arr.forEach(l => scene.remove(l));
  arr.length = 0;
}

function _setupClinicalLights() {
  // Even, shadow-free lighting for accurate body assessment
  const a = new THREE.AmbientLight(0xffffff, 0.5);
  scene.add(a); _studioLightObjs.push(a);
  [[0,400,400],[0,400,-400],[400,400,0],[-400,400,0]].forEach(([x,y,z]) => {
    const d = new THREE.DirectionalLight(0xffffff, 0.4);
    d.position.set(x, y, z);
    scene.add(d); _studioLightObjs.push(d);
  });
  const top = new THREE.DirectionalLight(0xffffff, 0.3);
  top.position.set(0, 600, 0);
  scene.add(top); _studioLightObjs.push(top);
}

function _setupOutdoorLights() {
  // Golden hour outdoor feel
  const hemi = new THREE.HemisphereLight(0x87ceeb, 0x556633, 0.6);
  scene.add(hemi); _studioLightObjs.push(hemi);
  const sun = new THREE.DirectionalLight(0xffd090, 1.6);
  sun.position.set(300, 500, 200);
  sun.castShadow = true;
  sun.shadow.mapSize.set(2048, 2048);
  sun.shadow.camera.left = -400; sun.shadow.camera.right = 400;
  sun.shadow.camera.top = 400;   sun.shadow.camera.bottom = -400;
  scene.add(sun); _studioLightObjs.push(sun);
  const fill = new THREE.DirectionalLight(0x88aacc, 0.25);
  fill.position.set(-200, 100, -300);
  scene.add(fill); _studioLightObjs.push(fill);
}

function setLightPreset(preset) {
  _clearLights(_studioLightObjs);
  _currentLightPreset = preset;
  switch (preset) {
    case 'clinical':
      _setupClinicalLights();
      _ssaoEnabled = false;  // flat/even for measurement accuracy
      break;
    case 'outdoor':
      _setupOutdoorLights();
      _ssaoEnabled = true;
      break;
    default:
      _setupStudioLights();
      _ssaoEnabled = true;
      break;
  }
  _saveViewerSettings();
  document.querySelectorAll('.light-preset-btn').forEach(btn => {
    btn.classList.toggle('active', btn.dataset.preset === preset);
  });
  // Sync SSAO checkbox with preset
  const chk = document.getElementById('chk-ssao');
  if (chk) chk.checked = _ssaoEnabled;
}
window.setLightPreset = setLightPreset;

function _saveViewerSettings() {
  try {
    const settings = {
      lightPreset: _currentLightPreset,
      activeTab: document.querySelector('.tab-btn.active')?.dataset.tab || 'view',
      roomOn: _roomOn,
      autoRotate: _autoRotate,
      ringsVisible: _ringsVisible,
    };
    localStorage.setItem('gtd3d_viewer_settings', JSON.stringify(settings));
  } catch (e) { /* ignore */ }
}

function _restoreViewerSettings() {
  try {
    const raw = localStorage.getItem('gtd3d_viewer_settings');
    if (!raw) return;
    const s = JSON.parse(raw);
    if (s.lightPreset && s.lightPreset !== 'studio') setLightPreset(s.lightPreset);
    if (s.activeTab && s.activeTab !== 'view') switchTab(s.activeTab);
    if (s.roomOn) window.toggleRoom();
    if (s.autoRotate) window.toggleAutoRotate();
    if (s.ringsVisible) window.toggleRings();
  } catch (e) { /* ignore */ }
}

// ── Environment map (HDRI with procedural fallback) ───────────────────────────
function _setupEnvironment() {
  const pmrem = new THREE.PMREMGenerator(renderer);
  pmrem.compileEquirectangularShader();

  // Try loading real studio HDRI first — gives natural skin reflections
  new RGBELoader()
    .setPath('./hdri/')
    .load('studio_small_09_1k.hdr', (hdrTexture) => {
      const envMap = pmrem.fromEquirectangular(hdrTexture).texture;
      scene.environment = envMap;
      // Do NOT set scene.background — keep dark UI background
      hdrTexture.dispose();
      pmrem.dispose();
      console.log('HDRI environment loaded');
    }, undefined, (err) => {
      // Fallback: procedural environment if HDRI fails to load
      console.warn('HDRI load failed, using procedural fallback:', err);
      _buildProceduralEnvironment(pmrem);
    });
}

/** Procedural studio environment — fallback when HDRI is unavailable */
function _buildProceduralEnvironment(pmrem) {
  // Neutral clinical environment — no color tint, pure white/grey
  const envScene = new THREE.Scene();
  envScene.background = new THREE.Color(0x404040);

  // Sky dome — neutral grey
  const domeGeo = new THREE.SphereGeometry(900, 32, 16, 0, Math.PI * 2, 0, Math.PI / 2);
  const domeMat = new THREE.MeshBasicMaterial({
    color: 0x808080, side: THREE.BackSide,
  });
  envScene.add(new THREE.Mesh(domeGeo, domeMat));

  // Ground plane — neutral grey
  const floorGeo = new THREE.PlaneGeometry(2000, 2000);
  const floorMat = new THREE.MeshBasicMaterial({ color: 0x606060 });
  const floor = new THREE.Mesh(floorGeo, floorMat);
  floor.rotation.x = -Math.PI / 2;
  floor.position.y = -10;
  envScene.add(floor);

  // White softboxes — neutral reflections, no color cast
  const panelGeo = new THREE.PlaneGeometry(500, 700);
  const keyPanel = new THREE.Mesh(panelGeo, new THREE.MeshBasicMaterial({ color: 0xffffff }));
  keyPanel.position.set(-450, 350, 350);
  keyPanel.lookAt(0, 150, 0);
  envScene.add(keyPanel);
  const fillPanel = new THREE.Mesh(panelGeo, new THREE.MeshBasicMaterial({ color: 0xfafafa }));
  fillPanel.position.set(450, 280, 300);
  fillPanel.lookAt(0, 150, 0);
  envScene.add(fillPanel);
  const rimPanel = new THREE.Mesh(panelGeo, new THREE.MeshBasicMaterial({ color: 0xeeeeee }));
  rimPanel.position.set(0, 250, -500);
  rimPanel.lookAt(0, 150, 0);
  envScene.add(rimPanel);
  const topPanel = new THREE.Mesh(
    new THREE.PlaneGeometry(600, 600),
    new THREE.MeshBasicMaterial({ color: 0xffffff })
  );
  topPanel.position.set(0, 800, 0);
  topPanel.rotation.x = Math.PI / 2;
  envScene.add(topPanel);
  for (const sx of [-600, 600]) {
    const side = new THREE.Mesh(
      new THREE.PlaneGeometry(300, 500),
      new THREE.MeshBasicMaterial({ color: 0xe0e0e0 })
    );
    side.position.set(sx, 200, 0);
    side.lookAt(0, 150, 0);
    envScene.add(side);
  }

  const envTex = pmrem.fromScene(envScene, 0.04).texture;
  scene.environment = envTex;
  pmrem.dispose();
}

// ── SSAO post-processing setup ────────────────────────────────────────────────
function _initSSAO() {
  // Skip on low-end GPUs
  if (renderer.capabilities.maxTextureSize < 4096) {
    console.warn('SSAO disabled: low-end GPU detected');
    _ssaoEnabled = false;
    return;
  }

  _composer = new EffectComposer(renderer);

  const renderPass = new RenderPass(scene, camera);
  _composer.addPass(renderPass);

  _ssaoPass = new SSAOPass(scene, camera, window.innerWidth, window.innerHeight);
  // INCREASED SSAO for deeper muscle shadows (more "power")
  _ssaoPass.kernelRadius = 48;       // increased from 24
  _ssaoPass.minDistance = 0.0005;    // decreased from 0.001
  _ssaoPass.maxDistance = 0.2;       // increased from 0.15
  _ssaoPass.output = SSAOPass.OUTPUT.Default;
  _composer.addPass(_ssaoPass);

  // ADD BLOOM for "sweaty/oily" skin specular highlights
  const bloomPass = new UnrealBloomPass(new THREE.Vector2(window.innerWidth, window.innerHeight), 1.5, 0.4, 0.85);
  bloomPass.threshold = 0.7; // Only very bright highlights bloom
  bloomPass.strength = 0.25; // Subtle but noticeable bloom
  bloomPass.radius = 0.8;
  _composer.addPass(bloomPass);

  
  // ADD CINEMATIC VIGNETTE
  // vignette removed
  // vignette pass disabled

  const outputPass = new OutputPass();

  _composer.addPass(outputPass);

  console.log('SSAO + Bloom post-processing initialized');
}

function setSSAOEnabled(on) {
  _ssaoEnabled = !!on;
}
window.setSSAOEnabled = setSSAOEnabled;

// ── Load from URL params ──────────────────────────────────────────────────────
function _loadFromUrl() {
  const params      = new URLSearchParams(window.location.search);
  const glbUrl      = params.get('model');
  // Track mesh ID from URL for screenshot upload
  const meshIdMatch = (glbUrl || '').match(/mesh\/(\d+)/);
  if (meshIdMatch) _currentMeshId = parseInt(meshIdMatch[1]);
  const objUrl      = params.get('obj');
  const volStr      = params.get('volume');
  const compareOld  = params.get('compare_old');
  const compareNew  = params.get('compare_new');

  if (volStr) {
    const el = document.getElementById('vol-val');
    if (el) el.textContent = parseFloat(volStr).toFixed(1);
  }

  if (glbUrl) {
    _loadGLB(glbUrl, compareOld && compareNew
      ? () => _applyCompareHeatmap(parseInt(compareOld), parseInt(compareNew))
      : null);
    // FORCE PRO DEFAULT VIEW (Give it a moment to initialize mesh)
    setTimeout(() => window.setViewMode('textured'), 500);
  } else if (objUrl) {
    _loadOBJ(objUrl);
    setTimeout(() => window.setViewMode('textured'), 500);
  } else {
    _showPlaceholder();
    setTimeout(() => window.setViewMode('textured'), 500);
  }
}

async function _applyCompareHeatmap(meshIdOld, meshIdNew) {
  const cid = _customerId();
  try {
    _setStatus('Loading comparison…');
    const resp = await fetch(`/web_app/api/customer/${cid}/compare_meshes`, {
      method: 'POST',
      headers: _authHeaders(),
      body: JSON.stringify({ mesh_id_old: meshIdOld, mesh_id_new: meshIdNew }),
    });
    const data = await resp.json();
    if (data.status !== 'success') {
      _setStatus('Comparison failed: ' + (data.message || '')); return;
    }
    applyHeatmap(bodyMesh, new Float32Array(data.heatmap_values));
    document.querySelector('.heatmap-legend')?.classList.add('visible');
    _setStatus(`Max Δ: ${data.max_displacement_mm}mm  Mean Δ: ${data.mean_displacement_mm}mm`);
    // Update comparison stats panel
    const statsEl = document.getElementById('compare-stats');
    if (statsEl) {
      statsEl.textContent = `Max Δ: ${data.max_displacement_mm}mm | Mean Δ: ${data.mean_displacement_mm}mm`;
      statsEl.style.display = 'block';
    }
    // Activate heatmap button
    document.querySelectorAll('.view-mode-btn').forEach(b => b.classList.remove('active'));
    document.getElementById('btn-heatmap')?.classList.add('active');
  } catch (e) {
    _setStatus('Comparison error: ' + e.message);
  }
}

// ── GLB Loader ────────────────────────────────────────────────────────────────
function _loadGLB(url, onLoaded) {
  _setStatus('Loading model…');
  const loader = new GLTFLoader();

  loader.load(url,
    (gltf) => {
      if (bodyMesh) { scene.remove(bodyMesh); }
      bodyMesh = gltf.scene;
      _applyDefaultMaterial(bodyMesh);
      _centerAndScale(bodyMesh);
      scene.add(bodyMesh);
      _updateStats(bodyMesh);
      const dateEntry = _meshList.find(m => url.includes(`/mesh/${m.id}.glb`));
      _setStatus(dateEntry?.created_on ? dateEntry.created_on.slice(0, 10) : '');
      _createRegionLabels();
      _computeAnalysis();
      if (_ringsVisible) _buildRings();
      _resetVisModes();
      _ghostRich = {};
      // Backup original vertex positions for non-destructive adjust
      _backupOriginalPositions(bodyMesh);
      _hideProgress();
      if (onLoaded) onLoaded();
      // Try to load PBR textures first, fall back to real skin texture,
      // then attach muscle highlighter AFTER material is settled (prevents race condition
      // where PBR material replacement wipes vertex colors set by the highlighter)
      _muscleHL.detach();
      _loadPBRTextures()
        .catch(() => _loadRealSkinTexture())
        .finally(() => {
          _muscleHL.attach(bodyMesh).catch(e => console.warn('[MuscleHighlighter] load failed:', e));
        });
    },
    (xhr) => {
      if (xhr.total > 0) _showProgress(Math.round(xhr.loaded / xhr.total * 100));
      _setStatus(`Loading… ${xhr.total > 0 ? Math.round(xhr.loaded / xhr.total * 100) + '%' : ''}`);
    },
    (err) => {
      console.error(err);
      _setStatus('Error loading model');
      _hideProgress();
      const info = document.getElementById('mesh-info');
      if (info) { info.textContent = 'Failed to load model'; info.style.color = '#ef4444'; }
    },
  );
}

// ── OBJ Loader (legacy) ───────────────────────────────────────────────────────
function _loadOBJ(url) {
  _setStatus('Loading OBJ…');
  const loader = new OBJLoader();
  loader.load(url,
    (obj) => {
      if (bodyMesh) { scene.remove(bodyMesh); }
      bodyMesh = obj;
      _applyDefaultMaterial(bodyMesh);
      _centerAndScale(bodyMesh);
      scene.add(bodyMesh);
      _updateStats(bodyMesh);
      _setStatus('');
    },
    (xhr) => _setStatus(`Loading… ${Math.round(xhr.loaded / xhr.total * 100)}%`),
    (err) => { console.error(err); _setStatus('Error loading OBJ'); },
  );
}

// ── Material helpers ──────────────────────────────────────────────────────────
function _applyDefaultMaterial(object) {
  object.traverse(child => {
    if (child.isMesh) {
      // Store the original loaded material (may have embedded texture)
      const loadedMat = child.material;
      const hasEmbeddedTexture = loadedMat && loadedMat.map;
      const hasNormalMap = loadedMat && loadedMat.normalMap;

      // Save original for "Textured" toggle
      origMaterials.push({ mesh: child, mat: loadedMat });

      if (hasEmbeddedTexture) {
        // GLB has photo-based texture — upgrade to Physical with SSS
        const mat = new THREE.MeshPhysicalMaterial();
        if (loadedMat.isMeshStandardMaterial) {
          THREE.MeshStandardMaterial.prototype.copy.call(mat, loadedMat);
        } else {
          mat.map = loadedMat.map;
          if (loadedMat.normalMap) mat.normalMap = loadedMat.normalMap;
          if (loadedMat.roughnessMap) mat.roughnessMap = loadedMat.roughnessMap;
          if (loadedMat.aoMap) mat.aoMap = loadedMat.aoMap;
        }
        // Skin SSS properties for photorealistic rendering
        mat.roughness = mat.roughnessMap ? 1.0 : 0.42;
        mat.specularIntensity = 0.35;
        mat.specularColor = new THREE.Color(1.0, 1.0, 1.0);
        mat.sheen = 0.3;
        mat.sheenRoughness = 0.45;
        mat.sheenColor = new THREE.Color(0xcc8866);
        mat.clearcoat = 0.1;
        mat.clearcoatRoughness = 0.2;
        mat.envMapIntensity = 0.5;
        mat.side = THREE.DoubleSide;
        if (!mat.normalMap) mat.normalMap = _createSkinNormalMap();
        mat.normalScale = new THREE.Vector2(0.75, 0.75);
        if (mat.roughnessMap) mat.roughnessFactor = 1.0;
        if (mat.aoMap) mat.aoMapIntensity = 0.8;
        // Anisotropic filtering for crisp textures
        const _maxAniso = renderer.capabilities.getMaxAnisotropy();
        if (mat.map) mat.map.anisotropy = _maxAniso;
        if (mat.normalMap) mat.normalMap.anisotropy = _maxAniso;
        if (mat.roughnessMap) mat.roughnessMap.anisotropy = _maxAniso;
        if (mat.aoMap) mat.aoMap.anisotropy = _maxAniso;
        _applyPoreNormalPatch(mat);
        child.material = mat;
        _originalMaterials.set(child, mat);
      } else {
        // No texture — use procedural skin
        const mat = SKIN_MATERIAL.clone();
        _applyPoreNormalPatch(mat);
        child.material = mat;
        _originalMaterials.set(child, mat);
      }
      child.castShadow    = true;
      child.receiveShadow = true;
    }
  });
}

function _centerAndScale(object) {
  // Check if mesh is Z-up (height = Z > Y) — rotate to Y-up for Three.js
  // GLB files are already Y-up by spec, so skip rotation for those
  const preBox = new THREE.Box3().setFromObject(object);
  const preSize = new THREE.Vector3();
  preBox.getSize(preSize);
  if (preSize.z > preSize.y * 1.2) {
    // Z-up mesh (OBJ, old SMPL exports) — rotate to Y-up
    object.rotation.x = -Math.PI / 2;
  }

  const box = new THREE.Box3().setFromObject(object);
  const size = new THREE.Vector3();
  box.getSize(size);

  // Scale so body is ~300 units tall in scene
  const targetH = 300;
  const scale   = size.y > 0 ? targetH / size.y : 1;
  object.scale.setScalar(scale);

  // Re-centre: bottom at y=0, centered in X/Z
  const box2 = new THREE.Box3().setFromObject(object);
  const ctr2 = new THREE.Vector3();
  box2.getCenter(ctr2);
  object.position.sub(ctr2);
  object.position.y += targetH / 2;

  // Set camera to frame full A-pose body (wider than just torso)
  const box3 = new THREE.Box3().setFromObject(object);
  const size3 = new THREE.Vector3();
  box3.getSize(size3);
  const maxDim = Math.max(size3.x, size3.y, size3.z);
  const fov = camera.fov * (Math.PI / 180);
  const camZ = maxDim / (2 * Math.tan(fov / 2)) * 1.6;
  const midY = size3.y * 0.45;
  camera.position.set(0, midY, camZ);
  controls.target.set(0, midY, 0);
  controls.update();
}

function _centerOnly(object) {
  // Same as _centerAndScale but does NOT move the camera
  const preBox = new THREE.Box3().setFromObject(object);
  const preSize = new THREE.Vector3();
  preBox.getSize(preSize);
  if (preSize.z > preSize.y * 1.2) {
    object.rotation.x = -Math.PI / 2;
  }
  const box = new THREE.Box3().setFromObject(object);
  const size = new THREE.Vector3();
  box.getSize(size);
  const targetH = 300;
  const scale = size.y > 0 ? targetH / size.y : 1;
  object.scale.setScalar(scale);
  const box2 = new THREE.Box3().setFromObject(object);
  const ctr2 = new THREE.Vector3();
  box2.getCenter(ctr2);
  object.position.sub(ctr2);
  object.position.y += targetH / 2;
}

// ── Stats panel ───────────────────────────────────────────────────────────────
function _updateStats(object) {
  let verts = 0, faces = 0;
  object.traverse(child => {
    if (child.isMesh && child.geometry) {
      const pos = child.geometry.attributes.position;
      if (pos) { verts += pos.count; faces += Math.floor(pos.count / 3); }
    }
  });
  const ve = document.getElementById('v-count');
  const fe = document.getElementById('f-count');
  if (ve) ve.textContent = verts.toLocaleString();
  if (fe) fe.textContent = faces.toLocaleString();
}

function _setStatus(msg) {
  const el = document.getElementById('mesh-info');
  if (!el) return;
  el.textContent = msg;
  el.classList.toggle('loading', msg.includes('Loading') || msg.includes('loading'));
}

// ── Placeholder (no URL) — try static GLBs first ─────────────────────────────
function _showPlaceholder() {
  const candidates = ['/web_app/api/mesh/template.glb',
                       'gtd3d_body_template.glb',
                       'demo_pbr.glb', 'photorealistic_body.glb', 'skin_textured.glb',
                       'smpl_direct.glb', 'demo.glb'];
  (async () => {
    for (const name of candidates) {
      try {
        const resp = await fetch(name, { method: 'HEAD' });
        if (resp.ok) { _loadGLB(name, null); return; }
      } catch (_) {}
    }
    // Nothing found — show capsule fallback
    _setStatus('No model — use ?model=path.glb');
    if (bodyMesh) { scene.remove(bodyMesh); }
    const geo = new THREE.CapsuleGeometry(30, 80, 16, 32);
    const mat = SKIN_MATERIAL.clone();
    bodyMesh = new THREE.Mesh(geo, mat);
    bodyMesh.position.y = 80;
    bodyMesh.castShadow = true;
    scene.add(bodyMesh);
  })();
}

// ── Raycaster for MeasurementOverlay ─────────────────────────────────────────
function _getMeshIntersection(event) {
  if (!bodyMesh) return null;
  const rect = renderer.domElement.getBoundingClientRect();
  _mouse.x =  ((event.clientX - rect.left)  / rect.width)  * 2 - 1;
  _mouse.y = -((event.clientY - rect.top)   / rect.height) * 2 + 1;
  raycaster.setFromCamera(_mouse, camera);
  const hits = raycaster.intersectObject(bodyMesh, true);
  return hits.length > 0 ? { point: hits[0].point, faceIndex: hits[0].faceIndex } : null;
}

// ── Body region detection ─────────────────────────────────────────────────────
function getBodyRegion(point) {
  // point is THREE.Vector3 in scene space (Y-up, body stands upright)
  if (!bodyMesh) return 'unknown';
  const box = new THREE.Box3().setFromObject(bodyMesh);
  const size = new THREE.Vector3();
  box.getSize(size);
  const minY = box.min.y;
  const y = point.y - minY;         // height from feet in scene units
  const ratio = y / size.y;         // 0=feet, 1=crown
  const x = Math.abs(point.x);      // lateral distance from centre

  // Arms: lateral position beyond shoulder zone and above hip
  if (x > size.x * 0.30 && ratio > 0.40) return 'arm';
  // Legs: lateral position > centre, below waist
  if (x > size.x * 0.15 && ratio < 0.30) return 'leg';

  if (ratio > 0.90) return 'head';
  if (ratio > 0.82) return 'neck';
  if (ratio > 0.70) return 'shoulder';
  if (ratio > 0.58) return 'chest';
  if (ratio > 0.50) return 'waist';
  if (ratio > 0.40) return 'hip';
  if (ratio > 0.28) return 'thigh';
  if (ratio > 0.18) return 'knee';
  if (ratio > 0.08) return 'calf';
  return 'ankle';
}

function _onMeshClick(event) {
  const hit = _getMeshIntersection(event);
  if (!hit) return;

  // Measure mode: collect points
  if (_measureMode) {
    const pt = hit.point.clone();
    const marker = new THREE.Mesh(
      new THREE.SphereGeometry(2, 8, 8),
      new THREE.MeshBasicMaterial({ color: 0xff4444 })
    );
    marker.position.copy(pt);
    scene.add(marker);
    _measurePoints.push({ point: pt, marker });

    if (_measurePoints.length === 2) {
      const geom = new THREE.BufferGeometry().setFromPoints(
        [_measurePoints[0].point, _measurePoints[1].point]
      );
      const line = new THREE.Line(geom, new THREE.LineBasicMaterial({ color: 0xff4444 }));
      scene.add(line);
      _measureLines.push(line);

      const dist = _measurePoints[0].point.distanceTo(_measurePoints[1].point);
      // Convert from scene units back to mm: scene is scaled to targetH=300 over ~1680mm
      const sceneToMm = bodyMesh ? (() => {
        const b = new THREE.Box3().setFromObject(bodyMesh);
        return 1680 / (b.max.y - b.min.y);  // mm per scene unit
      })() : 1;
      const distMm = dist * sceneToMm;
      _setStatus(`Distance: ${distMm.toFixed(1)} mm`);
      _showMeasureLabel(_measurePoints[0].point, _measurePoints[1].point, distMm);
      _measurePoints = [];
    }
    return;
  }

  const region = getBodyRegion(hit.point);
  _showRegionLabel(region, event.clientX, event.clientY);
  _openAdjustPanel(region);
}

function _showRegionLabel(region, cx, cy) {
  let label = document.getElementById('region-label');
  if (!label) {
    label = document.createElement('div');
    label.id = 'region-label';
    label.style.cssText = 'position:fixed;background:rgba(0,0,0,0.75);color:#fff;padding:4px 10px;border-radius:4px;pointer-events:none;font-size:13px;z-index:100;';
    document.body.appendChild(label);
  }
  label.textContent = region.charAt(0).toUpperCase() + region.slice(1);
  label.style.left = (cx + 12) + 'px';
  label.style.top  = (cy - 10) + 'px';
  label.style.display = 'block';
  clearTimeout(label._timer);
  label._timer = setTimeout(() => { label.style.display = 'none'; }, 2500);
}

// ── Floating region labels ────────────────────────────────────────────────────
let _labelsEnabled  = false;
const _labelEls     = [];   // HTML div elements
const _labelAnchors = [];   // THREE.Vector3 world positions

const _LABEL_DEFS = [
  { name: 'Head',     yFrac: 0.95 },
  { name: 'Neck',     yFrac: 0.86 },
  { name: 'Shoulder', yFrac: 0.76 },
  { name: 'Chest',    yFrac: 0.64 },
  { name: 'Waist',    yFrac: 0.54 },
  { name: 'Hip',      yFrac: 0.45 },
  { name: 'Thigh',    yFrac: 0.34 },
  { name: 'Knee',     yFrac: 0.23 },
  { name: 'Calf',     yFrac: 0.13 },
];

function _createRegionLabels() {
  // Remove any previous labels
  _labelEls.forEach(el => el.remove());
  _labelEls.length = 0;
  _labelAnchors.length = 0;

  if (!bodyMesh) return;
  const box = new THREE.Box3().setFromObject(bodyMesh);
  const h   = box.max.y - box.min.y;
  const xOff = (box.max.x - box.min.x) * 0.55 + 10;  // just outside the body edge

  for (const def of _LABEL_DEFS) {
    const worldPos = new THREE.Vector3(xOff, box.min.y + def.yFrac * h, 0);
    _labelAnchors.push(worldPos);

    const el = document.createElement('div');
    el.className = 'region-label-float';
    el.textContent = def.name;
    el.style.cssText = [
      'position:fixed',
      'background:rgba(0,0,0,0.65)',
      'color:#e0e0e0',
      'font:11px/1.4 sans-serif',
      'padding:2px 7px',
      'border-radius:3px',
      'pointer-events:none',
      'white-space:nowrap',
      'display:none',
      'z-index:50',
      'border-left:2px solid rgba(100,180,255,0.7)',
    ].join(';');
    document.body.appendChild(el);
    _labelEls.push(el);
  }

  if (_labelsEnabled) _setLabelsVisible(true);
}

function _setLabelsVisible(on) {
  _labelEls.forEach(el => { el.style.display = on ? 'block' : 'none'; });
}

function _updateRegionLabels() {
  if (!_labelsEnabled || !_labelEls.length) return;
  const w = window.innerWidth, h = window.innerHeight;
  const tmp = new THREE.Vector3();
  for (let i = 0; i < _labelAnchors.length; i++) {
    tmp.copy(_labelAnchors[i]);
    tmp.project(camera);          // NDC -1..1
    const sx = (tmp.x * 0.5 + 0.5) * w;
    const sy = (-(tmp.y) * 0.5 + 0.5) * h;
    // Hide if behind camera or off-screen
    if (tmp.z > 1 || sx < 0 || sx > w || sy < 0 || sy > h) {
      _labelEls[i].style.display = 'none';
    } else {
      _labelEls[i].style.display = 'block';
      _labelEls[i].style.left = sx + 8 + 'px';
      _labelEls[i].style.top  = sy - 8 + 'px';
    }
  }
}

window.toggleLabels = function() {
  _labelsEnabled = !_labelsEnabled;
  if (_labelsEnabled && bodyMesh && !_labelEls.length) _createRegionLabels();
  _setLabelsVisible(_labelsEnabled);
  const btn = document.getElementById('btn-labels');
  if (btn) btn.classList.toggle('active', _labelsEnabled);
};

// ── Adjustment panel ──────────────────────────────────────────────────────────
let _currentRegion = null;
const _regionAdjustments = {};  // region → {width, depth, length}
const _origPositions = new WeakMap(); // child mesh → Float32Array backup

function _backupOriginalPositions(root) {
  if (!root) return;
  let count = 0;
  root.traverse(child => {
    if (!child.isMesh || !child.geometry) return;
    const pos = child.geometry.attributes.position;
    if (pos) {
      _origPositions.set(child, new Float32Array(pos.array));
      count++;
    }
  });
  console.log(`[Adjust] Backed up ${count} mesh positions`);
}

// Expose debug state for agent_browser.py
window._adjustDebug = () => {
  // Sample vertex positions: 5 from start + 5 from mid-body (hip zone)
  const verts = [], hipVerts = [];
  if (bodyMesh) bodyMesh.traverse(c => {
    if (c.isMesh && c.geometry?.attributes?.position && verts.length === 0) {
      const p = c.geometry.attributes.position;
      // Find body height range
      let minY = Infinity, maxY = -Infinity;
      for (let i = 0; i < p.count; i++) { const y = p.getY(i); if (y < minY) minY = y; if (y > maxY) maxY = y; }
      const h = maxY - minY;
      const hipMin = minY + 0.40 * h, hipMax = minY + 0.55 * h;
      for (let i = 0; i < Math.min(5, p.count); i++)
        verts.push([+p.getX(i).toFixed(3), +p.getY(i).toFixed(3), +p.getZ(i).toFixed(3)]);
      // Collect hip verts
      for (let i = 0; i < p.count && hipVerts.length < 5; i++) {
        const y = p.getY(i);
        if (y >= hipMin && y <= hipMax) hipVerts.push([+p.getX(i).toFixed(4), +p.getY(i).toFixed(4), +p.getZ(i).toFixed(4), i]);
      }
    }
  });
  return {
    currentRegion: _currentRegion,
    hasBodyMesh: !!bodyMesh,
    regionAdjustments: { ..._regionAdjustments },
    origBackupCount: (() => { let c = 0; if (bodyMesh) bodyMesh.traverse(ch => { if (ch.isMesh && _origPositions.has(ch)) c++; }); return c; })(),
    sampleVerts: verts,
    hipVerts: hipVerts,
  };
};

function _restoreOriginalPositions(root) {
  if (!root) return;
  let restored = 0, missed = 0;
  root.traverse(child => {
    if (!child.isMesh || !child.geometry) return;
    const orig = _origPositions.get(child);
    if (!orig) { missed++; return; }
    const pos = child.geometry.attributes.position;
    pos.array.set(orig);
    pos.needsUpdate = true;
    child.geometry.computeBoundingBox();
    restored++;
  });
  console.log(`[Adjust] Restored ${restored} meshes, ${missed} missed`);
}

// ── Live deformation: debounced server re-deform via update_deformation API ───

async function _fetchAndCacheProfile() {
  if (_cachedProfile) return _cachedProfile;
  try {
    const cid = _customerId();
    const resp = await fetch(`/web_app/api/customer/${cid}/body_profile`,
      { headers: _authHeaders() });
    const data = await resp.json();
    if (data.status === 'success') {
      _cachedProfile = data.profile || data;
    }
  } catch (e) {
    console.warn('Failed to fetch body profile for deformation:', e);
  }
  return _cachedProfile;
}

function _scheduleDeformationUpdate() {
  clearTimeout(_deformDebounceTimer);
  _deformDebounceTimer = setTimeout(_doDeformationUpdate, 500);
}

async function _doDeformationUpdate() {
  // Disabled: deform_template produces malformed meshes.
  // Adjustments are preview-only (client-side vertex edits).
  // Use saveAdjustments() to persist measurement deltas to the profile.
  return;
}

const REGION_TO_FIELD = {
  chest:    'chest_circumference_cm',
  waist:    'waist_circumference_cm',
  hip:      'hip_circumference_cm',
  thigh:    'thigh_circumference_cm',
  calf:     'calf_circumference_cm',
  arm:      'bicep_circumference_cm',
  neck:     'neck_circumference_cm',
  head:     'head_circumference_cm',
  shoulder: 'shoulder_width_cm',
};

// Map muscle group keys → body region for adjustment
const MUSCLE_TO_REGION = {
  pectorals: 'chest', traps: 'neck', abs: 'waist', obliques: 'waist',
  glutes: 'hip', quads_l: 'thigh', quads_r: 'thigh',
  calves_l: 'calf', calves_r: 'calf',
  biceps_l: 'arm', biceps_r: 'arm',
  forearms_l: 'arm', forearms_r: 'arm',
  deltoids_l: 'shoulder', deltoids_r: 'shoulder',
};

// Expose for debugging
window._getRegionZRange = function(region) { return _getRegionZRange(region); };
window._getBodyMesh = () => bodyMesh;

// Called by muscle group panel buttons
window.selectMuscleRegion = function(muscleKey) {
  const region = MUSCLE_TO_REGION[muscleKey];
  if (region) _openAdjustPanel(region);
};

function _openAdjustPanel(region) {
  _currentRegion = region;
  const panel = document.getElementById('adjust-panel');
  // Update Studio tab region label
  const studioLabel = document.getElementById('studio-region-name');
  if (studioLabel) studioLabel.textContent = region.charAt(0).toUpperCase() + region.slice(1);
  if (!panel) return;
  document.getElementById('adjust-region').textContent =
    region.charAt(0).toUpperCase() + region.slice(1);
  // Restore saved slider values (both Scene and Studio panels)
  const saved = _regionAdjustments[region] || { width: 0, depth: 0, length: 0 };
  const dimMap = { width: 'w', depth: 'd', length: 'l' };
  ['width', 'depth', 'length'].forEach(dim => {
    const slider = document.getElementById('adj-' + dim);
    const val    = document.getElementById('adj-' + dim + '-val');
    if (slider) slider.value = saved[dim];
    if (val)    val.textContent = saved[dim];
    // Sync Studio tab sliders
    const studioSlider = document.getElementById('studio-adj-' + dimMap[dim]);
    const studioVal    = document.getElementById('studio-adj-' + dimMap[dim] + '-val');
    if (studioSlider) studioSlider.value = saved[dim];
    if (studioVal)    studioVal.textContent = saved[dim] + 'mm';
  });
  panel.style.display = 'block';
}

function _getRegionZRange(region) {
  // Returns [min, max] in RAW GEOMETRY coordinates (the axis that represents height).
  // The mesh may be Z-up (raw) or Y-up (GLB). We detect which axis is tallest.
  if (!bodyMesh) return [0, 300];
  let minH = Infinity, maxH = -Infinity;
  let heightAxis = 2; // default Z (for Z-up meshes rotated to Y-up by _centerAndScale)
  bodyMesh.traverse(child => {
    if (!child.isMesh || !child.geometry?.attributes?.position) return;
    const pos = child.geometry.attributes.position;
    // Detect height axis from geometry bounding box (tallest raw axis)
    if (heightAxis === 2) {
      let ranges = [0, 0, 0];
      for (let a = 0; a < 3; a++) {
        let mn = Infinity, mx = -Infinity;
        for (let i = 0; i < pos.count; i++) {
          const v = a === 0 ? pos.getX(i) : a === 1 ? pos.getY(i) : pos.getZ(i);
          if (v < mn) mn = v; if (v > mx) mx = v;
        }
        ranges[a] = mx - mn;
      }
      heightAxis = ranges[2] > ranges[1] ? 2 : 1; // Z-up or Y-up
    }
    for (let i = 0; i < pos.count; i++) {
      const v = heightAxis === 2 ? pos.getZ(i) : pos.getY(i);
      if (v < minH) minH = v;
      if (v > maxH) maxH = v;
    }
  });
  const h = maxH - minH;
  const RANGES = {
    ankle:    [0.00, 0.08], calf:   [0.08, 0.22], knee:   [0.22, 0.32],
    thigh:    [0.32, 0.45], hip:    [0.45, 0.55], waist:  [0.55, 0.65],
    chest:    [0.65, 0.78], shoulder:[0.78, 0.85], neck:  [0.85, 0.92],
    head:     [0.92, 1.00], arm:    [0.55, 1.00], leg:    [0.00, 0.45],
  };
  const r = RANGES[region] || [0, 1];
  return [minH + r[0] * h, minH + r[1] * h, heightAxis];
}

window.applyAdjustment = function() {
  if (!bodyMesh || !_currentRegion) return;
  const wDelta = parseFloat(document.getElementById('adj-width')?.value || 0);
  const dDelta = parseFloat(document.getElementById('adj-depth')?.value || 0);
  const lDelta = parseFloat(document.getElementById('adj-length')?.value || 0);
  _regionAdjustments[_currentRegion] = { width: wDelta, depth: dDelta, length: lDelta };

  // Restore original positions first, then re-apply ALL region adjustments
  _restoreOriginalPositions(bodyMesh);

  for (const [region, deltas] of Object.entries(_regionAdjustments)) {
    if (deltas.width === 0 && deltas.depth === 0 && deltas.length === 0) continue;
    const [hMin, hMax, hAxis] = _getRegionZRange(region);
    let _modCount = 0, _totalCount = 0;
    console.log(`[Adjust] Applying ${region}: w=${deltas.width} d=${deltas.depth} l=${deltas.length} hAxis=${hAxis} range=[${hMin.toFixed(3)}, ${hMax.toFixed(3)}]`);
    bodyMesh.traverse(child => {
      if (!child.isMesh || !child.geometry) return;
      const pos = child.geometry.attributes.position;
      if (!pos) return;
      _totalCount += pos.count;
      for (let i = 0; i < pos.count; i++) {
        // Get height value along the correct axis
        const hVal = hAxis === 2 ? pos.getZ(i) : pos.getY(i);
        if (hVal < hMin || hVal > hMax) continue;
        _modCount++;
        // Scale the two non-height axes (width + depth)
        // Slider is ±30 (meant as mm). Geometry is in meters. Convert: mm/1000 = meters.
        const wScale = deltas.width / 1000;  // mm → meters
        const dScale = deltas.depth / 1000;
        const lScale = deltas.length / 1000;
        const x = pos.getX(i);
        const crossVal = hAxis === 2 ? pos.getY(i) : pos.getZ(i);
        // Additive offset scaled by normalized distance from center
        const dist = Math.sqrt(x * x + crossVal * crossVal);
        if (dist > 0.001) {
          const nx = x / dist, nc = crossVal / dist;
          pos.setX(i, x + nx * wScale);
          if (hAxis === 2)
            pos.setY(i, crossVal + nc * dScale);
          else
            pos.setZ(i, crossVal + nc * dScale);
        }
        // Length: additive along height axis
        if (hMax > hMin) {
          const lOff = lScale * (hVal - hMin) / (hMax - hMin);
          if (hAxis === 2) pos.setZ(i, hVal + lOff);
          else pos.setY(i, hVal + lOff);
        }
      }
      pos.needsUpdate = true;
      child.geometry.computeBoundingBox();
    });
    console.log(`[Adjust] Modified ${_modCount}/${_totalCount} verts in ${region}`);
  }
};

window.resetAdjustment = function() {
  // Reset all sliders (Scene + Studio tabs)
  ['adj-width', 'adj-depth', 'adj-length'].forEach(id => {
    const el = document.getElementById(id);
    if (el) el.value = 0;
    const vEl = document.getElementById(id + '-val');
    if (vEl) vEl.textContent = 0;
  });
  const dimMap = { width: 'w', depth: 'd', length: 'l' };
  ['width', 'depth', 'length'].forEach(dim => {
    const s = document.getElementById('studio-adj-' + dimMap[dim]);
    const v = document.getElementById('studio-adj-' + dimMap[dim] + '-val');
    if (s) s.value = 0;
    if (v) v.textContent = '0mm';
  });

  // Clear ALL region adjustments and fully restore original mesh
  for (const key of Object.keys(_regionAdjustments)) delete _regionAdjustments[key];
  _restoreOriginalPositions(bodyMesh);
  console.log('[Adjust] Reset: all adjustments cleared, mesh restored');
};

window.saveAdjustments = async function() {
  // Build field→delta map from all adjusted regions
  const fieldDeltas = {};
  for (const [region, deltas] of Object.entries(_regionAdjustments)) {
    const field = REGION_TO_FIELD[region];
    if (field && deltas.width !== 0) {
      // Width slider is ±30 scene units ≈ mm; circumference delta = π * width_delta / 10 cm
      fieldDeltas[field] = (fieldDeltas[field] || 0) + Math.PI * deltas.width / 10;
    }
  }
  if (Object.keys(fieldDeltas).length === 0) {
    _setStatus('No changes to save'); return;
  }

  try {
    const cid = _customerId();

    // 1. Fetch current profile so we can post absolute values
    const getResp = await fetch(`/web_app/api/customer/${cid}/body_profile`,
      { headers: _authHeaders() });
    const profile = await getResp.json();
    if (profile.status !== 'success') {
      _setStatus('Save failed: could not read profile'); return;
    }

    // 2. Build absolute updates: current value + delta
    const updates = {};
    for (const [field, delta] of Object.entries(fieldDeltas)) {
      const current = parseFloat(profile.profile?.[field] || profile[field] || 0);
      updates[field] = Math.max(0, current + delta);
    }

    // 3. POST absolute values to profile
    const postResp = await fetch(`/web_app/api/customer/${cid}/body_profile`, {
      method: 'POST',
      headers: _authHeaders(),
      body: JSON.stringify(updates),
    });
    const result = await postResp.json();
    if (result.status !== 'success') {
      _setStatus('Save failed: ' + (result.message || '')); return;
    }

    _setStatus('Saved — regenerating mesh…');

    // 4. Regenerate mesh with updated profile
    const meshResp = await fetch(`/web_app/api/customer/${cid}/body_model`, {
      method: 'POST',
      headers: _authHeaders(),
      body: JSON.stringify({}),
    });
    const meshResult = await meshResp.json();
    if (meshResult.glb_url) {
      // Clear adjustments and reload with new mesh
      for (const key of Object.keys(_regionAdjustments)) delete _regionAdjustments[key];
      _loadGLB(meshResult.glb_url, null);
      _setStatus('');
    } else {
      _setStatus('Mesh regeneration failed');
    }
  } catch (e) {
    _setStatus('Save failed: ' + e.message);
  }
};

// ── Heatmap ───────────────────────────────────────────────────────────────────
function applyHeatmap(mesh, perVertexValues) {
  // perVertexValues: Float32Array, length = vertex count, range 0..1
  mesh.traverse(child => {
    if (!child.isMesh || !child.geometry) return;
    const pos = child.geometry.attributes.position;
    if (!pos) return;
    const n = pos.count;
    const src = perVertexValues || new Float32Array(n).fill(0.5);
    const colors = new Float32Array(n * 3);
    for (let i = 0; i < n; i++) {
      const t = Math.max(0, Math.min(1, src[i] || 0.5));
      // Blue (0) → Green (0.5) → Red (1)
      let r, g, b;
      if (t < 0.5) {
        const u = t * 2;
        r = 0.23 * (1 - u);
        g = 0.77 * u;
        b = 0.95 * (1 - u);
      } else {
        const u = (t - 0.5) * 2;
        r = 0.94 * u;
        g = 0.77 * (1 - u);
        b = 0.05 * (1 - u);
      }
      colors[i * 3]     = r;
      colors[i * 3 + 1] = g;
      colors[i * 3 + 2] = b;
    }
    child.geometry.setAttribute('color', new THREE.BufferAttribute(colors, 3));
    child.material = new THREE.MeshStandardMaterial({
      vertexColors: true, roughness: 0.7, side: THREE.DoubleSide,
    });
  });
}

function clearHeatmap() {
  origMaterials.forEach(({ mesh, mat }) => { mesh.material = mat; });
  if (bodyMesh) {
    bodyMesh.traverse(child => {
      if (child.isMesh && child.geometry) {
        const colorAttr = child.geometry.attributes.color;
        if (colorAttr) {
          // Reset to white instead of deleting — preserves the buffer for muscle highlighter
          const arr = colorAttr.array;
          for (let i = 0; i < arr.length; i++) arr[i] = 1.0;
          colorAttr.needsUpdate = true;
          // Disable vertexColors on material so white has no visual effect
          if (child.material && child.material.vertexColors) {
            child.material.vertexColors = false;
            child.material.needsUpdate = true;
          }
        }
      }
    });
  }
}

/** Re-sync muscle highlighter after material changes (call after any view mode switch). */
function _resyncMuscleHighlighter() {
  if (_muscleHL && _muscleHL.activeGroup) {
    _muscleHL._ensureVertexColors();
    _muscleHL.highlight(_muscleHL.activeGroup);
  }
}

// ── Public control functions (called from index.html buttons) ─────────────────
window.setViewMode = function(mode) {
  if (!bodyMesh) return;
  document.querySelectorAll('.view-mode-btn').forEach(b => b.classList.remove('active'));
  const btn = document.getElementById('btn-' + mode);
  if (btn) btn.classList.add('active');

  if (mode === 'solid') {
    heatmapOn = false;
    clearHeatmap();
    document.querySelector('.heatmap-legend')?.classList.remove('visible');
  } else if (mode === 'wireframe') {
    heatmapOn = false;
    clearHeatmap();
    bodyMesh.traverse(c => { if (c.isMesh) c.material.wireframe = true; });
    document.querySelector('.heatmap-legend')?.classList.remove('visible');
  } else if (mode === 'textured') {
    heatmapOn = false;
    clearHeatmap();
    // Restore original loaded materials (which may include textures)
    if (bodyMesh) {
      bodyMesh.traverse(c => {
        if (c.isMesh) {
          const orig = _originalMaterials.get(c);
          if (orig) c.material = orig;
        }
      });
    }
    document.querySelector('.heatmap-legend')?.classList.remove('visible');
  } else if (mode === 'skin') {
    heatmapOn = false;
    clearHeatmap();
    if (bodyMesh) bodyMesh.traverse(c => { if (c.isMesh) c.material = SKIN_MATERIAL; });
    document.querySelector('.heatmap-legend')?.classList.remove('visible');
    const tilingCtrl = document.getElementById('skin-tiling');
    if (tilingCtrl) tilingCtrl.style.display = 'block';
  } else if (mode === 'heatmap') {
    heatmapOn = true;
    const vCount = (() => {
      let n = 0;
      bodyMesh.traverse(c => { if (c.isMesh && c.geometry?.attributes.position) n += c.geometry.attributes.position.count; });
      return n;
    })();
    const testData = new Float32Array(vCount);
    for (let i = 0; i < vCount; i++) testData[i] = i / vCount;
    applyHeatmap(bodyMesh, testData);
    document.querySelector('.heatmap-legend')?.classList.add('visible');
  }
  // Hide tiling control unless skin mode
  if (mode !== 'skin') {
    const tilingCtrl = document.getElementById('skin-tiling');
    if (tilingCtrl) tilingCtrl.style.display = 'none';
  }
  // Re-sync muscle highlighter after material change (preserves active highlight)
  _resyncMuscleHighlighter();
};

window.toggleWireframe = function() { window.setViewMode('wireframe'); };

window.resetCamera = function() {
  let endPos, endTarget;
  if (bodyMesh) {
    const box = new THREE.Box3().setFromObject(bodyMesh);
    const size = new THREE.Vector3();
    box.getSize(size);
    const maxDim = Math.max(size.x, size.y, size.z);
    const fov = camera.fov * (Math.PI / 180);
    const camZ = maxDim / (2 * Math.tan(fov / 2)) * 1.6;
    const midY = size.y * 0.45;
    endPos    = new THREE.Vector3(0, midY, camZ);
    endTarget = new THREE.Vector3(0, midY, 0);
  } else {
    endPos    = new THREE.Vector3(0, 150, 400);
    endTarget = new THREE.Vector3(0, 80, 0);
  }
  _camTransition = {
    startPos:    camera.position.clone(),
    startTarget: controls.target.clone(),
    endPos,
    endTarget,
    startTime: performance.now(),
    duration:  600,
  };
};

window.takeScreenshot = function() {
  const scale = 2;
  const w = renderer.domElement.width;
  const h = renderer.domElement.height;

  // Render at high resolution
  renderer.setSize(w * scale, h * scale, false);
  renderer.render(scene, camera);

  // Capture to offscreen canvas
  const canvas = document.createElement('canvas');
  canvas.width = w * scale;
  canvas.height = h * scale;
  const ctx = canvas.getContext('2d');
  ctx.drawImage(renderer.domElement, 0, 0);

  // Restore renderer immediately
  renderer.setSize(w, h, false);
  renderer.render(scene, camera);

  // Draw watermark bar at bottom
  const barH = 44 * scale;
  ctx.fillStyle = 'rgba(0,0,0,0.7)';
  ctx.fillRect(0, canvas.height - barH, canvas.width, barH);
  ctx.fillStyle = '#e0e0e0';
  ctx.font = `bold ${14 * scale}px sans-serif`;
  const date = new Date().toLocaleDateString('en-US', {year:'numeric', month:'short', day:'numeric'});
  ctx.fillText('GTD3D \u2014 ' + date, 12 * scale, canvas.height - barH + 20 * scale);
  if (_bodyProfile) {
    ctx.font = `${11 * scale}px sans-serif`;
    ctx.fillStyle = '#94a3b8';
    const parts = [];
    if (_bodyProfile.height_cm) parts.push('H:' + _bodyProfile.height_cm + 'cm');
    if (_bodyProfile.weight_kg) parts.push('W:' + _bodyProfile.weight_kg + 'kg');
    if (_bodyProfile.chest_circumference_cm) parts.push('Ch:' + _bodyProfile.chest_circumference_cm + 'cm');
    if (_bodyProfile.waist_circumference_cm) parts.push('Wa:' + _bodyProfile.waist_circumference_cm + 'cm');
    const name = _bodyProfile.name || '';
    const gender = _bodyProfile.gender || '';
    if (name || gender) parts.unshift([name, gender].filter(Boolean).join(' · '));
    if (parts.length) ctx.fillText(parts.join('  \u00b7  '), 12 * scale, canvas.height - barH + 36 * scale);
  }

  const dataURL = canvas.toDataURL('image/png');

  // Download
  const link = document.createElement('a');
  link.download = `gtd3d_${Date.now()}.png`;
  link.href = dataURL;
  link.click();

  // Upload screenshot to server (non-blocking, best-effort)
  if (_currentMeshId && _viewerToken) {
    fetch(`/web_app/api/mesh/${_currentMeshId}/screenshot`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'Authorization': `Bearer ${_viewerToken}` },
      body: JSON.stringify({ image: dataURL }),
    }).catch(() => {});
  }
};

window.clearMeasurements = function() {
  if (window.MeasurementOverlay) window.MeasurementOverlay.clear();
  // Clear measure mode markers, lines, labels
  _measureLines.forEach(l => scene.remove(l));
  _measureLines = [];
  _measurePoints.forEach(p => scene.remove(p.marker));
  _measurePoints = [];
  _measureLabels.forEach(l => l.remove());
  _measureLabels = [];
  // Clear cross-section
  if (_sectionPlane)   { scene.remove(_sectionPlane);   _sectionPlane   = null; }
  if (_sectionOutline) { scene.remove(_sectionOutline); _sectionOutline = null; }
  const secStats = document.getElementById('section-stats');
  if (secStats) secStats.textContent = '';
};

// ── Mesh comparison UI ────────────────────────────────────────────────────────
async function _loadMeshList() {
  if (!_viewerToken) return;
  try {
    const cid = _customerId();
    const resp = await fetch(`/web_app/api/customer/${cid}/meshes`, {
      headers: { 'Authorization': `Bearer ${_viewerToken}` }
    });
    const data = await resp.json();
    if (data.status !== 'success') return;
    _meshList = data.meshes;
    if (_meshList.length > 1) {
      const info = document.getElementById('mesh-info');
      if (info && !info.textContent.includes('scan')) {
        info.textContent += ` · ${_meshList.length} scans`;
      }
    }
    // Populate timeline slider
    const slider = document.getElementById('timeline-slider');
    const dateEl = document.getElementById('timeline-date');
    if (slider && _meshList.length > 0) {
      slider.max = _meshList.length - 1;
      slider.value = 0;
      if (dateEl) dateEl.textContent = _meshList[0].created_on;
    }
    const oldSel = document.getElementById('compare-old');
    const newSel = document.getElementById('compare-new');
    if (!oldSel || !newSel) return;
    oldSel.innerHTML = '<option value="">— none —</option>';
    newSel.innerHTML = '<option value="">— none —</option>';
    for (const m of data.meshes) {
      const label = `#${m.id} ${m.created_on} (${m.muscle_group})`;
      const opt1 = `<option value="${m.id}">${label}</option>`;
      oldSel.innerHTML += opt1;
      newSel.innerHTML += opt1;
    }
  } catch (e) { console.warn('Failed to load mesh list:', e); }
}

window.switchMesh = function(idx) {
  idx = parseInt(idx);
  if (idx < 0 || idx >= _meshList.length) return;
  const m = _meshList[idx];
  if (bodyMesh) { scene.remove(bodyMesh); bodyMesh = null; }
  if (_ghostMesh) { scene.remove(_ghostMesh); _ghostMesh = null; }
  origMaterials = [];
  _originalMaterials.clear();
  _currentMeshId = m.id;
  _setStatus('Loading scan #' + m.id + '…');
  const loader = new GLTFLoader();
  loader.load(`/web_app/api/mesh/${m.id}.glb`, (gltf) => {
    bodyMesh = gltf.scene;
    _applyDefaultMaterial(bodyMesh);
    _centerOnly(bodyMesh);
    scene.add(bodyMesh);
    _updateStats(bodyMesh);
    _setStatus('Scan #' + m.id + ' — ' + m.created_on);
    _createRegionLabels();
    _computeAnalysis();
    if (_ringsVisible) _buildRings();
    _resetVisModes();
  });
  const dateEl = document.getElementById('timeline-date');
  if (dateEl) dateEl.textContent = m.created_on;
};

window.toggleTimelinePlay = function() {
  const slider = document.getElementById('timeline-slider');
  const btn = document.getElementById('btn-play');
  if (!slider || _meshList.length < 2) return;
  if (_timelineTimer) {
    clearInterval(_timelineTimer);
    _timelineTimer = null;
    if (btn) btn.textContent = 'Play';
    return;
  }
  if (btn) btn.textContent = 'Stop';
  _timelineTimer = setInterval(() => {
    let idx = parseInt(slider.value) + 1;
    if (idx >= _meshList.length) idx = 0;
    slider.value = idx;
    window.switchMesh(idx);
  }, 2500);
};

window.loadGhost = function() {
  const sel = document.getElementById('compare-old');
  const meshId = sel?.value;
  if (!meshId) { _setStatus('Select a "Before" mesh first'); return; }
  if (_ghostMesh) { scene.remove(_ghostMesh); _ghostMesh = null; }
  _setStatus('Loading ghost…');
  const loader = new GLTFLoader();
  loader.load(`/web_app/api/mesh/${meshId}.glb`, (gltf) => {
    _ghostMesh = gltf.scene;
    _ghostMesh.traverse(c => {
      if (c.isMesh) {
        c.material = new THREE.MeshStandardMaterial({
          color: 0x44ff88, wireframe: true, transparent: true, opacity: 0.3,
        });
        c.castShadow = false;
        c.receiveShadow = false;
      }
    });
    _centerOnly(_ghostMesh);
    scene.add(_ghostMesh);
    const ghostEntry = _meshList.find(m => String(m.id) === String(meshId));
    const ghostDate = ghostEntry ? ` (${ghostEntry.created_on.slice(0, 10)})` : '';
    _setStatus('Ghost: #' + meshId + ghostDate);
    if (window.switchTab) switchTab('analyze');
    _computeAnalysis();
    if (_ringsVisible) _buildGhostRings();
    if (_growthMode) _applyGrowthColors();
    if (_sliceMode) _buildSliceView();
    if (_axisVisible) _buildPostureAxis();
    _refreshProfile();
  });
};

window.clearGhost = function() {
  if (_ghostMesh) { scene.remove(_ghostMesh); _ghostMesh = null; }
  if (_ghostRingGroup) { scene.remove(_ghostRingGroup); _ghostRingGroup = null; }
  _setStatus('');
  _computeAnalysis();
  if (_ringsVisible) _buildRings();
  if (_growthMode) {
    _growthMode = false; _removeGrowthColors();
    const gl = document.getElementById('growth-legend'); if (gl) gl.style.display = 'none';
    document.getElementById('btn-growth')?.classList.remove('active');
  }
  if (_sliceMode) _buildSliceView();  // rebuild without ghost outlines
  if (_axisVisible) _buildPostureAxis();
  _ghostRich = {};
  _refreshProfile();
};

let _statsVisible = false;
let _bodyProfile  = null;
async function _loadBodyStats() {
  if (!_viewerToken) return;
  try {
    const cid = _customerId();
    const resp = await fetch(`/web_app/api/customer/${cid}/body_profile`, {
      headers: _authHeaders(),
    });
    const data = await resp.json();
    if (data.status !== 'success' || !data.profile) return;
    const p = data.profile;
    _bodyProfile = p;
    const el = document.getElementById('body-stats-content');
    if (!el) return;
    const stats = [
      ['Height', p.height_cm, 'cm'],
      ['Weight', p.weight_kg, 'kg'],
      ['Chest', p.chest_circumference_cm, 'cm'],
      ['Waist', p.waist_circumference_cm, 'cm'],
      ['Hip', p.hip_circumference_cm, 'cm'],
      ['Thigh', p.thigh_circumference_cm, 'cm'],
      ['Bicep', p.bicep_circumference_cm, 'cm'],
      ['Calf', p.calf_circumference_cm, 'cm'],
      ['Neck', p.neck_circumference_cm, 'cm'],
      ['Shoulder', p.shoulder_width_cm, 'cm'],
    ];
    el.innerHTML = stats
      .filter(([, v]) => v != null)
      .map(([name, val, unit]) =>
        `<div style="display:flex;justify-content:space-between;"><span style="color:#94a3b8;">${name}</span><strong>${val}</strong><span style="color:#666;">${unit}</span></div>`
      ).join('');
  } catch (e) { console.warn('Stats load failed:', e); }
}

window.toggleBodyStats = function() {
  _statsVisible = !_statsVisible;
  const panel = document.getElementById('body-stats-panel');
  if (panel) panel.style.display = _statsVisible ? 'block' : 'none';
  document.getElementById('btn-stats')?.classList.toggle('active', _statsVisible);
};

window.copyStats = function() {
  if (!_bodyProfile) { _setStatus('No body profile loaded'); return; }
  const p = _bodyProfile;
  const lines = [
    'GTD3D Body Measurements \u2014 ' + new Date().toLocaleDateString('en-US', {year:'numeric', month:'short', day:'numeric'}),
    '',
    p.height_cm ? 'Height: ' + p.height_cm + ' cm' : null,
    p.weight_kg ? 'Weight: ' + p.weight_kg + ' kg' : null,
    p.chest_circumference_cm ? 'Chest: ' + p.chest_circumference_cm + ' cm' : null,
    p.waist_circumference_cm ? 'Waist: ' + p.waist_circumference_cm + ' cm' : null,
    p.hip_circumference_cm ? 'Hip: ' + p.hip_circumference_cm + ' cm' : null,
    p.thigh_circumference_cm ? 'Thigh: ' + p.thigh_circumference_cm + ' cm' : null,
    p.bicep_circumference_cm ? 'Bicep: ' + p.bicep_circumference_cm + ' cm' : null,
    p.calf_circumference_cm ? 'Calf: ' + p.calf_circumference_cm + ' cm' : null,
    p.neck_circumference_cm ? 'Neck: ' + p.neck_circumference_cm + ' cm' : null,
    p.shoulder_width_cm ? 'Shoulder: ' + p.shoulder_width_cm + ' cm' : null,
  ].filter(Boolean).join('\n');
  const ta = document.createElement('textarea');
  ta.value = lines;
  ta.style.cssText = 'position:fixed;opacity:0';
  document.body.appendChild(ta);
  ta.select();
  document.execCommand('copy');
  ta.remove();
  _setStatus('Measurements copied!');
  setTimeout(() => _setStatus(''), 2000);
};

window.toggleAutoRotate = function() {
  _autoRotate = !_autoRotate;
  controls.autoRotate = _autoRotate;
  controls.autoRotateSpeed = 2.0;
  document.getElementById('btn-spin')?.classList.toggle('active', _autoRotate);
  _saveViewerSettings();
};

window.setCameraPreset = function(preset) {
  if (!bodyMesh) return;
  const box = new THREE.Box3().setFromObject(bodyMesh);
  const size = new THREE.Vector3();
  box.getSize(size);
  const maxDim = Math.max(size.x, size.y, size.z);
  const fov = camera.fov * (Math.PI / 180);
  const dist = maxDim / (2 * Math.tan(fov / 2)) * 1.6;
  const midY = size.y * 0.45;
  let endPos, endTarget = new THREE.Vector3(0, midY, 0);
  switch (preset) {
    case 'front': endPos = new THREE.Vector3(0, midY, dist);      break;
    case 'back':  endPos = new THREE.Vector3(0, midY, -dist);     break;
    case 'left':  endPos = new THREE.Vector3(-dist, midY, 0);     break;
    case 'right': endPos = new THREE.Vector3(dist, midY, 0);      break;
    case 'top':   endPos = new THREE.Vector3(0, dist, 0.01);
                  endTarget = new THREE.Vector3(0, 0, 0);         break;
    default: return;
  }
  _camTransition = {
    startPos: camera.position.clone(), startTarget: controls.target.clone(),
    endPos, endTarget, startTime: performance.now(), duration: 600,
  };
};

window.toggleFullscreen = function() {
  const overlay = document.getElementById('ui-overlay');
  const legend = document.querySelector('.heatmap-legend');
  if (!document.fullscreenElement) {
    document.body.requestFullscreen().catch(() => {});
    if (overlay) overlay.style.display = 'none';
    if (legend) legend.style.display = 'none';
  } else {
    document.exitFullscreen();
    if (overlay) overlay.style.display = '';
    if (legend) legend.style.display = '';
  }
};

// ── Hover info tooltip (V9) ─────────────────────────────────────────────────
const _REGION_FIELDS = {
  chest: ['chest_circumference_cm', 'cm'], waist: ['waist_circumference_cm', 'cm'],
  hip: ['hip_circumference_cm', 'cm'], thigh: ['thigh_circumference_cm', 'cm'],
  calf: ['calf_circumference_cm', 'cm'], arm: ['bicep_circumference_cm', 'cm'],
  neck: ['neck_circumference_cm', 'cm'], shoulder: ['shoulder_width_cm', 'cm'],
  head: ['head_circumference_cm', 'cm'], knee: ['thigh_circumference_cm', 'cm'],
};

function _onMeshHover(event) {
  if (_measureMode || _walkMode) return;
  const tooltip = document.getElementById('hover-tooltip');
  if (!tooltip) return;
  const hit = _getMeshIntersection(event);
  if (!hit) { tooltip.style.display = 'none'; return; }
  const region = getBodyRegion(hit.point);
  const label = region.charAt(0).toUpperCase() + region.slice(1);
  let text = label;
  if (_bodyProfile) {
    const entry = _REGION_FIELDS[region];
    if (entry) {
      const val = _bodyProfile[entry[0]];
      if (val != null) text += ': ' + val + entry[1];
    }
  }
  tooltip.textContent = text;
  tooltip.style.display = 'block';
  tooltip.style.left = (event.clientX + 15) + 'px';
  tooltip.style.top = (event.clientY - 10) + 'px';
}

window.runComparison = async function() {
  const oldId = document.getElementById('compare-old')?.value;
  const newId = document.getElementById('compare-new')?.value;
  if (!oldId || !newId) { _setStatus('Select both meshes to compare'); return; }
  if (window.switchTab) switchTab('analyze');
  await _applyCompareHeatmap(parseInt(oldId), parseInt(newId));
};

window.clearComparison = function() {
  window.setViewMode('solid');
  const statsEl = document.getElementById('compare-stats');
  if (statsEl) { statsEl.style.display = 'none'; statsEl.textContent = ''; }
};

// ── Measure mode ──────────────────────────────────────────────────────────────
window.toggleMeasure = function() {
  _measureMode = !_measureMode;
  const btn = document.getElementById('btn-measure');
  if (btn) btn.classList.toggle('active', _measureMode);
  if (!_measureMode && _measurePoints.length === 1) {
    scene.remove(_measurePoints[0].marker);
    _measurePoints = [];
  }
  _setStatus(_measureMode ? 'Click two points to measure distance' : '');
};

function _showMeasureLabel(p1, p2, distMm) {
  const mid = p1.clone().add(p2).multiplyScalar(0.5);
  const div = document.createElement('div');
  div.style.cssText = 'position:fixed;background:rgba(255,68,68,0.9);color:#fff;padding:2px 7px;border-radius:3px;font-size:11px;pointer-events:none;z-index:60;';
  div.textContent = `${distMm.toFixed(1)} mm`;
  document.getElementById('canvas-container').appendChild(div);
  _measureLabels.push(div);

  function updatePos() {
    if (!div.parentElement) return;
    const projected = mid.clone().project(camera);
    const x = (projected.x * 0.5 + 0.5) * window.innerWidth;
    const y = (-projected.y * 0.5 + 0.5) * window.innerHeight;
    div.style.left = x + 'px';
    div.style.top  = y + 'px';
    requestAnimationFrame(updatePos);
  }
  updatePos();
}

// ── V11: Mesh cross-section helper ───────────────────────────────────────────
function _meshCrossSection(mesh, heightRatio) {
  if (!mesh) return null;
  const box = new THREE.Box3().setFromObject(mesh);
  const size = new THREE.Vector3();
  box.getSize(size);
  const sliceY = box.min.y + size.y * heightRatio;
  const sceneToMm = size.y > 0 ? 1680 / size.y : 1;
  const pts = [];
  mesh.traverse(child => {
    if (!child.isMesh || !child.geometry) return;
    const pos = child.geometry.attributes.position;
    const idx = child.geometry.index;
    const mat = child.matrixWorld;
    const getV = (i) => new THREE.Vector3(pos.getX(i), pos.getY(i), pos.getZ(i)).applyMatrix4(mat);
    const triCount = idx ? idx.count / 3 : pos.count / 3;
    for (let t = 0; t < triCount; t++) {
      const i0 = idx ? idx.getX(t * 3) : t * 3;
      const i1 = idx ? idx.getX(t * 3 + 1) : t * 3 + 1;
      const i2 = idx ? idx.getX(t * 3 + 2) : t * 3 + 2;
      const v0 = getV(i0), v1 = getV(i1), v2 = getV(i2);
      for (const [a, b] of [[v0,v1],[v1,v2],[v2,v0]]) {
        if ((a.y - sliceY) * (b.y - sliceY) < 0) {
          const f = (sliceY - a.y) / (b.y - a.y);
          pts.push(new THREE.Vector3(a.x + f*(b.x-a.x), sliceY, a.z + f*(b.z-a.z)));
        }
      }
    }
  });
  let perim = 0;
  for (let i = 0; i + 1 < pts.length; i += 2) perim += pts[i].distanceTo(pts[i+1]);
  return { circumferenceCm: (perim * sceneToMm) / 10, points: pts, sceneToMm };
}

// ── Cross-section ─────────────────────────────────────────────────────────────
function _updateCrossSection(ratio) {
  if (!bodyMesh) return;
  if (_sectionPlane)   { scene.remove(_sectionPlane);   _sectionPlane   = null; }
  if (_sectionOutline) { scene.remove(_sectionOutline); _sectionOutline = null; }

  const box = new THREE.Box3().setFromObject(bodyMesh);
  const size = new THREE.Vector3();
  box.getSize(size);
  const sliceY = box.min.y + size.y * ratio;

  // Translucent plane
  const planeSize = Math.max(size.x, size.z) * 1.8;
  _sectionPlane = new THREE.Mesh(
    new THREE.PlaneGeometry(planeSize, planeSize),
    new THREE.MeshBasicMaterial({ color: 0x4a9eff, transparent: true, opacity: 0.12, side: THREE.DoubleSide })
  );
  _sectionPlane.rotation.x = -Math.PI / 2;
  _sectionPlane.position.y = sliceY;
  scene.add(_sectionPlane);

  // Compute cross-section edges
  const crossPoints = [];
  bodyMesh.traverse(child => {
    if (!child.isMesh || !child.geometry) return;
    const geo  = child.geometry;
    const pos  = geo.attributes.position;
    const idx  = geo.index;
    const mat  = child.matrixWorld;
    const getV = (i) => new THREE.Vector3(pos.getX(i), pos.getY(i), pos.getZ(i)).applyMatrix4(mat);
    const triCount = idx ? idx.count / 3 : pos.count / 3;
    for (let t = 0; t < triCount; t++) {
      const i0 = idx ? idx.getX(t * 3) : t * 3;
      const i1 = idx ? idx.getX(t * 3 + 1) : t * 3 + 1;
      const i2 = idx ? idx.getX(t * 3 + 2) : t * 3 + 2;
      const v0 = getV(i0), v1 = getV(i1), v2 = getV(i2);
      const edges = [[v0, v1], [v1, v2], [v2, v0]];
      for (const [a, b] of edges) {
        if ((a.y - sliceY) * (b.y - sliceY) < 0) {
          const tVal = (sliceY - a.y) / (b.y - a.y);
          crossPoints.push(new THREE.Vector3(
            a.x + tVal * (b.x - a.x), sliceY, a.z + tVal * (b.z - a.z)
          ));
        }
      }
    }
  });

  if (crossPoints.length >= 2) {
    _sectionOutline = new THREE.LineSegments(
      new THREE.BufferGeometry().setFromPoints(crossPoints),
      new THREE.LineBasicMaterial({ color: 0x4a9eff })
    );
    scene.add(_sectionOutline);

    let perimeter = 0;
    for (let i = 0; i + 1 < crossPoints.length; i += 2) {
      perimeter += crossPoints[i].distanceTo(crossPoints[i + 1]);
    }
    // Convert scene units → mm
    const sceneToMm = size.y > 0 ? 1680 / size.y : 1;
    const perimMm   = perimeter * sceneToMm;
    const heightMm  = (sliceY - box.min.y) * sceneToMm;
    const statsEl = document.getElementById('section-stats');
    if (statsEl) {
      statsEl.textContent = `H: ${heightMm.toFixed(0)}mm | Circ ≈ ${perimMm.toFixed(0)}mm (${(perimMm / 10).toFixed(1)}cm)`;
    }
  }
}

window.quickSection = function(region) {
  const HEIGHTS = { chest: 64, waist: 54, hip: 45, thigh: 34 };
  const pct = HEIGHTS[region];
  if (pct == null) return;
  const slider = document.getElementById('section-height');
  if (slider) {
    slider.value = pct;
    document.getElementById('section-height-val').textContent = pct;
  }
  _updateCrossSection(pct / 100);
};

// ── V12: Sorted cross-section for ring rendering ────────────────────────────
function _sortedCrossSection(mesh, heightRatio) {
  const data = _meshCrossSection(mesh, heightRatio);
  if (!data || data.points.length < 4) return null;
  // Compute centroid
  const cx = data.points.reduce((s, p) => s + p.x, 0) / data.points.length;
  const cz = data.points.reduce((s, p) => s + p.z, 0) / data.points.length;
  // Sort by angle around centroid
  data.points.sort((a, b) => Math.atan2(a.z - cz, a.x - cx) - Math.atan2(b.z - cz, b.x - cx));
  // Close the loop
  data.points.push(data.points[0].clone());
  data.centroidX = cx;
  data.centroidZ = cz;
  return data;
}

// ── V13: Rich cross-section (width, depth, area, roundness) ─────────────────
function _richCrossSection(mesh, heightRatio) {
  const data = _sortedCrossSection(mesh, heightRatio);
  if (!data) return null;
  const sm = data.sceneToMm || 1;            // scene units → mm
  const pts = data.points;
  const xs  = pts.map(p => p.x);
  const zs  = pts.map(p => p.z);
  const widthCm  = (Math.max(...xs) - Math.min(...xs)) * sm / 10;
  const depthCm  = (Math.max(...zs) - Math.min(...zs)) * sm / 10;
  // Shoelace area (scene units²) → cm²
  let area = 0;
  for (let i = 0; i < pts.length - 1; i++) {
    area += pts[i].x * pts[i + 1].z - pts[i + 1].x * pts[i].z;
  }
  const areaCm2 = Math.abs(area) * 0.5 * (sm / 10) ** 2;
  // ISO circularity / roundness: 1.0 = perfect circle, lower = flatter
  const circ      = data.circumferenceCm;
  const roundness = circ > 0 ? (4 * Math.PI * areaCm2) / (circ * circ) : 0;
  return { ...data, widthCm, depthCm, areaCm2, roundness };
}

// ── V14: Growth slice computation ───────────────────────────────────────────
function _computeGrowthSlices(currMesh, ghostMesh, numSlices) {
  const slices = [];
  for (let i = 0; i < numSlices; i++) {
    const ratio = 0.10 + (i / (numSlices - 1)) * 0.75;
    const curr = _meshCrossSection(currMesh, ratio);
    const prev = ghostMesh ? _meshCrossSection(ghostMesh, ratio) : null;
    slices.push({
      ratio,
      currCirc: curr ? curr.circumferenceCm : 0,
      prevCirc: prev ? prev.circumferenceCm : 0,
      delta: curr && prev ? curr.circumferenceCm - prev.circumferenceCm : 0,
    });
  }
  return slices;
}

// ── V15: Fast mesh helpers ────────────────────────────────────────────────────
function _computeProfileFast(mesh, numBuckets) {
  if (!mesh) return null;
  const box = new THREE.Box3().setFromObject(mesh);
  const minY = box.min.y, rangeY = box.max.y - box.min.y;
  if (rangeY < 1) return null;
  const buckets = Array.from({ length: numBuckets }, () =>
    ({ minX: Infinity, maxX: -Infinity, minZ: Infinity, maxZ: -Infinity }));
  const v = new THREE.Vector3();
  mesh.traverse(child => {
    if (!child.isMesh || !child.geometry) return;
    const pos = child.geometry.attributes.position;
    for (let i = 0; i < pos.count; i++) {
      v.set(pos.getX(i), pos.getY(i), pos.getZ(i)).applyMatrix4(child.matrixWorld);
      const bin = Math.min(numBuckets - 1, Math.floor((v.y - minY) / rangeY * numBuckets));
      if (bin >= 0) {
        buckets[bin].minX = Math.min(buckets[bin].minX, v.x);
        buckets[bin].maxX = Math.max(buckets[bin].maxX, v.x);
        buckets[bin].minZ = Math.min(buckets[bin].minZ, v.z);
        buckets[bin].maxZ = Math.max(buckets[bin].maxZ, v.z);
      }
    }
  });
  // Fill empty buckets by borrowing from neighbors
  for (let i = 1; i < numBuckets; i++) {
    if (!isFinite(buckets[i].maxX)) buckets[i] = { ...buckets[i - 1] };
  }
  return { buckets, box };
}

function _computeCentroidAxis(mesh, numLevels) {
  if (!mesh) return null;
  const box = new THREE.Box3().setFromObject(mesh);
  const minY = box.min.y, rangeY = box.max.y - box.min.y;
  if (rangeY < 1) return null;
  const bins = Array.from({ length: numLevels }, () => ({ sumX: 0, sumZ: 0, count: 0 }));
  const v = new THREE.Vector3();
  mesh.traverse(child => {
    if (!child.isMesh || !child.geometry) return;
    const pos = child.geometry.attributes.position;
    for (let i = 0; i < pos.count; i++) {
      v.set(pos.getX(i), pos.getY(i), pos.getZ(i)).applyMatrix4(child.matrixWorld);
      const bin = Math.min(numLevels - 1, Math.floor((v.y - minY) / rangeY * numLevels));
      if (bin >= 0) { bins[bin].sumX += v.x; bins[bin].sumZ += v.z; bins[bin].count++; }
    }
  });
  const sceneToMm = rangeY > 0 ? 1680 / rangeY : 1;
  return bins.map((b, i) => ({
    y: minY + (i + 0.5) * rangeY / numLevels,
    cx: b.count > 0 ? b.sumX / b.count : 0,
    cz: b.count > 0 ? b.sumZ / b.count : 0,
    devMm: b.count > 0 ? Math.sqrt((b.sumX / b.count) ** 2 + (b.sumZ / b.count) ** 2) * sceneToMm : 0,
  }));
}

// ── V11: Scan Analysis ───────────────────────────────────────────────────────
const _ANALYSIS_LANDMARKS = { Shoulder: 0.76, Chest: 0.64, Waist: 0.54, Hip: 0.45, Thigh: 0.34 };

function _computeAnalysis() {
  if (!bodyMesh) return;
  const el = document.getElementById('analysis-content');
  if (!el) return;
  let html = '';
  const curr      = {};
  const currRich  = {};
  const ghostCurr = {};
  _ghostRich      = {};

  // Mesh-derived circumferences
  html += '<div style="color:#4a9eff;font-size:10px;text-transform:uppercase;letter-spacing:0.05em;margin-bottom:4px;">From 3D Mesh</div>';
  for (const [name, ratio] of Object.entries(_ANALYSIS_LANDMARKS)) {
    const data = _richCrossSection(bodyMesh, ratio);
    curr[name]     = data ? data.circumferenceCm : null;
    currRich[name] = data;
    html += `<div style="display:flex;justify-content:space-between;"><span style="color:#94a3b8;">${name}</span><strong>${curr[name] ? curr[name].toFixed(1) : '\u2014'}</strong><span style="color:#666;">cm</span></div>`;
  }

  // Ghost comparison deltas
  if (_ghostMesh) {
    html += '<div style="margin-top:6px;color:#44ff88;font-size:10px;text-transform:uppercase;letter-spacing:0.05em;margin-bottom:4px;">vs Previous Scan</div>';
    for (const [name, ratio] of Object.entries(_ANALYSIS_LANDMARKS)) {
      const prev = _richCrossSection(_ghostMesh, ratio);
      const prevCm = prev ? prev.circumferenceCm : null;
      ghostCurr[name] = prevCm;
      _ghostRich[name] = prev;
      if (prevCm && curr[name]) {
        const delta = curr[name] - prevCm;
        const color = delta > 0.5 ? '#22c55e' : delta < -0.5 ? '#ef4444' : '#94a3b8';
        const sign = delta > 0 ? '+' : '';
        html += `<div style="display:flex;justify-content:space-between;"><span style="color:#94a3b8;">${name}</span><span style="color:${color};font-weight:bold;">${sign}${delta.toFixed(1)}cm</span></div>`;
      }
    }
  }

  // Extensible sections
  html += _computeWidthDepthHtml(currRich);
  html += _computeVolumeZonesHtml(currRich, Object.keys(ghostCurr).length > 0 ? _ghostRich : null);
  html += _computeSymmetryHtml();
  html += _computeRatiosHtml(curr);

  el.innerHTML = html;
  _redrawRadar(curr, Object.keys(ghostCurr).length > 0 ? ghostCurr : null);
}

function _computeSymmetryHtml() {
  if (!bodyMesh) return '';
  let html = '<div style="margin-top:6px;color:#4a9eff;font-size:10px;text-transform:uppercase;letter-spacing:0.05em;margin-bottom:4px;">Symmetry L/R</div>';
  for (const [name, ratio] of Object.entries(_ANALYSIS_LANDMARKS)) {
    const data = _meshCrossSection(bodyMesh, ratio);
    if (!data || data.points.length < 4) continue;
    let leftMax = 0, rightMax = 0;
    for (const pt of data.points) {
      if (pt.x < 0) leftMax = Math.max(leftMax, -pt.x);
      else rightMax = Math.max(rightMax, pt.x);
    }
    const wider = Math.max(leftMax, rightMax);
    const pct = wider > 0 ? (1 - Math.abs(leftMax - rightMax) / wider) * 100 : 100;
    const color = pct >= 95 ? '#22c55e' : pct >= 90 ? '#f59e0b' : '#ef4444';
    html += `<div style="display:flex;justify-content:space-between;"><span style="color:#94a3b8;">${name}</span><span style="color:${color};font-weight:bold;">${pct.toFixed(0)}%</span></div>`;
  }
  return html;
}
function _computeBarChartHtml(measurements) {
  if (!measurements) return '';
  const entries = Object.entries(measurements).filter(([_, v]) => v != null);
  if (entries.length === 0) return '';
  const maxVal = Math.max(...entries.map(([_, v]) => v));
  let html = '<div style="margin-top:6px;">';
  for (const [name, val] of entries) {
    const pct = maxVal > 0 ? (val / maxVal) * 100 : 0;
    html += `<div style="display:flex;align-items:center;margin-bottom:3px;">`;
    html += `<span style="color:#94a3b8;width:55px;font-size:9px;flex-shrink:0;">${name}</span>`;
    html += `<div style="flex:1;height:8px;background:rgba(74,158,255,0.1);border-radius:4px;overflow:hidden;">`;
    html += `<div style="width:${pct.toFixed(0)}%;height:100%;background:#4a9eff;border-radius:4px;"></div>`;
    html += `</div>`;
    html += `<span style="color:#4a9eff;width:42px;text-align:right;font-size:9px;flex-shrink:0;">${val.toFixed(1)}</span>`;
    html += `</div>`;
  }
  html += '</div>';
  return html;
}

function _computeVolumeZonesHtml(richMap, ghostRichMap) {
  if (!richMap || !richMap.Shoulder) return '';
  const H_CM = 168;  // body height in cm
  // Define zones: [name, bottom_ratio, top_ratio, area_landmarks...]
  const zones = [
    { name: 'Legs',    h: 0.34, area: richMap.Thigh?.areaCm2 || 0 },
    { name: 'Thighs',  h: 0.11, area: ((richMap.Thigh?.areaCm2||0) + (richMap.Hip?.areaCm2||0)) / 2 },
    { name: 'Pelvis',  h: 0.09, area: ((richMap.Hip?.areaCm2||0) + (richMap.Waist?.areaCm2||0)) / 2 },
    { name: 'Torso',   h: 0.10, area: ((richMap.Waist?.areaCm2||0) + (richMap.Chest?.areaCm2||0)) / 2 },
    { name: 'Chest',   h: 0.12, area: ((richMap.Chest?.areaCm2||0) + (richMap.Shoulder?.areaCm2||0)) / 2 },
    { name: 'Upper',   h: 0.24, area: richMap.Shoulder?.areaCm2 || 0 },
  ];
  zones.forEach(z => { z.vol = z.area * z.h * H_CM; });
  const totalVol = zones.reduce((s, z) => s + z.vol, 0);
  if (totalVol < 1) return '';

  // Ghost volumes
  if (ghostRichMap && ghostRichMap.Shoulder) {
    const gz = [
      { area: ghostRichMap.Thigh?.areaCm2 || 0 },
      { area: ((ghostRichMap.Thigh?.areaCm2||0) + (ghostRichMap.Hip?.areaCm2||0)) / 2 },
      { area: ((ghostRichMap.Hip?.areaCm2||0) + (ghostRichMap.Waist?.areaCm2||0)) / 2 },
      { area: ((ghostRichMap.Waist?.areaCm2||0) + (ghostRichMap.Chest?.areaCm2||0)) / 2 },
      { area: ((ghostRichMap.Chest?.areaCm2||0) + (ghostRichMap.Shoulder?.areaCm2||0)) / 2 },
      { area: ghostRichMap.Shoulder?.areaCm2 || 0 },
    ];
    zones.forEach((z, i) => { z.ghostVol = gz[i].area * z.h * H_CM; });
  }

  let html = '<div style="margin-top:6px;color:#4a9eff;font-size:10px;text-transform:uppercase;letter-spacing:0.05em;margin-bottom:4px;">Volume Zones</div>';
  for (const z of zones) {
    const pct = (z.vol / totalVol * 100).toFixed(0);
    let delta = '';
    if (z.ghostVol != null) {
      const d = z.vol - z.ghostVol;
      const c = d > 50 ? '#22c55e' : d < -50 ? '#ef4444' : '#94a3b8';
      delta = ` <span style="color:${c};font-size:9px;">${d > 0 ? '+' : ''}${(d / 1000).toFixed(2)}L</span>`;
    }
    html += `<div style="display:flex;justify-content:space-between;align-items:center;">`;
    html += `<span style="color:#94a3b8;">${z.name}</span>`;
    html += `<span style="color:#e0e0e0;font-size:10px;">${pct}%${delta}</span>`;
    html += `</div>`;
  }
  return html;
}

function _computeRatiosHtml(measurements) {
  if (!measurements || !measurements.Waist) return '';
  let html = '<div style="margin-top:6px;color:#4a9eff;font-size:10px;text-transform:uppercase;letter-spacing:0.05em;margin-bottom:4px;">Body Ratios</div>';
  if (measurements.Shoulder && measurements.Waist) {
    const r = measurements.Shoulder / measurements.Waist;
    const color = r >= 1.30 ? '#22c55e' : r >= 1.15 ? '#f59e0b' : '#94a3b8';
    html += `<div style="display:flex;justify-content:space-between;"><span style="color:#94a3b8;">Shoulder/Waist</span><span style="color:${color};font-weight:bold;">${r.toFixed(2)}</span></div>`;
  }
  if (measurements.Waist && measurements.Hip) {
    const r = measurements.Waist / measurements.Hip;
    const color = r <= 0.90 ? '#22c55e' : r <= 1.0 ? '#f59e0b' : '#ef4444';
    html += `<div style="display:flex;justify-content:space-between;"><span style="color:#94a3b8;">Waist/Hip</span><span style="color:${color};font-weight:bold;">${r.toFixed(2)}</span></div>`;
  }
  return html;
}

// ── V13: Radar chart ────────────────────────────────────────────────────────
function _drawRadarChart(canvas, curr, ghost) {
  const ctx = canvas.getContext('2d');
  const W = canvas.width, H = canvas.height;
  const cx = W / 2, cy = H / 2, R = W * 0.34;
  ctx.clearRect(0, 0, W, H);

  const names  = Object.keys(_ANALYSIS_LANDMARKS);
  const N      = names.length;
  const angles = names.map((_, i) => (i * 2 * Math.PI / N) - Math.PI / 2);
  const vals   = names.map(k => curr[k] || 0);
  const maxVal = Math.max(...vals, 1);

  // Grid circles
  ctx.lineWidth = 0.5;
  for (let g = 1; g <= 3; g++) {
    ctx.beginPath();
    ctx.arc(cx, cy, R * g / 3, 0, Math.PI * 2);
    ctx.strokeStyle = 'rgba(74,158,255,0.15)';
    ctx.stroke();
  }
  // Axes
  for (let i = 0; i < N; i++) {
    ctx.beginPath();
    ctx.moveTo(cx, cy);
    ctx.lineTo(cx + R * Math.cos(angles[i]), cy + R * Math.sin(angles[i]));
    ctx.strokeStyle = 'rgba(74,158,255,0.25)';
    ctx.stroke();
  }

  // Ghost polygon
  if (ghost) {
    ctx.beginPath();
    for (let i = 0; i < N; i++) {
      const r = R * (ghost[names[i]] || 0) / maxVal;
      const x = cx + r * Math.cos(angles[i]);
      const y = cy + r * Math.sin(angles[i]);
      i === 0 ? ctx.moveTo(x, y) : ctx.lineTo(x, y);
    }
    ctx.closePath();
    ctx.fillStyle   = 'rgba(68,255,136,0.10)';
    ctx.fill();
    ctx.strokeStyle = '#44ff88';
    ctx.lineWidth   = 1;
    ctx.stroke();
  }

  // Current polygon
  ctx.beginPath();
  for (let i = 0; i < N; i++) {
    const r = R * vals[i] / maxVal;
    const x = cx + r * Math.cos(angles[i]);
    const y = cy + r * Math.sin(angles[i]);
    i === 0 ? ctx.moveTo(x, y) : ctx.lineTo(x, y);
  }
  ctx.closePath();
  ctx.fillStyle   = 'rgba(74,158,255,0.18)';
  ctx.fill();
  ctx.strokeStyle = '#4a9eff';
  ctx.lineWidth   = 1.5;
  ctx.stroke();

  // Labels: axis name + value
  ctx.textAlign    = 'center';
  ctx.textBaseline = 'middle';
  for (let i = 0; i < N; i++) {
    const lx = cx + (R + 22) * Math.cos(angles[i]);
    const ly = cy + (R + 22) * Math.sin(angles[i]);
    ctx.font      = '9px sans-serif';
    ctx.fillStyle = '#94a3b8';
    ctx.fillText(names[i], lx, ly - 5);
    ctx.font      = 'bold 9px sans-serif';
    ctx.fillStyle = '#4a9eff';
    ctx.fillText((vals[i] > 0 ? vals[i].toFixed(0) : '\u2014') + 'cm', lx, ly + 5);
  }
}

function _redrawRadar(curr, ghost) {
  const canvas = document.getElementById('radar-canvas');
  if (!canvas) return;
  const hasData = Object.values(curr).some(v => v != null);
  if (!hasData) { canvas.style.display = 'none'; return; }
  canvas.style.display = 'block';
  _drawRadarChart(canvas, curr, ghost);
}

function _computeWidthDepthHtml(richMap) {
  if (!richMap) return '';
  let html = '<div style="margin-top:6px;color:#4a9eff;font-size:10px;text-transform:uppercase;letter-spacing:0.05em;margin-bottom:4px;">Width \u00d7 Depth</div>';
  for (const [name, data] of Object.entries(richMap)) {
    if (!data) continue;
    const w = data.widthCm.toFixed(1);
    const d = data.depthCm.toFixed(1);
    const r = data.depthCm > 0 ? (data.widthCm / data.depthCm).toFixed(2) : '\u2014';
    html += `<div style="display:flex;justify-content:space-between;align-items:baseline;">`;
    html += `<span style="color:#94a3b8;">${name}</span>`;
    html += `<span style="color:#e0e0e0;font-size:10px;">${w}\u00d7${d}<span style="color:#555;font-size:9px;"> (${r})</span></span>`;
    html += `</div>`;
  }
  return html;
}

// ── V14: Growth heatmap ─────────────────────────────────────────────────────
function _growthToRGB(delta, maxDelta) {
  const dz = 0.3;  // dead zone in cm (measurement noise)
  const absD = Math.abs(delta);
  if (absD < dz) return [0.83, 0.83, 0.83];
  const t = Math.min(1, (absD - dz) / Math.max(maxDelta - dz, 0.1));
  if (delta > 0) return [0.83 + 0.11 * t, 0.83 - 0.56 * t, 0.83 - 0.56 * t];
  return [0.83 - 0.60 * t, 0.83 - 0.32 * t, 0.83 + 0.13 * t];
}

function _applyGrowthColors() {
  if (!bodyMesh || !_ghostMesh) return;
  const slices = _computeGrowthSlices(bodyMesh, _ghostMesh, 30);
  const maxDelta = Math.max(...slices.map(s => Math.abs(s.delta)), 0.5);
  const box = new THREE.Box3().setFromObject(bodyMesh);
  const minY = box.min.y, rangeY = box.max.y - box.min.y;

  bodyMesh.traverse(child => {
    if (!child.isMesh || !child.geometry) return;
    const pos = child.geometry.attributes.position;
    const colors = new Float32Array(pos.count * 3);
    const v = new THREE.Vector3();

    for (let i = 0; i < pos.count; i++) {
      v.set(pos.getX(i), pos.getY(i), pos.getZ(i)).applyMatrix4(child.matrixWorld);
      const hRatio = rangeY > 0 ? (v.y - minY) / rangeY : 0.5;

      // Interpolate delta from nearest slices
      let delta = 0;
      if (hRatio <= slices[0].ratio) delta = slices[0].delta;
      else if (hRatio >= slices[slices.length - 1].ratio) delta = slices[slices.length - 1].delta;
      else {
        for (let s = 0; s < slices.length - 1; s++) {
          if (hRatio <= slices[s + 1].ratio) {
            const f = (hRatio - slices[s].ratio) / (slices[s + 1].ratio - slices[s].ratio);
            delta = slices[s].delta + f * (slices[s + 1].delta - slices[s].delta);
            break;
          }
        }
      }

      const rgb = _growthToRGB(delta, maxDelta);
      colors[i * 3] = rgb[0]; colors[i * 3 + 1] = rgb[1]; colors[i * 3 + 2] = rgb[2];
    }

    child.geometry.setAttribute('color', new THREE.Float32BufferAttribute(colors, 3));
    if (!child._preGrowthMat) child._preGrowthMat = child.material;
    child.material = new THREE.MeshStandardMaterial({
      vertexColors: true, roughness: 0.6, metalness: 0.1
    });
  });
}

function _removeGrowthColors() {
  if (!bodyMesh) return;
  bodyMesh.traverse(child => {
    if (child.isMesh && child._preGrowthMat) {
      child.material = child._preGrowthMat;
      delete child._preGrowthMat;
      if (child.geometry.attributes.color) child.geometry.deleteAttribute('color');
      // Maintain slice transparency if active
      if (_sliceMode) {
        child.material.transparent = true;
        child.material.opacity = 0.15;
        child.material.needsUpdate = true;
      }
    }
  });
}

window.toggleGrowthMap = function() {
  if (!_ghostMesh) return;
  _growthMode = !_growthMode;
  if (_growthMode) {
    _applyGrowthColors();
    const legend = document.getElementById('growth-legend');
    if (legend) legend.style.display = 'block';
  } else {
    _removeGrowthColors();
    const legend = document.getElementById('growth-legend');
    if (legend) legend.style.display = 'none';
  }
  const btn = document.getElementById('btn-growth');
  if (btn) btn.classList.toggle('active', _growthMode);
};

// ── V14: Slice explorer ─────────────────────────────────────────────────────
function _buildSliceView() {
  if (_sliceGroup) scene.remove(_sliceGroup);
  _sliceGroup = new THREE.Group();
  if (!bodyMesh) return;

  const numSlices = 12;
  const box = new THREE.Box3().setFromObject(bodyMesh);
  const bodyH = box.max.y - box.min.y;

  for (let i = 0; i < numSlices; i++) {
    const ratio = 0.10 + i * (0.72 / (numSlices - 1));
    const data = _sortedCrossSection(bodyMesh, ratio);
    if (!data || data.points.length < 4) continue;

    // Determine fill color based on growth delta (with ghost)
    let fillColor = 0x4a9eff;
    if (_ghostMesh) {
      const gCirc = _meshCrossSection(_ghostMesh, ratio);
      if (gCirc) {
        const delta = data.circumferenceCm - gCirc.circumferenceCm;
        if (delta > 0.5) fillColor = 0xef4444;
        else if (delta < -0.5) fillColor = 0x3b82f6;
        else fillColor = 0x999999;
      }
    }

    // Build filled polygon from cross-section
    const shape = new THREE.Shape();
    shape.moveTo(data.points[0].x, data.points[0].z);
    for (let j = 1; j < data.points.length; j++) {
      shape.lineTo(data.points[j].x, data.points[j].z);
    }

    const origY = box.min.y + bodyH * ratio;
    const spreadY = box.min.y + (origY - box.min.y) * 1.6;

    const fill = new THREE.Mesh(
      new THREE.ShapeGeometry(shape),
      new THREE.MeshBasicMaterial({ color: fillColor, transparent: true, opacity: 0.25, side: THREE.DoubleSide })
    );
    fill.rotation.x = -Math.PI / 2;
    fill.position.y = spreadY;
    _sliceGroup.add(fill);

    // Outline
    const outPts = data.points.map(p => new THREE.Vector3(p.x, 0, p.z));
    const outline = new THREE.LineLoop(
      new THREE.BufferGeometry().setFromPoints(outPts),
      new THREE.LineBasicMaterial({ color: 0x4a9eff })
    );
    outline.rotation.x = -Math.PI / 2;
    outline.position.y = spreadY;
    _sliceGroup.add(outline);

    // Ghost outline if loaded
    if (_ghostMesh) {
      const gData = _sortedCrossSection(_ghostMesh, ratio);
      if (gData && gData.points.length >= 4) {
        const gPts = gData.points.map(p => new THREE.Vector3(p.x, 0, p.z));
        const gOutline = new THREE.LineLoop(
          new THREE.BufferGeometry().setFromPoints(gPts),
          new THREE.LineBasicMaterial({ color: 0x44ff88, transparent: true, opacity: 0.6 })
        );
        gOutline.rotation.x = -Math.PI / 2;
        gOutline.position.y = spreadY;
        _sliceGroup.add(gOutline);
      }
    }
  }

  scene.add(_sliceGroup);
}

function _clearSliceView() {
  if (_sliceGroup) { scene.remove(_sliceGroup); _sliceGroup = null; }
}

window.toggleSliceView = function() {
  _sliceMode = !_sliceMode;
  if (_sliceMode) {
    _buildSliceView();
    if (bodyMesh) bodyMesh.traverse(c => {
      if (c.isMesh && c.material) {
        c.material.transparent = true;
        c.material.opacity = 0.15;
        c.material.needsUpdate = true;
      }
    });
  } else {
    _clearSliceView();
    if (bodyMesh) bodyMesh.traverse(c => {
      if (c.isMesh && c.material) {
        c.material.transparent = false;
        c.material.opacity = 1.0;
        c.material.needsUpdate = true;
      }
    });
  }
  const btn = document.getElementById('btn-slices');
  if (btn) btn.classList.toggle('active', _sliceMode);
};

function _resetVisModes() {
  if (_axisVisible) {
    _axisVisible = false;
    if (_axisGroup) { scene.remove(_axisGroup); _axisGroup = null; }
    document.getElementById('btn-axis')?.classList.remove('active');
  }
  if (_profileVisible) {
    _profileVisible = false;
    const pc = document.getElementById('profile-canvas'); if (pc) pc.style.display = 'none';
    document.getElementById('btn-profile')?.classList.remove('active');
  }
  if (_growthMode) {
    _growthMode = false; _removeGrowthColors();
    const gl = document.getElementById('growth-legend'); if (gl) gl.style.display = 'none';
    const gb = document.getElementById('btn-growth'); if (gb) gb.classList.remove('active');
  }
  if (_sliceMode) {
    _sliceMode = false; _clearSliceView();
    const sb = document.getElementById('btn-slices'); if (sb) sb.classList.remove('active');
    if (bodyMesh) bodyMesh.traverse(c => {
      if (c.isMesh && c.material) { c.material.transparent = false; c.material.opacity = 1; c.material.needsUpdate = true; }
    });
  }
}

// ── V15: Silhouette profile panel ────────────────────────────────────────────
function _drawSilhouetteProfile(canvas, currData, ghostData) {
  const ctx = canvas.getContext('2d');
  const W = canvas.width, H = canvas.height;
  ctx.clearRect(0, 0, W, H);
  ctx.fillStyle = 'rgba(22,33,62,0.92)';
  ctx.fillRect(0, 0, W, H);

  const N = currData.buckets.length;
  const plotTop = 18, plotH = H - 24, labelW = 26;
  const colW = (W - labelW - 4) / 2;
  const frontCx = labelW + colW / 2;
  const sideCx  = labelW + colW + 4 + colW / 2;

  // Headers
  ctx.font = 'bold 8px sans-serif'; ctx.textAlign = 'center'; ctx.fillStyle = '#4a9eff';
  ctx.fillText('FRONT', frontCx, 10);
  ctx.fillText('SIDE', sideCx, 10);
  ctx.strokeStyle = 'rgba(74,158,255,0.2)'; ctx.lineWidth = 0.5;
  ctx.beginPath(); ctx.moveTo(labelW + colW + 2, 12); ctx.lineTo(labelW + colW + 2, H - 4); ctx.stroke();

  // Find max extents for normalization
  const maxHalfW = Math.max(...currData.buckets.map(b => Math.max(Math.abs(b.maxX), Math.abs(b.minX))), 1);
  const maxHalfD = Math.max(...currData.buckets.map(b => Math.max(Math.abs(b.maxZ), Math.abs(b.minZ))), 1);

  function drawOutline(data, cx, getRight, getLeft, isGhost) {
    const buckets = data.buckets;
    const N2 = buckets.length;
    const scale = cx === frontCx ? colW * 0.46 / maxHalfW : colW * 0.46 / maxHalfD;
    ctx.beginPath();
    // Right edge top→bottom
    for (let i = N2 - 1; i >= 0; i--) {
      const y = plotTop + (1 - i / (N2 - 1)) * plotH;
      ctx.lineTo(cx + getRight(buckets[i]) * scale, y);
    }
    // Left edge bottom→top
    for (let i = 0; i < N2; i++) {
      const y = plotTop + (1 - i / (N2 - 1)) * plotH;
      ctx.lineTo(cx + getLeft(buckets[i]) * scale, y);
    }
    ctx.closePath();
    ctx.fillStyle = isGhost ? 'rgba(68,255,136,0.08)' : 'rgba(74,158,255,0.12)';
    ctx.fill();
    ctx.strokeStyle = isGhost ? 'rgba(68,255,136,0.7)' : '#4a9eff';
    ctx.lineWidth = isGhost ? 0.8 : 1.2;
    ctx.stroke();
  }

  if (ghostData) {
    drawOutline(ghostData, frontCx, b => b.maxX, b => b.minX, true);
    drawOutline(ghostData, sideCx, b => b.maxZ, b => b.minZ, true);
  }
  drawOutline(currData, frontCx, b => b.maxX, b => b.minX, false);
  drawOutline(currData, sideCx, b => b.maxZ, b => b.minZ, false);

  // Landmark height markers
  const NAMES = Object.keys(_ANALYSIS_LANDMARKS);
  const RATIOS = Object.values(_ANALYSIS_LANDMARKS);
  ctx.font = '7px sans-serif'; ctx.textAlign = 'right'; ctx.lineWidth = 0.4;
  for (let li = 0; li < NAMES.length; li++) {
    const y = plotTop + (1 - RATIOS[li]) * plotH;
    ctx.fillStyle = '#555'; ctx.strokeStyle = 'rgba(74,158,255,0.2)';
    ctx.beginPath(); ctx.moveTo(labelW, y); ctx.lineTo(W, y); ctx.stroke();
    ctx.fillStyle = '#94a3b8';
    ctx.fillText(NAMES[li].slice(0, 3), labelW - 1, y + 3);
  }
}

window.toggleProfile = function() {
  _profileVisible = !_profileVisible;
  let canvas = document.getElementById('profile-canvas');
  if (!canvas) return;
  canvas.style.display = _profileVisible ? 'block' : 'none';
  const btn = document.getElementById('btn-profile');
  if (btn) btn.classList.toggle('active', _profileVisible);
  if (_profileVisible) _refreshProfile();
};

function _refreshProfile() {
  if (!_profileVisible || !bodyMesh) return;
  const canvas = document.getElementById('profile-canvas');
  if (!canvas) return;
  const curr  = _computeProfileFast(bodyMesh, 120);
  const ghost = _ghostMesh ? _computeProfileFast(_ghostMesh, 120) : null;
  if (curr) _drawSilhouetteProfile(canvas, curr, ghost);
}

// ── V15: Posture axis ────────────────────────────────────────────────────────
function _buildPostureAxis() {
  if (_axisGroup) { scene.remove(_axisGroup); _axisGroup = null; }
  if (!bodyMesh) return;

  _axisGroup = new THREE.Group();
  const NUM = 20;
  const centroids = _computeCentroidAxis(bodyMesh, NUM);
  if (!centroids) return;

  const points = centroids.map(c => new THREE.Vector3(c.cx, c.y, c.cz));
  const colorArr = new Float32Array(NUM * 3);
  centroids.forEach((c, i) => {
    const t = Math.min(1, c.devMm / 20);  // 0=straight, 1=20mm+ deviation
    colorArr[i * 3]     = 0.3 + 0.7 * t;  // R: low→high
    colorArr[i * 3 + 1] = 0.9 - 0.7 * t;  // G: high→low
    colorArr[i * 3 + 2] = 0.3 * (1 - t);  // B: fades
  });
  const lineGeo = new THREE.BufferGeometry().setFromPoints(points);
  lineGeo.setAttribute('color', new THREE.Float32BufferAttribute(colorArr, 3));
  _axisGroup.add(new THREE.Line(lineGeo, new THREE.LineBasicMaterial({ vertexColors: true })));

  // Sphere at each centroid (colored same as line)
  centroids.forEach((c, i) => {
    const t = Math.min(1, c.devMm / 20);
    const color = new THREE.Color(0.3 + 0.7 * t, 0.9 - 0.7 * t, 0.3 * (1 - t));
    const sphere = new THREE.Mesh(
      new THREE.SphereGeometry(2, 6, 4),
      new THREE.MeshBasicMaterial({ color })
    );
    sphere.position.set(c.cx, c.y, c.cz);
    _axisGroup.add(sphere);
  });

  // Ghost axis if loaded
  if (_ghostMesh) {
    const gCentroids = _computeCentroidAxis(_ghostMesh, NUM);
    if (gCentroids) {
      const gPoints = gCentroids.map(c => new THREE.Vector3(c.cx, c.y, c.cz));
      const gGeo = new THREE.BufferGeometry().setFromPoints(gPoints);
      _axisGroup.add(new THREE.Line(gGeo, new THREE.LineBasicMaterial({ color: 0x44ff88, transparent: true, opacity: 0.5 })));
    }
  }

  _axisGroup.visible = _axisVisible;
  scene.add(_axisGroup);
}

window.togglePostureAxis = function() {
  _axisVisible = !_axisVisible;
  if (_axisVisible && !_axisGroup) _buildPostureAxis();
  if (_axisGroup) _axisGroup.visible = _axisVisible;
  const btn = document.getElementById('btn-axis');
  if (btn) btn.classList.toggle('active', _axisVisible);
};

// ── V12: Measurement rings ──────────────────────────────────────────────────
function _buildRings() {
  if (_ringGroup) { scene.remove(_ringGroup); _ringGroup = null; }
  _clearRingLabels();
  if (!bodyMesh) return;
  _ringGroup = new THREE.Group();
  _ringGroup.visible = _ringsVisible;

  for (const [name, ratio] of Object.entries(_ANALYSIS_LANDMARKS)) {
    const data = _sortedCrossSection(bodyMesh, ratio);
    if (!data) continue;
    const geom = new THREE.BufferGeometry().setFromPoints(data.points);
    const mat = new THREE.LineBasicMaterial({ color: 0x4a9eff, linewidth: 2 });
    const ring = new THREE.Line(geom, mat);
    ring.userData.landmarkName = name;
    ring.userData.circumferenceCm = data.circumferenceCm;
    _ringGroup.add(ring);

    // Create HTML label
    const label = document.createElement('div');
    label.style.cssText = 'position:fixed;z-index:20;background:rgba(22,33,62,0.9);color:#4a9eff;border:1px solid #4a9eff;border-radius:4px;padding:2px 6px;font-size:11px;font-weight:bold;pointer-events:none;white-space:nowrap;display:none;';
    label.innerHTML = `<span style="color:#94a3b8;font-size:9px;">${name}</span> ${data.circumferenceCm.toFixed(1)}cm`;
    // Find rightmost point for label anchor
    let rightmost = data.points[0];
    for (const p of data.points) { if (p.x > rightmost.x) rightmost = p; }
    label.userData = { anchor: rightmost.clone() };
    document.body.appendChild(label);
    _ringLabels.push(label);
  }
  scene.add(_ringGroup);
}

function _clearRingLabels() {
  for (const el of _ringLabels) el.remove();
  _ringLabels = [];
}

function _updateRingLabels() {
  if (!_ringsVisible || _walkMode || _ringLabels.length === 0) return;
  for (const label of _ringLabels) {
    const pos = label.userData.anchor.clone();
    pos.project(camera);
    if (pos.z > 1) { label.style.display = 'none'; continue; }
    const x = (pos.x * 0.5 + 0.5) * window.innerWidth;
    const y = (-pos.y * 0.5 + 0.5) * window.innerHeight;
    label.style.left = (x + 10) + 'px';
    label.style.top = (y - 8) + 'px';
    label.style.display = 'block';
  }
}

function _buildGhostRings() {
  if (_ghostRingGroup) { scene.remove(_ghostRingGroup); _ghostRingGroup = null; }
  if (!_ghostMesh) return;
  _ghostRingGroup = new THREE.Group();
  _ghostRingGroup.visible = _ringsVisible;

  for (const [name, ratio] of Object.entries(_ANALYSIS_LANDMARKS)) {
    const data = _sortedCrossSection(_ghostMesh, ratio);
    if (!data) continue;
    const geom = new THREE.BufferGeometry().setFromPoints(data.points);
    const mat = new THREE.LineBasicMaterial({ color: 0x44ff88, linewidth: 2, transparent: true, opacity: 0.6 });
    const ring = new THREE.Line(geom, mat);
    ring.userData.landmarkName = name;
    ring.userData.circumferenceCm = data.circumferenceCm;
    _ghostRingGroup.add(ring);
  }
  scene.add(_ghostRingGroup);
  _updateRingLabelDeltas();
}

function _updateRingLabelDeltas() {
  if (!_ghostRingGroup || _ringLabels.length === 0) return;
  for (const label of _ringLabels) {
    const name = label.innerHTML.match(/<span[^>]*>(\w+)<\/span>/)?.[1];
    if (!name) continue;
    const ghostRing = _ghostRingGroup.children.find(r => r.userData.landmarkName === name);
    if (!ghostRing) continue;
    const curr = parseFloat(label.innerHTML.match(/([\d.]+)cm/)?.[1]);
    if (!curr) continue;
    const delta = curr - ghostRing.userData.circumferenceCm;
    const color = delta > 0.5 ? '#22c55e' : delta < -0.5 ? '#ef4444' : '#94a3b8';
    const sign = delta > 0 ? '+' : '';
    const deltaSpan = ` <span style="color:${color};font-size:9px;">${sign}${delta.toFixed(1)}</span>`;
    label.innerHTML = label.innerHTML.replace(/ <span style="color:#[0-9a-f]+;font-size:9px;">[^<]+<\/span>$/, '') + deltaSpan;
  }
}

window.toggleRings = function() {
  _ringsVisible = !_ringsVisible;
  if (_ringsVisible && !_ringGroup) _buildRings();
  if (_ringGroup) _ringGroup.visible = _ringsVisible;
  if (_ghostRingGroup) _ghostRingGroup.visible = _ringsVisible;
  for (const el of _ringLabels) el.style.display = _ringsVisible ? '' : 'none';
  const btn = document.getElementById('btn-rings');
  if (btn) btn.classList.toggle('active', _ringsVisible);
  _saveViewerSettings();
};

// ── Room shell (P1) ──────────────────────────────────────────────────────────
function _buildRoom() {
  _roomGroup = new THREE.Group();
  _roomGroup.visible = false;
  const hw = _ROOM_W / 2, hd = _ROOM_D / 2;

  const floorMat = new THREE.MeshStandardMaterial({ color: 0xd4cfc4, roughness: 0.8 });
  const wallMat  = new THREE.MeshStandardMaterial({ color: 0xe8e4dc, roughness: 0.7 });
  const ceilMat  = new THREE.MeshStandardMaterial({ color: 0xc8c4b8, roughness: 0.9 });

  // Floor
  const floor = new THREE.Mesh(new THREE.PlaneGeometry(_ROOM_W, _ROOM_D), floorMat);
  floor.rotation.x = -Math.PI / 2; floor.position.y = 0;
  floor.receiveShadow = true; floor.name = 'room_floor';
  _roomGroup.add(floor); _roomWalls.floor = floor;

  // Ceiling
  const ceiling = new THREE.Mesh(new THREE.PlaneGeometry(_ROOM_W, _ROOM_D), ceilMat);
  ceiling.rotation.x = Math.PI / 2; ceiling.position.y = _ROOM_H;
  ceiling.name = 'room_ceiling';
  _roomGroup.add(ceiling); _roomWalls.ceiling = ceiling;

  // Back wall (Z=-hd, facing +Z)
  const back = new THREE.Mesh(new THREE.PlaneGeometry(_ROOM_W, _ROOM_H), wallMat.clone());
  back.position.set(0, _ROOM_H / 2, -hd); back.receiveShadow = true; back.name = 'room_back';
  _roomGroup.add(back); _roomWalls.back = back;

  // Front wall (Z=+hd, facing -Z)
  const front = new THREE.Mesh(new THREE.PlaneGeometry(_ROOM_W, _ROOM_H), wallMat.clone());
  front.rotation.y = Math.PI; front.position.set(0, _ROOM_H / 2, hd);
  front.receiveShadow = true; front.name = 'room_front';
  _roomGroup.add(front); _roomWalls.front = front;

  // Left wall (X=-hw, facing +X)
  const left = new THREE.Mesh(new THREE.PlaneGeometry(_ROOM_D, _ROOM_H), wallMat.clone());
  left.rotation.y = Math.PI / 2; left.position.set(-hw, _ROOM_H / 2, 0);
  left.receiveShadow = true; left.name = 'room_left';
  _roomGroup.add(left); _roomWalls.left = left;

  // Right wall (X=+hw, facing -X)
  const right = new THREE.Mesh(new THREE.PlaneGeometry(_ROOM_D, _ROOM_H), wallMat.clone());
  right.rotation.y = -Math.PI / 2; right.position.set(hw, _ROOM_H / 2, 0);
  right.receiveShadow = true; right.name = 'room_right';
  _roomGroup.add(right); _roomWalls.right = right;

  // Floor measurement grid (20cm intervals, 20 divisions across 4m)
  _gridHelper = new THREE.GridHelper(_ROOM_W, 20, 0x777777, 0x555555);
  _gridHelper.position.y = 0.5;
  _roomGroup.add(_gridHelper);

  scene.add(_roomGroup);
}

window.toggleRoom = function() {
  _roomOn = !_roomOn;
  if (_roomGroup) _roomGroup.visible = _roomOn;
  if (_contactShadow) _contactShadow.visible = _roomOn;
  // Switch lights
  if (_roomOn) {
    _clearLights(_studioLightObjs);
    _setupRoomLights();
    scene.background = null;
  } else {
    _clearLights(_roomLightObjs);
    _setupStudioLights();
    scene.background = new THREE.Color(0x0a0a12);
  }
  document.getElementById('btn-room')?.classList.toggle('active', _roomOn);
  _saveViewerSettings();
};

// ── Contact shadow (P3) ─────────────────────────────────────────────────────
function _createContactShadow() {
  const sz = 128;
  const canvas = document.createElement('canvas');
  canvas.width = sz; canvas.height = sz;
  const ctx = canvas.getContext('2d');
  const grad = ctx.createRadialGradient(sz/2, sz/2, 0, sz/2, sz/2, sz/2);
  grad.addColorStop(0, 'rgba(0,0,0,0.35)');
  grad.addColorStop(1, 'rgba(0,0,0,0)');
  ctx.fillStyle = grad;
  ctx.fillRect(0, 0, sz, sz);
  const tex = new THREE.CanvasTexture(canvas);
  _contactShadow = new THREE.Mesh(
    new THREE.PlaneGeometry(80, 80),
    new THREE.MeshBasicMaterial({ map: tex, transparent: true, depthWrite: false })
  );
  _contactShadow.rotation.x = -Math.PI / 2;
  _contactShadow.position.y = 0.2;
  _contactShadow.visible = false;
  scene.add(_contactShadow);
}

// ── Mirror (P4) ─────────────────────────────────────────────────────────────
function _setupMirror() {
  _cubeRenderTarget = new THREE.WebGLCubeRenderTarget(512, {
    generateMipmaps: true,
    minFilter: THREE.LinearMipmapLinearFilter,
  });
  _cubeCamera = new THREE.CubeCamera(1, 2000, _cubeRenderTarget);
  scene.add(_cubeCamera);
}

window.toggleMirror = function() {
  // Restore previous mirror wall material
  if (_mirrorWallMesh && _preMirrorMat) {
    _mirrorWallMesh.material = _preMirrorMat;
    _mirrorWallMesh = null;
    _preMirrorMat = null;
  }
  _mirrorWallIndex++;
  if (_mirrorWallIndex >= _MIRROR_WALLS.length) _mirrorWallIndex = -1;
  if (_mirrorWallIndex < 0) {
    document.getElementById('btn-mirror')?.classList.remove('active');
    return;
  }
  // Auto-enable room if not on
  if (!_roomOn) window.toggleRoom();
  const wallName = _MIRROR_WALLS[_mirrorWallIndex];
  _mirrorWallMesh = _roomWalls[wallName];
  if (!_mirrorWallMesh) return;
  _preMirrorMat = _mirrorWallMesh.material;
  _mirrorWallMesh.material = new THREE.MeshStandardMaterial({
    metalness: 0.95, roughness: 0.05, envMap: _cubeRenderTarget.texture,
    color: 0xffffff,
  });
  // Position CubeCamera at wall surface
  _cubeCamera.position.copy(_mirrorWallMesh.position);
  document.getElementById('btn-mirror')?.classList.add('active');
};

function _updateMirror() {
  if (_mirrorWallIndex < 0 || !_mirrorWallMesh || !_cubeCamera) return;
  // Hide mirror wall before cube camera render to prevent self-reflection
  _mirrorWallMesh.visible = false;
  _cubeCamera.update(renderer, scene);
  _mirrorWallMesh.visible = true;
}

// ── Walk mode (P5) ──────────────────────────────────────────────────────────
function _setupWalkControls() {
  _pointerControls = new PointerLockControls(camera, renderer.domElement);
}

window.toggleWalkMode = function() {
  _walkMode = !_walkMode;
  if (_walkMode) {
    // Auto-enable room
    if (!_roomOn) window.toggleRoom();
    // Disable orbit, enable pointer lock
    controls.enabled = false;
    _pointerControls.lock();
    // Position camera at room corner, eye height, looking at body
    const hw = _ROOM_W / 2 - 20, hd = _ROOM_D / 2 - 20;
    camera.position.set(hw, _EYE_HEIGHT, hd);
    camera.lookAt(0, _EYE_HEIGHT * 0.5, 0);
    _walkClock.start();
    _moveState.forward = _moveState.backward = _moveState.left = _moveState.right = false;
  } else {
    _pointerControls.unlock();
    controls.enabled = true;
    _walkClock.stop();
    _moveState.forward = _moveState.backward = _moveState.left = _moveState.right = false;
    window.resetCamera();
  }
  document.getElementById('btn-walk')?.classList.toggle('active', _walkMode);
};

function _updateFirstPerson() {
  if (!_walkMode) return;
  const delta = _walkClock.getDelta();
  _moveDirection.set(0, 0, 0);
  if (_moveState.forward)  _moveDirection.z = -1;
  if (_moveState.backward) _moveDirection.z =  1;
  if (_moveState.left)     _moveDirection.x = -1;
  if (_moveState.right)    _moveDirection.x =  1;
  if (_moveDirection.lengthSq() > 0) {
    _moveDirection.normalize();
    _pointerControls.moveRight(_moveDirection.x * _WALK_SPEED * delta);
    _pointerControls.moveForward(-_moveDirection.z * _WALK_SPEED * delta);
  }
  // Lock eye height
  camera.position.y = _EYE_HEIGHT;
  // Wall collision: clamp to room bounds with margin
  const margin = 20;
  const hw = _ROOM_W / 2 - margin, hd = _ROOM_D / 2 - margin;
  camera.position.x = Math.max(-hw, Math.min(hw, camera.position.x));
  camera.position.z = Math.max(-hd, Math.min(hd, camera.position.z));
}

// ── Props (P6) ──────────────────────────────────────────────────────────────
function _buildProps() {
  _propsGroup = new THREE.Group();
  _propsGroup.visible = false;

  // 1m calibration rod (red cylinder, 178.6 scene units = 1000mm)
  const rodH = 178.6;
  const rodGeo = new THREE.CylinderGeometry(2, 2, rodH, 8);
  const rodMat = new THREE.MeshStandardMaterial({ color: 0xdd3333, roughness: 0.6 });
  const rod = new THREE.Mesh(rodGeo, rodMat);
  rod.position.set(80, rodH / 2, 0);
  rod.castShadow = true;
  _propsGroup.add(rod);

  // Camera stand A (front, 65cm = 116 scene units)
  const standH = 116;
  const standGeo = new THREE.CylinderGeometry(3, 3, standH, 8);
  const standMat = new THREE.MeshStandardMaterial({ color: 0x666666, roughness: 0.7 });
  const standA = new THREE.Mesh(standGeo, standMat);
  standA.position.set(0, standH / 2, 178);
  standA.castShadow = true;
  _propsGroup.add(standA);
  // Phone box on top
  const phoneGeo = new THREE.BoxGeometry(8, 16, 4);
  const phoneMat = new THREE.MeshStandardMaterial({ color: 0x222222 });
  const phoneA = new THREE.Mesh(phoneGeo, phoneMat);
  phoneA.position.set(0, standH + 8, 178);
  phoneA.castShadow = true;
  _propsGroup.add(phoneA);

  // Camera stand B (back)
  const standB = standA.clone();
  standB.position.set(0, standH / 2, -178);
  standB.castShadow = true;
  _propsGroup.add(standB);
  const phoneB = phoneA.clone();
  phoneB.position.set(0, standH + 8, -178);
  phoneB.castShadow = true;
  _propsGroup.add(phoneB);

  // Door outline on left wall (2m×0.9m = 357×161 scene units)
  const doorW = 161, doorH = 357;
  const doorGeo = new THREE.BoxGeometry(doorW, doorH, 2);
  const doorEdges = new THREE.EdgesGeometry(doorGeo);
  const doorLine = new THREE.LineSegments(doorEdges, new THREE.LineBasicMaterial({ color: 0x888888 }));
  doorLine.position.set(-_ROOM_W / 2 + 1, doorH / 2, -100);
  doorLine.rotation.y = Math.PI / 2;
  _propsGroup.add(doorLine);

  scene.add(_propsGroup);
}

window.toggleProps = function() {
  _propsOn = !_propsOn;
  if (_propsGroup) _propsGroup.visible = _propsOn;
  document.getElementById('btn-props')?.classList.toggle('active', _propsOn);
};

// ── Room texture loading (P2) ───────────────────────────────────────────────
async function _loadRoomTextures() {
  if (!_viewerToken) return;
  try {
    const cid = _customerId();
    const resp = await fetch(`/web_app/api/customer/${cid}/room_textures`, {
      headers: { 'Authorization': `Bearer ${_viewerToken}` },
    });
    const data = await resp.json();
    if (data.status !== 'success' || !data.textures) return;
    const loader = new THREE.TextureLoader();
    for (const t of data.textures) {
      const wall = _roomWalls[t.surface];
      if (!wall) continue;
      loader.load(t.url, (tex) => {
        wall.material.map = tex;
        wall.material.needsUpdate = true;
      });
    }
  } catch (e) { console.warn('Room textures not loaded:', e); }
}

// ── Loading progress bar ───────────────────────────────────────────────────────
function _showProgress(pct) {
  let bar = document.getElementById('load-progress');
  if (!bar) {
    bar = document.createElement('div');
    bar.id = 'load-progress';
    bar.style.cssText = 'position:fixed;top:0;left:0;height:3px;background:#4a9eff;transition:width 0.2s;z-index:9999;pointer-events:none;';
    document.body.appendChild(bar);
  }
  bar.style.width = pct + '%';
}

function _hideProgress() {
  const bar = document.getElementById('load-progress');
  if (bar) { bar.style.width = '100%'; setTimeout(() => bar.remove(), 350); }
}

// ── Render loop ───────────────────────────────────────────────────────────────
let _mirrorFrame = 0;
function _animate() {
  requestAnimationFrame(_animate);
  if (_camTransition) {
    const t = Math.min(1, (performance.now() - _camTransition.startTime) / _camTransition.duration);
    const e = t * (2 - t);
    camera.position.lerpVectors(_camTransition.startPos, _camTransition.endPos, e);
    controls.target.lerpVectors(_camTransition.startTarget, _camTransition.endTarget, e);
    if (t >= 1) _camTransition = null;
  }
  _updateFirstPerson();
  _mcpUpdateRotations();
  
    // Continuous Zoom (z=in, v=out)
    if (_moveState.zoomIn) {
        const factor = 0.975; // 2.5% per frame (smoother)
        const dist = camera.position.distanceTo(controls.target);
        if (dist > controls.minDistance + 1) {
            camera.position.lerp(controls.target, 1.0 - factor);
            controls.update();
        }
    }
    if (_moveState.zoomOut) {
        const factor = 1.025; // 2.5% per frame (smoother)
        const dist = camera.position.distanceTo(controls.target);
        if (dist < controls.maxDistance - 1) {
            const dir = new THREE.Vector3().subVectors(camera.position, controls.target).normalize();
            camera.position.addScaledVector(dir, dist * (factor - 1.0));
            controls.update();
        }
    }
    
    // Distance-Aware Normal Scaling (Gemini Pro)
    if (bodyMesh) {
        const dist = camera.position.distanceTo(controls.target);
        // Scale normals from 0.8 (close) up to 2.5 (far) to maintain anatomical pop
        const nScale = THREE.MathUtils.mapLinear(THREE.MathUtils.clamp(dist, 50, 800), 50, 800, 0.8, 2.5);
        bodyMesh.traverse(c => {
            if (c.isMesh && c.material && c.material.normalScale) {
                c.material.normalScale.set(nScale, nScale);
            }
        });
    }
    if (!_walkMode) controls.update();
  // Update mirror every 2nd frame for performance (always uses renderer directly)
  if (++_mirrorFrame % 2 === 0) _updateMirror();
  // Render with SSAO composer when enabled, otherwise direct
  if (_composer && _ssaoEnabled) {
    _composer.render();
  } else {
    renderer.render(scene, camera);
  }
  _updateRegionLabels();
  _updateRingLabels();
}

function _onResize() {
  camera.aspect = window.innerWidth / window.innerHeight;
  camera.updateProjectionMatrix();
  renderer.setSize(window.innerWidth, window.innerHeight);
  if (_composer) _composer.setSize(window.innerWidth, window.innerHeight);
}

// ── CSV Export ───────────────────────────────────────────────────────────────
async function exportDataCSV() {
  if (!_viewerToken) await _autoLogin();
  const params = new URLSearchParams(location.search);
  const cid = params.get('customer') || '1';
  try {
    const r = await fetch(`/web_app/api/customer/${cid}/progress_report`, {
      headers: { 'Authorization': 'Bearer ' + _viewerToken }
    });
    const d = await r.json();
    if (d.status !== 'success') throw new Error(d.message);

    const lines = ['GTD3D Body Data Export', ''];
    lines.push('PROFILE', 'Field,Value');
    const p = d.profile;
    if (p.height_cm) lines.push(`Height (cm),${p.height_cm}`);
    if (p.weight_kg) lines.push(`Weight (kg),${p.weight_kg}`);
    if (p.gender)    lines.push(`Gender,${p.gender}`);

    lines.push('', 'CIRCUMFERENCES', 'Region,Value (cm)');
    Object.entries(d.circumferences || {}).forEach(([k, v]) => lines.push(`${k},${v}`));

    lines.push('', 'SCAN HISTORY', 'Mesh ID,Date,Volume (cm³)');
    (d.meshes || []).forEach(m => lines.push(`${m.id},${m.date},${m.volume_cm3 || ''}`));

    if (window.MeasurementOverlay && window.MeasurementOverlay.measurements?.length) {
      lines.push('', 'VIEWER MEASUREMENTS', 'Name,Distance (mm)');
      window.MeasurementOverlay.measurements.forEach((m, i) =>
        lines.push(`${m.name || 'Distance ' + (i+1)},${m.distance_mm.toFixed(1)}`));
    }

    const blob = new Blob([lines.join('\n')], { type: 'text/csv' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `body_data_${cid}_${new Date().toISOString().slice(0,10)}.csv`;
    a.click();
    URL.revokeObjectURL(url);
  } catch (e) {
    console.error('Export failed:', e);
    alert('Export failed: ' + e.message);
  }
}
window.exportDataCSV = exportDataCSV;

// ── Skin photo upload ─────────────────────────────────────────────────────────
async function uploadSkinPhoto(file) {
  if (!file) return;
  if (!_viewerToken) await _autoLogin();
  const params = new URLSearchParams(location.search);
  const cid = params.get('customer') || '1';

  const info = document.getElementById('mesh-info');
  if (info) info.textContent = 'Processing skin texture...';

  const formData = new FormData();
  formData.append('image', file);
  formData.append('distance', '30');
  formData.append('size', '1024');

  try {
    const r = await fetch(`/web_app/api/customer/${cid}/skin_texture`, {
      method: 'POST',
      headers: { 'Authorization': 'Bearer ' + _viewerToken },
      body: formData,
    });
    const d = await r.json();
    if (d.status !== 'success') throw new Error(d.message);

    await _loadRealSkinTexture();
    window.setViewMode('skin');

    if (info) info.textContent = 'Skin texture applied!';
    setTimeout(() => { if (info) info.textContent = ''; }, 2000);
  } catch (e) {
    if (info) info.textContent = 'Skin upload failed: ' + e.message;
    console.error('Skin upload failed:', e);
  }
}
window.uploadSkinPhoto = uploadSkinPhoto;

// ── Customer selector ─────────────────────────────────────────────────────────
async function _loadCustomerList() {
  if (!_viewerToken) return;
  try {
    const r = await fetch('/web_app/api/customers', {
      headers: { 'Authorization': 'Bearer ' + _viewerToken }
    });
    const d = await r.json();
    if (d.status !== 'success' || !d.customers) return;
    const sel = document.getElementById('customer-select');
    if (!sel) return;
    if (d.customers.length <= 1) return;

    const params = new URLSearchParams(location.search);
    const currentCid = params.get('customer') || '1';
    sel.innerHTML = d.customers.map(c =>
      `<option value="${c.id}" ${c.id == currentCid ? 'selected' : ''}>${c.name} (${c.mesh_count} scans)</option>`
    ).join('');
    sel.style.display = 'block';
  } catch (e) { /* ignore */ }
}

function switchCustomer(cid) {
  const params = new URLSearchParams(location.search);
  params.set('customer', cid);
  fetch(`/web_app/api/customer/${cid}/meshes`, {
    headers: { 'Authorization': 'Bearer ' + _viewerToken }
  }).then(r => r.json()).then(d => {
    const meshes = d.meshes || [];
    if (meshes.length > 0) params.set('model', `/web_app/api/mesh/${meshes[0].id}.glb`);
    location.search = params.toString();
  }).catch(() => {
    params.delete('model');
    location.search = params.toString();
  });
}
window.switchCustomer = switchCustomer;

// ── MCP WebSocket Bridge ─────────────────────────────────────────────────────
// Connects to three-js-mcp server (port 8082) so Claude can remotely
// add/move/remove objects and control rotation via MCP tool calls.

let _mcpWs = null;
const _mcpObjects = {};   // id → THREE.Mesh
const _mcpRotations = {}; // id → { speed }

function _mcpConnect() {
  const url = 'ws://localhost:8082';
  try { _mcpWs = new WebSocket(url); } catch { return; }

  _mcpWs.onopen = () => {
    console.log('[MCP] Connected to three-js-mcp');
    _mcpSendSceneState();
  };

  _mcpWs.onmessage = (evt) => {
    let cmd;
    try { cmd = JSON.parse(evt.data); } catch { return; }
    _mcpHandleCommand(cmd);
  };

  _mcpWs.onclose = () => {
    console.log('[MCP] Disconnected — reconnecting in 5s');
    setTimeout(_mcpConnect, 5000);
  };

  _mcpWs.onerror = () => {}; // suppress console noise; onclose handles reconnect
}

function _mcpHandleCommand(cmd) {
  const { action } = cmd;

  if (action === 'addObject') {
    const geomMap = {
      cube:     () => new THREE.BoxGeometry(30, 30, 30),
      sphere:   () => new THREE.SphereGeometry(15, 24, 24),
      cylinder: () => new THREE.CylinderGeometry(10, 10, 40, 24),
      cone:     () => new THREE.ConeGeometry(15, 40, 24),
      torus:    () => new THREE.TorusGeometry(15, 5, 16, 48),
    };
    const geomFn = geomMap[(cmd.type || 'cube').toLowerCase()] || geomMap.cube;
    const color = cmd.color ? new THREE.Color(cmd.color) : new THREE.Color(0x00ff88);
    const mesh = new THREE.Mesh(geomFn(), new THREE.MeshStandardMaterial({ color }));
    if (cmd.position) mesh.position.set(cmd.position[0], cmd.position[1], cmd.position[2]);
    const id = cmd.id || `mcp_${Date.now()}`;
    mesh.name = id;
    scene.add(mesh);
    _mcpObjects[id] = mesh;
    _mcpSendSceneState();
  }

  else if (action === 'moveObject' && cmd.id && _mcpObjects[cmd.id]) {
    const m = _mcpObjects[cmd.id];
    if (cmd.position) m.position.set(cmd.position[0], cmd.position[1], cmd.position[2]);
    _mcpSendSceneState();
  }

  else if (action === 'removeObject' && cmd.id && _mcpObjects[cmd.id]) {
    scene.remove(_mcpObjects[cmd.id]);
    _mcpObjects[cmd.id].geometry.dispose();
    _mcpObjects[cmd.id].material.dispose();
    delete _mcpObjects[cmd.id];
    delete _mcpRotations[cmd.id];
    _mcpSendSceneState();
  }

  else if (action === 'startRotation' && cmd.id && _mcpObjects[cmd.id]) {
    _mcpRotations[cmd.id] = { speed: cmd.speed || 0.02 };
  }

  else if (action === 'stopRotation' && cmd.id) {
    delete _mcpRotations[cmd.id];
  }
}

function _mcpSendSceneState() {
  if (!_mcpWs || _mcpWs.readyState !== WebSocket.OPEN) return;
  const data = Object.entries(_mcpObjects).map(([id, mesh]) => ({
    id,
    type: mesh.geometry.type.replace('Geometry', '').replace('Buffer', '').toLowerCase(),
    position: [mesh.position.x, mesh.position.y, mesh.position.z],
    color: '#' + mesh.material.color.getHexString(),
  }));
  _mcpWs.send(JSON.stringify({ type: 'sceneState', data }));
}

function _mcpUpdateRotations() {
  for (const [id, { speed }] of Object.entries(_mcpRotations)) {
    const m = _mcpObjects[id];
    if (m) m.rotation.y += speed;
  }
}

// ── GPU Status ────────────────────────────────────────────────────────────────
async function _checkGPUStatus() {
    try {
        const resp = await fetch('/web_app/api/gpu_status');
        const data = await resp.json();
        const indicator = document.getElementById('gpu-status');
        if (!indicator) return;

        if (data.gpu === 'available') {
            indicator.textContent = 'GPU';
            indicator.style.color = '#4CAF50';
            indicator.title = `RunPod GPU ready (${data.tasks_supported?.length || 0} tasks)`;
        } else {
            indicator.textContent = 'GPU';
            indicator.style.color = '#666';
            indicator.title = 'GPU offline \u2014 using local CPU';
        }
    } catch (e) {
        // Silent fail — GPU status is informational only
    }
}

// ── Boot ──────────────────────────────────────────────────────────────────────
init();
_checkGPUStatus();
_mcpConnect();

// Build muscle highlight panel (attaches to #canvas-container)
const _panelContainer = document.getElementById('canvas-container') || document.body;
buildMusclePanel(_muscleHL, _panelContainer);

// Build skin upload panel (bottom-right)
buildSkinUploadPanel(_panelContainer, (newGlbUrl) => {
  // Reload model when skin texture is updated
  if (typeof loadModel === 'function') loadModel(newGlbUrl);
});

// ── Mobile UI helpers ─────────────────────────────────────────────────────────

window.toggleCard = function() {
  const card = document.querySelector('.card');
  if (!card) return;
  // On mobile: toggle 'expanded' class (card hidden by default via CSS)
  // On desktop: toggle 'collapsed' class (card visible by default)
  if (window.innerWidth <= 768) {
    card.classList.toggle('expanded');
  } else {
    card.classList.toggle('collapsed');
  }
};

window.toggleMusclePanel = function() {
  const panel = document.getElementById('muscle-panel');
  if (!panel) return;
  panel.style.display = panel.style.display === 'none' ? 'flex' : 'none';
};

// Mobile panels are hidden by CSS @media rules — toggled via bottom bar buttons
