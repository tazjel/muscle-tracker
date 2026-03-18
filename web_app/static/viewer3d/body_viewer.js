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

// ── Scene globals ─────────────────────────────────────────────────────────────
let scene, camera, renderer, controls;
let bodyMesh      = null;   // the loaded mesh object
let heatmapOn     = false;
let origMaterials = [];     // stored to restore after heatmap
const _originalMaterials = new Map();  // mesh → original loaded material (for texture toggle)
const raycaster  = new THREE.Raycaster();
const _mouse     = new THREE.Vector2();

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
const _moveState     = { forward: false, backward: false, left: false, right: false };
const _moveDirection = new THREE.Vector3();
const _WALK_SPEED    = 200;
const _EYE_HEIGHT    = 300;
let _walkClock       = new THREE.Clock(false);

// ── Props globals ────────────────────────────────────────────────────────────
let _propsGroup = null;
let _propsOn    = false;

// ── Light groups ─────────────────────────────────────────────────────────────
let _studioLightObjs = [];
let _roomLightObjs   = [];

// ── V8 globals ───────────────────────────────────────────────────────────────
let _meshList    = [];
let _ghostMesh   = null;
let _autoRotate  = false;
let _gridHelper  = null;
let _camTransition = null;
let _timelineTimer = null;

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
let _viewerToken = null;

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

// ── Procedural skin texture — color variation like real skin ──────────────────
function _createSkinColorMap(size = 512) {
  const canvas = document.createElement('canvas');
  canvas.width = canvas.height = size;
  const ctx = canvas.getContext('2d');

  // Base skin tone
  ctx.fillStyle = '#C4956A';
  ctx.fillRect(0, 0, size, size);

  // Layer 1: Large blotchy patches (vein/flush areas)
  for (let i = 0; i < 40; i++) {
    const x = Math.random() * size;
    const y = Math.random() * size;
    const r = 30 + Math.random() * 80;
    const colors = ['rgba(180,100,90,0.08)', 'rgba(160,110,80,0.06)',
                    'rgba(200,130,100,0.07)', 'rgba(140,90,70,0.05)'];
    const grad = ctx.createRadialGradient(x, y, 0, x, y, r);
    grad.addColorStop(0, colors[i % colors.length]);
    grad.addColorStop(1, 'rgba(196,149,106,0)');
    ctx.fillStyle = grad;
    ctx.fillRect(0, 0, size, size);
  }

  // Layer 2: Fine speckle noise (pores, freckles)
  const imgData = ctx.getImageData(0, 0, size, size);
  const d = imgData.data;
  for (let i = 0; i < d.length; i += 4) {
    const vary = (Math.random() - 0.5) * 18;
    d[i]     = Math.max(0, Math.min(255, d[i] + vary));         // R
    d[i + 1] = Math.max(0, Math.min(255, d[i + 1] + vary * 0.7)); // G
    d[i + 2] = Math.max(0, Math.min(255, d[i + 2] + vary * 0.5)); // B
  }
  ctx.putImageData(imgData, 0, 0);

  const tex = new THREE.CanvasTexture(canvas);
  tex.wrapS = tex.wrapT = THREE.RepeatWrapping;
  tex.repeat.set(4, 4);
  tex.colorSpace = THREE.SRGBColorSpace;
  return tex;
}

