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
import { OrbitControls } from 'https://cdn.jsdelivr.net/npm/three@0.160.0/examples/jsm/controls/OrbitControls.js';
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

// User's skin tone — light brown #C4956A
const SKIN_COLOR    = 0xC4956A;
const SKIN_MATERIAL = new THREE.MeshStandardMaterial({
  color:     SKIN_COLOR,
  roughness: 0.65,
  metalness: 0.0,
  side:      THREE.DoubleSide,
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
  _setupLights();

  // Environment map (PMREMGenerator gradient — no external HDR file needed)
  _setupEnvironment();

  // Resize
  window.addEventListener('resize', _onResize);

  // Expose for MeasurementOverlay
  window.bodyViewer = {
    scene, camera, renderer,
    get mesh() { return bodyMesh; },
    getMeshIntersection: _getMeshIntersection,
  };

  // Click-to-select body region
  renderer.domElement.addEventListener('click', _onMeshClick);

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

  // Authenticate for save/regenerate calls then load mesh list
  _autoLogin().then(() => _loadMeshList());

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
      case 'l': case 'L': window.toggleLabels();  break;
      case 'm': case 'M': window.toggleMeasure(); break;
      case 'r': case 'R': window.resetCamera();   break;
      case 's': case 'S': if (!e.ctrlKey) window.takeScreenshot(); break;
      case 'Escape':
        _measureMode = false;
        document.getElementById('btn-measure')?.classList.remove('active');
        break;
    }
  });

  // Start render loop
  _animate();
}

// ── Lighting ──────────────────────────────────────────────────────────────────
function _setupLights() {
  // Soft ambient
  scene.add(new THREE.AmbientLight(0xfff5e4, 0.4));

  // Hemisphere — warm sky, cool ground
  scene.add(new THREE.HemisphereLight(0xffeedd, 0x334455, 0.5));

  // Key light (front-top, overhead lamp to match scanning setup)
  const key = new THREE.DirectionalLight(0xffffff, 1.2);
  key.position.set(0, 400, 200);
  key.castShadow = true;
  key.shadow.mapSize.set(1024, 1024);
  scene.add(key);

  // Fill light (left-side, softer)
  const fill = new THREE.DirectionalLight(0xe8f0ff, 0.4);
  fill.position.set(-300, 100, 100);
  scene.add(fill);

  // Rim light (back, highlights silhouette)
  const rim = new THREE.DirectionalLight(0xffffff, 0.25);
  rim.position.set(0, 50, -400);
  scene.add(rim);
}

// ── Environment map (procedural, no file) ─────────────────────────────────────
function _setupEnvironment() {
  const pmrem = new THREE.PMREMGenerator(renderer);
  pmrem.compileEquirectangularShader();

  // Simple gradient environment via a RoomEnvironment-like approach
  const envScene = new THREE.Scene();
  envScene.background = new THREE.Color(0x1a1a2e);
  // Add emissive geometry for ambient light contribution
  const boxGeo = new THREE.BoxGeometry(2000, 2000, 2000);
  const boxMat = new THREE.MeshStandardMaterial({
    color: 0x334466, side: THREE.BackSide, emissive: 0x223355, emissiveIntensity: 0.3,
  });
  envScene.add(new THREE.Mesh(boxGeo, boxMat));

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

  // Draco compression support
  const draco = new DRACOLoader();
  draco.setDecoderPath('https://cdn.jsdelivr.net/npm/three@0.160.0/examples/jsm/libs/draco/');
  loader.setDRACOLoader(draco);

  loader.load(url,
    (gltf) => {
      bodyMesh = gltf.scene;
      _applyDefaultMaterial(bodyMesh);
      _centerAndScale(bodyMesh);
      scene.add(bodyMesh);
      _updateStats(bodyMesh);
      _setStatus('');
      _createRegionLabels();
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
      // Only override if no useful embedded material (GLB skin material is MeshStandardMaterial)
      if (!child.material || child.material.type === 'MeshBasicMaterial') {
        child.material = SKIN_MATERIAL.clone();
        _originalMaterials.set(child, child.material);
      }
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
  if (el) el.textContent = msg;
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
  if (bodyMesh) {
    const box = new THREE.Box3().setFromObject(bodyMesh);
    const size = new THREE.Vector3();
    box.getSize(size);
    const maxDim = Math.max(size.x, size.y, size.z);
    const fov = camera.fov * (Math.PI / 180);
    const camZ = maxDim / (2 * Math.tan(fov / 2)) * 1.6;
    const midY = size.y * 0.45;
    camera.position.set(0, midY, camZ);
    controls.target.set(0, midY, 0);
  } else {
    camera.position.set(0, 150, 400);
    controls.target.set(0, 80, 0);
  }
  controls.update();
};

window.takeScreenshot = function() {
  // Render at 2× resolution for sharper export
  const w = renderer.domElement.width;
  const h = renderer.domElement.height;
  renderer.setSize(w * 2, h * 2, false);
  renderer.render(scene, camera);
  const dataUrl = renderer.domElement.toDataURL('image/png');
  renderer.setSize(w, h, false);
  renderer.render(scene, camera);
  const link = document.createElement('a');
  link.download = `muscle_tracker_3d_${Date.now()}.png`;
  link.href = dataUrl;
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
function _animate() {
  requestAnimationFrame(_animate);
  controls.update();
  renderer.render(scene, camera);
  _updateRegionLabels();
}

function _onResize() {
  camera.aspect = window.innerWidth / window.innerHeight;
  camera.updateProjectionMatrix();
  renderer.setSize(window.innerWidth, window.innerHeight);
}

// ── Boot ──────────────────────────────────────────────────────────────────────
init();