// ── Skin normal map — multi-scale bumps (pores + wrinkle lines) ──────────────
function _createSkinNormalMap(size = 512) {
  const canvas = document.createElement('canvas');
  canvas.width = canvas.height = size;
  const ctx = canvas.getContext('2d');
  ctx.fillStyle = 'rgb(128,128,255)';
  ctx.fillRect(0, 0, size, size);
  const imgData = ctx.getImageData(0, 0, size, size);
  const d = imgData.data;

  // Pass 1: Fine pore noise
  for (let i = 0; i < d.length; i += 4) {
    d[i]     = 128 + (Math.random() - 0.5) * 25;
    d[i + 1] = 128 + (Math.random() - 0.5) * 25;
  }

  // Pass 2: Larger bumps (muscle/skin folds) via scattered dents
  for (let n = 0; n < 200; n++) {
    const cx = Math.floor(Math.random() * size);
    const cy = Math.floor(Math.random() * size);
    const r = 3 + Math.floor(Math.random() * 8);
    const strength = 15 + Math.random() * 25;
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

  // Pass 3: Fine wrinkle lines (horizontal/vertical creases)
  for (let n = 0; n < 60; n++) {
    const horizontal = Math.random() > 0.5;
    const pos = Math.floor(Math.random() * size);
    const len = 20 + Math.floor(Math.random() * 60);
    const start = Math.floor(Math.random() * (size - len));
    const str = 20 + Math.random() * 15;
    for (let t = 0; t < len; t++) {
      const x = horizontal ? start + t : pos;
      const y = horizontal ? pos : start + t;
      const idx = (y * size + x) * 4;
      const ch = horizontal ? 1 : 0;  // perturb perpendicular to line
      d[idx + ch] = Math.max(0, Math.min(255, d[idx + ch] + str));
    }
  }

  ctx.putImageData(imgData, 0, 0);
  const tex = new THREE.CanvasTexture(canvas);
  tex.wrapS = tex.wrapT = THREE.RepeatWrapping;
  tex.repeat.set(6, 6);
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
  ctx.putImageData(imgData, 0, 0);
  const tex = new THREE.CanvasTexture(canvas);
  tex.wrapS = tex.wrapT = THREE.RepeatWrapping;
  tex.repeat.set(4, 4);
  return tex;
}

const SKIN_MATERIAL = new THREE.MeshPhysicalMaterial({
  map:              _createSkinColorMap(),       // color variation, not flat
  roughnessMap:     _createSkinRoughnessMap(),   // varied roughness
  roughness:        0.6,
  metalness:        0.0,
  side:             THREE.DoubleSide,
  // Subsurface scattering approximation
  sheen:            0.5,
  sheenRoughness:   0.5,
  sheenColor:       new THREE.Color(0xcc7755),   // warm reddish undertone (blood)
  // Skin sheen
  clearcoat:        0.03,
  clearcoatRoughness: 0.5,
  // Normal map for surface detail
  normalMap:        _createSkinNormalMap(),
  normalScale:      new THREE.Vector2(0.6, 0.6), // stronger bumps
});

// ── Init ──────────────────────────────────────────────────────────────────────
function init() {
  const container = document.getElementById('canvas-container');

  // Scene
  scene = new THREE.Scene();
  scene.background = new THREE.Color(0x1a1a2e);

  // Camera
  camera = new THREE.PerspectiveCamera(50, window.innerWidth / window.innerHeight, 0.1, 5000);
  camera.position.set(0, 150, 400);

  // Renderer
  renderer = new THREE.WebGLRenderer({ antialias: true, preserveDrawingBuffer: true });
  renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
  renderer.setSize(window.innerWidth, window.innerHeight);
  renderer.toneMapping        = THREE.ACESFilmicToneMapping;
  renderer.toneMappingExposure = 1.1;
  renderer.shadowMap.enabled  = true;
  renderer.shadowMap.type     = THREE.PCFSoftShadowMap;
  container.appendChild(renderer.domElement);

  // Controls
  controls = new OrbitControls(camera, renderer.domElement);
  controls.enableDamping    = true;
  controls.dampingFactor    = 0.08;
  controls.minDistance      = 50;
  controls.maxDistance      = 2000;
  controls.target.set(0, 80, 0);  // roughly mid-torso height
  controls.update();

  // Lights
  _setupStudioLights();

  // Environment map (PMREMGenerator gradient — no external HDR file needed)
  _setupEnvironment();

  // V7: Room, props, mirror, contact shadow
  _buildRoom();
  _buildProps();
  _createContactShadow();
  _setupMirror();
  _setupWalkControls();

  // Resize
  window.addEventListener('resize', _onResize);

  // Restore sidebar when exiting fullscreen via Escape
  document.addEventListener('fullscreenchange', () => {
    if (!document.fullscreenElement) {
      const overlay = document.getElementById('ui-overlay');
      if (overlay) overlay.style.display = '';
    }
  });

  // Expose for MeasurementOverlay
  window.bodyViewer = {
    scene, camera, renderer,
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

  // Collapsible panels — click h3 to toggle
  document.querySelectorAll('.collapsible > h3').forEach(h3 => {
    h3.addEventListener('click', () => h3.parentElement.classList.toggle('collapsed'));
  });

  // Authenticate for save/regenerate calls then load mesh list + room textures
  _autoLogin().then(() => { _loadMeshList(); _loadRoomTextures(); _loadBodyStats(); });

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
      case 's': case 'S':
        if (_walkMode) _moveState.backward = true;
        else if (!e.ctrlKey) window.takeScreenshot();
        break;
      case 'w': case 'W': if (_walkMode) _moveState.forward  = true; break;
      case 'a': case 'A': if (_walkMode) _moveState.left     = true; break;
      case 'd': case 'D': if (_walkMode) _moveState.right    = true; break;
      case 'Escape':
        if (_walkMode) { window.toggleWalkMode(); break; }
        _measureMode = false;
        document.getElementById('btn-measure')?.classList.remove('active');
        break;
    }
  });
  document.addEventListener('keyup', (e) => {
    switch (e.key) {
      case 'w': case 'W': _moveState.forward  = false; break;
      case 'a': case 'A': _moveState.left     = false; break;
      case 's': case 'S': _moveState.backward = false; break;
      case 'd': case 'D': _moveState.right    = false; break;
    }
  });

  // Start render loop
  _animate();
}

// ── Lighting ──────────────────────────────────────────────────────────────────
function _setupStudioLights() {
  const a = new THREE.AmbientLight(0xfff5e4, 0.4);
  scene.add(a); _studioLightObjs.push(a);

  const h = new THREE.HemisphereLight(0xffeedd, 0x334455, 0.5);
  scene.add(h); _studioLightObjs.push(h);

  const key = new THREE.DirectionalLight(0xffffff, 1.2);
  key.position.set(0, 400, 200);
  key.castShadow = true;
  key.shadow.mapSize.set(1024, 1024);
  // Expand frustum so body shadow covers room floor
  key.shadow.camera.left   = -400;
  key.shadow.camera.right  =  400;
  key.shadow.camera.top    =  400;
  key.shadow.camera.bottom = -400;
  scene.add(key); _studioLightObjs.push(key);

  const fill = new THREE.DirectionalLight(0xe8f0ff, 0.4);
  fill.position.set(-300, 100, 100);
  scene.add(fill); _studioLightObjs.push(fill);

  const rim = new THREE.DirectionalLight(0xffffff, 0.25);
  rim.position.set(0, 50, -400);
  scene.add(rim); _studioLightObjs.push(rim);
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

// ── Environment map (procedural, no file) ─────────────────────────────────────
function _setupEnvironment() {
  const pmrem = new THREE.PMREMGenerator(renderer);
  pmrem.compileEquirectangularShader();

  // Warm studio-like environment for skin-flattering reflections
  const envScene = new THREE.Scene();
  envScene.background = new THREE.Color(0x2a2535);

  // Sky dome — warm overhead light
  const domeGeo = new THREE.SphereGeometry(900, 16, 8, 0, Math.PI * 2, 0, Math.PI / 2);
  const domeMat = new THREE.MeshBasicMaterial({
    color: 0x665544, side: THREE.BackSide,
  });
  envScene.add(new THREE.Mesh(domeGeo, domeMat));

  // Ground plane — subtle warm bounce fill
  const floorGeo = new THREE.PlaneGeometry(2000, 2000);
  const floorMat = new THREE.MeshBasicMaterial({ color: 0x443333 });
  const floor = new THREE.Mesh(floorGeo, floorMat);
  floor.rotation.x = -Math.PI / 2;
  floor.position.y = -10;
  envScene.add(floor);

  // Emissive panels for soft fill (studio softbox simulation)
  const panelGeo = new THREE.PlaneGeometry(400, 600);
  const panelMat = new THREE.MeshBasicMaterial({ color: 0xffeedd });
  // Front-left softbox
  const p1 = new THREE.Mesh(panelGeo, panelMat);
  p1.position.set(-500, 300, 300);
  p1.lookAt(0, 150, 0);
  envScene.add(p1);
  // Front-right softbox
  const p2 = new THREE.Mesh(panelGeo, panelMat);
  p2.position.set(500, 300, 300);
  p2.lookAt(0, 150, 0);
  envScene.add(p2);
  // Back rim panel (cooler)
  const p3 = new THREE.Mesh(panelGeo, new THREE.MeshBasicMaterial({ color: 0xccddff }));
  p3.position.set(0, 200, -500);
  p3.lookAt(0, 150, 0);
  envScene.add(p3);

  const envTex = pmrem.fromScene(envScene, 0.04).texture;
  scene.environment = envTex;
  pmrem.dispose();
}

// ── Load from URL params ──────────────────────────────────────────────────────
function _loadFromUrl() {
  const params      = new URLSearchParams(window.location.search);
  const glbUrl      = params.get('model');
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
  } else if (objUrl) {
    _loadOBJ(objUrl);
  } else {
    _showPlaceholder();
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
      bodyMesh = gltf.scene;
      _applyDefaultMaterial(bodyMesh);
      _centerAndScale(bodyMesh);
      scene.add(bodyMesh);
      _updateStats(bodyMesh);
      _setStatus('');
      _createRegionLabels();
      _computeAnalysis();
      if (_ringsVisible) _buildRings();
      _resetVisModes();
      _ghostRich = {};
      _hideProgress();
      if (onLoaded) onLoaded();
    },
    (xhr) => {
      if (xhr.total > 0) _showProgress(Math.round(xhr.loaded / xhr.total * 100));
      _setStatus(`Loading… ${xhr.total > 0 ? Math.round(xhr.loaded / xhr.total * 100) + '%' : ''}`);
    },
    (err) => { console.error(err); _setStatus('Error loading model'); _hideProgress(); },
  );
}

// ── OBJ Loader (legacy) ───────────────────────────────────────────────────────
function _loadOBJ(url) {
  _setStatus('Loading OBJ…');
  const loader = new OBJLoader();
  loader.load(url,
    (obj) => {
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
      // Store original material for texture toggle
      _originalMaterials.set(child, child.material);
      origMaterials.push({ mesh: child, mat: child.material });
      // Upgrade all body meshes to the physical skin material for realism
      const hasTexture = child.material && child.material.map;
      if (hasTexture) {
        // Keep embedded texture but upgrade material properties
        const tex = child.material.map;
        const mat = SKIN_MATERIAL.clone();
        mat.map = tex;
        child.material = mat;
      } else {
        child.material = SKIN_MATERIAL.clone();
      }
      _originalMaterials.set(child, child.material);
      child.castShadow    = true;
      child.receiveShadow = true;
    }
  });
}

function _centerAndScale(object) {
  // Our mesh is exported Z-up (height = Z); rotate to Y-up for Three.js
  object.rotation.x = -Math.PI / 2;

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
  object.rotation.x = -Math.PI / 2;
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

// ── Placeholder (no URL) ──────────────────────────────────────────────────────
function _showPlaceholder() {
  _setStatus('No model URL — use ?model=path.glb');
  const geo = new THREE.CapsuleGeometry(30, 80, 16, 32);
  const mat = SKIN_MATERIAL.clone();
  bodyMesh = new THREE.Mesh(geo, mat);
  bodyMesh.position.y = 80;
  bodyMesh.castShadow = true;
  scene.add(bodyMesh);
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

function _openAdjustPanel(region) {
  _currentRegion = region;
  const panel = document.getElementById('adjust-panel');
  if (!panel) return;
  document.getElementById('adjust-region').textContent =
    region.charAt(0).toUpperCase() + region.slice(1);
  // Restore saved slider values
  const saved = _regionAdjustments[region] || { width: 0, depth: 0, length: 0 };
  ['width', 'depth', 'length'].forEach(dim => {
    const slider = document.getElementById('adj-' + dim);
    const val    = document.getElementById('adj-' + dim + '-val');
    if (slider) slider.value = saved[dim];
    if (val)    val.textContent = saved[dim];
  });
  panel.style.display = 'block';
}

function _getRegionZRange(region) {
  // Returns [minY, maxY] in scene units — body spans 0 to ~targetH
  // These ratios match getBodyRegion() thresholds
  if (!bodyMesh) return [0, 300];
  const box = new THREE.Box3().setFromObject(bodyMesh);
  const h = box.max.y - box.min.y;
  const base = box.min.y;
  const RANGES = {
    ankle:    [0.00, 0.08], calf:   [0.08, 0.18], knee:   [0.18, 0.28],
    thigh:    [0.28, 0.40], hip:    [0.40, 0.50], waist:  [0.50, 0.58],
    chest:    [0.58, 0.70], shoulder:[0.70, 0.82], neck:  [0.82, 0.90],
    head:     [0.90, 1.00], arm:    [0.55, 1.00], leg:    [0.00, 0.40],
  };
  const r = RANGES[region] || [0, 1];
  return [base + r[0] * h, base + r[1] * h];
}

window.applyAdjustment = function() {
  if (!bodyMesh || !_currentRegion) return;
  const wDelta = parseFloat(document.getElementById('adj-width')?.value || 0);
  const dDelta = parseFloat(document.getElementById('adj-depth')?.value || 0);
  const lDelta = parseFloat(document.getElementById('adj-length')?.value || 0);
  _regionAdjustments[_currentRegion] = { width: wDelta, depth: dDelta, length: lDelta };

  const [yMin, yMax] = _getRegionZRange(_currentRegion);
  bodyMesh.traverse(child => {
    if (!child.isMesh || !child.geometry) return;
    const pos = child.geometry.attributes.position;
    if (!pos) return;
    for (let i = 0; i < pos.count; i++) {
      const y = pos.getY(i);
      if (y < yMin || y > yMax) continue;
      const x = pos.getX(i);
      const z = pos.getZ(i);
      const dist = Math.sqrt(x * x + z * z);
      if (dist > 0) {
        pos.setX(i, x * (1 + wDelta / (dist + 1)));
        pos.setZ(i, z * (1 + dDelta / (dist + 1)));
      }
      if (yMax > yMin) {
        pos.setY(i, y + lDelta * (y - yMin) / (yMax - yMin));
      }
    }
    pos.needsUpdate = true;
    child.geometry.computeBoundingBox();
  });
};

window.resetAdjustment = function() {
  ['adj-width', 'adj-depth', 'adj-length'].forEach(id => {
    const el = document.getElementById(id);
    if (el) el.value = 0;
    const vEl = document.getElementById(id + '-val');
    if (vEl) vEl.textContent = 0;
  });
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

    // 3. POST absolute values back
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
      const params = new URLSearchParams(window.location.search);
      params.set('model', meshResult.glb_url);
      window.location.search = params.toString();
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
        child.geometry.deleteAttribute('color');
      }
    });
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
  } else if (mode === 'heatmap') {
    heatmapOn = true;
    // Generate test gradient data
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
    if (parts.length) ctx.fillText(parts.join('  \u00b7  '), 12 * scale, canvas.height - barH + 36 * scale);
  }

  // Download
  const link = document.createElement('a');
  link.download = `gtd3d_${Date.now()}.png`;
  link.href = canvas.toDataURL('image/png');
  link.click();
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
    _setStatus('Ghost: scan #' + meshId);
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
    scene.background = new THREE.Color(0x1a1a2e);
  }
  document.getElementById('btn-room')?.classList.toggle('active', _roomOn);
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
  if (!_walkMode) controls.update();
  // Update mirror every 2nd frame for performance
  if (++_mirrorFrame % 2 === 0) _updateMirror();
  renderer.render(scene, camera);
  _updateRegionLabels();
  _updateRingLabels();
}

function _onResize() {
  camera.aspect = window.innerWidth / window.innerHeight;
  camera.updateProjectionMatrix();
  renderer.setSize(window.innerWidth, window.innerHeight);
}

// ── Boot ──────────────────────────────────────────────────────────────────────
init();
