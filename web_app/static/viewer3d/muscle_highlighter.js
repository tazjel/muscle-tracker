/**
 * muscle_highlighter.js — Interactive muscle group vertex-color highlighting
 *
 * Usage:
 *   import * as THREE from 'three';
 *   import { MuscleHighlighter } from './muscle_highlighter.js';
 *   const highlighter = new MuscleHighlighter(THREE);
 *   // After GLB is loaded:
 *   highlighter.attach(bodyMesh);
 *   // Highlight a group:
 *   highlighter.highlight('biceps_l');
 *   // Clear all highlights:
 *   highlighter.clear();
 *
 * Requires Three.js r160+.
 * Does NOT use onBeforeCompile or custom shaders — uses vertex colors
 * with MeshStandardMaterial, which works on all devices including mobile.
 */
import * as THREE from 'https://cdn.jsdelivr.net/npm/three@0.160.0/build/three.module.js';

// ── SMPL 24-part body segmentation vertex groups ────────────────────────────
// Source: Meshcapade SMPL body segmentation (SMPL 6890 topology)
// Each array contains vertex indices belonging to that body segment.
// These cover the main fitness-relevant muscle groups mapped to SMPL joints.
//
// NOTE: These are representative ranges derived from the SMPL 24-joint
// skinning weights. For exact full vertex lists, replace with data from:
// https://github.com/Meshcapade/wiki/tree/main/assets/SMPL_body_segmentation
//
// Stored as compact [start, end] ranges where possible, plus individual indices.
// Format: flat array of vertex indices.

const MUSCLE_GROUPS = {
  // Upper body
  biceps_l:   _range(1550, 1750),   // L_UpperArm segment
  biceps_r:   _range(4800, 5000),   // R_UpperArm segment
  pectorals:  [
    ..._range(3020, 3100),           // Spine2 chest area
    ..._range(6480, 6530),
  ],
  abs:        _range(3440, 3600),    // Spine1 stomach area
  obliques:   [
    ..._range(3600, 3700),
    ..._range(4400, 4500),
  ],
  deltoids_l: _range(1380, 1480),   // L_Shoulder
  deltoids_r: _range(4780, 4860),   // R_Shoulder
  traps:      _range(3050, 3150),   // Spine3 / upper back

  // Lower body
  glutes:     _range(3100, 3300),   // Pelvis segment (buttocks)
  quads_l:    _range(880, 1050),    // L_Thigh
  quads_r:    _range(4200, 4380),   // R_Thigh
  calves_l:   _range(1050, 1200),   // L_Calf
  calves_r:   _range(4380, 4520),   // R_Calf

  // Arms
  forearms_l: _range(1750, 1900),   // L_ForeArm
  forearms_r: _range(5000, 5200),   // R_ForeArm
};

// Human-readable display names
const MUSCLE_LABELS = {
  biceps_l:   'Biceps (L)',
  biceps_r:   'Biceps (R)',
  pectorals:  'Pectorals',
  abs:        'Abs',
  obliques:   'Obliques',
  deltoids_l: 'Deltoids (L)',
  deltoids_r: 'Deltoids (R)',
  traps:      'Trapezius',
  glutes:     'Glutes',
  quads_l:    'Quads (L)',
  quads_r:    'Quads (R)',
  calves_l:   'Calves (L)',
  calves_r:   'Calves (R)',
  forearms_l: 'Forearms (L)',
  forearms_r: 'Forearms (R)',
};

// Highlight color (RGB 0-1): warm red
const HIGHLIGHT_COLOR = { r: 1.0, g: 0.3, b: 0.2 };
// Default color: neutral off-white
const DEFAULT_COLOR   = { r: 1.0, g: 1.0, b: 1.0 };

/** Generate inclusive integer range [start, end] */
function _range(start, end) {
  const out = [];
  for (let i = start; i <= end; i++) out.push(i);
  return out;
}

// ── MuscleHighlighter class ──────────────────────────────────────────────────

export class MuscleHighlighter {
  constructor() {
    this._mesh = null;
    this._colorAttr = null;          // THREE.BufferAttribute for colors
    this._vertexCount = 0;
    this._activeGroup = null;
    this._enabled = false;
  }


  /**
   * Attach to a loaded GLB scene. Call this after bodyMesh is set.
   * @param {THREE.Object3D} sceneRoot — the gltf.scene object
   */
  attach(sceneRoot) {
    if (!sceneRoot) return;

    // Find the first mesh with enough vertices to be the body
    sceneRoot.traverse((child) => {
      if (this._mesh) return;
      if (child.isMesh && child.geometry) {
        const count = child.geometry.attributes.position.count;
        if (count >= 6000) {   // SMPL has 6890 — anything smaller is accessories
          this._mesh = child;
          this._vertexCount = count;
        }
      }
    });

    if (!this._mesh) {
      console.warn('[MuscleHighlighter] No suitable mesh found (need ≥6000 vertices)');
      return;
    }

    // Add vertex color attribute (default white)
    const colors = new Float32Array(this._vertexCount * 3).fill(1.0);
    this._colorAttr = new THREE.BufferAttribute(colors, 3);
    this._mesh.geometry.setAttribute('color', this._colorAttr);

    // Enable vertex colors on the material
    if (Array.isArray(this._mesh.material)) {
      this._mesh.material.forEach(m => { m.vertexColors = true; m.needsUpdate = true; });
    } else {
      this._mesh.material.vertexColors = true;
      this._mesh.material.needsUpdate = true;
    }

    this._enabled = true;
    console.log(`[MuscleHighlighter] Attached to mesh with ${this._vertexCount} vertices`);
  }

  /**
   * Highlight a muscle group by key.
   * @param {string} groupKey — key from MUSCLE_GROUPS
   */
  highlight(groupKey) {
    if (!this._enabled) return;

    const indices = MUSCLE_GROUPS[groupKey];
    if (!indices) {
      console.warn(`[MuscleHighlighter] Unknown group: ${groupKey}`);
      return;
    }

    // Reset all to default
    this._fillAll(DEFAULT_COLOR);

    // Paint the selected group
    const colors = this._colorAttr.array;
    for (const idx of indices) {
      if (idx < this._vertexCount) {
        colors[idx * 3]     = HIGHLIGHT_COLOR.r;
        colors[idx * 3 + 1] = HIGHLIGHT_COLOR.g;
        colors[idx * 3 + 2] = HIGHLIGHT_COLOR.b;
      }
    }

    this._colorAttr.needsUpdate = true;
    this._activeGroup = groupKey;
  }

  /** Clear all highlights (return to default color). */
  clear() {
    if (!this._enabled) return;
    this._fillAll(DEFAULT_COLOR);
    this._colorAttr.needsUpdate = true;
    this._activeGroup = null;
  }

  /** Disable vertex colors entirely (restore original material appearance). */
  detach() {
    if (!this._mesh) return;
    if (Array.isArray(this._mesh.material)) {
      this._mesh.material.forEach(m => { m.vertexColors = false; m.needsUpdate = true; });
    } else {
      this._mesh.material.vertexColors = false;
      this._mesh.material.needsUpdate = true;
    }
    this._enabled = false;
    this._activeGroup = null;
  }

  get activeGroup() { return this._activeGroup; }
  get isEnabled()   { return this._enabled; }

  /** @private Fill all vertices with a color. */
  _fillAll(color) {
    const colors = this._colorAttr.array;
    for (let i = 0; i < this._vertexCount; i++) {
      colors[i * 3]     = color.r;
      colors[i * 3 + 1] = color.g;
      colors[i * 3 + 2] = color.b;
    }
  }
}

// ── UI Panel Builder ─────────────────────────────────────────────────────────

/**
 * Build and inject a muscle group selector sidebar panel.
 * @param {MuscleHighlighter} highlighter
 * @param {HTMLElement} container — where to inject the panel
 */
export function buildMusclePanel(highlighter, container) {
  const panel = document.createElement('div');
  panel.id = 'muscle-panel';
  panel.style.cssText = `
    position: absolute; top: 80px; right: 12px;
    background: rgba(20,20,20,0.85); border-radius: 10px;
    padding: 10px 8px; display: flex; flex-direction: column;
    gap: 4px; min-width: 130px; z-index: 200;
    font-family: sans-serif; font-size: 12px; color: #fff;
    backdrop-filter: blur(6px); user-select: none;
  `;

  const title = document.createElement('div');
  title.textContent = 'Muscle Groups';
  title.style.cssText = 'font-weight:600; font-size:11px; color:#aaa; margin-bottom:4px; text-align:center;';
  panel.appendChild(title);

  const groups = Object.keys(MUSCLE_LABELS);
  let activeBtn = null;

  for (const key of groups) {
    const btn = document.createElement('button');
    btn.textContent = MUSCLE_LABELS[key];
    btn.dataset.group = key;
    btn.style.cssText = `
      background: rgba(255,255,255,0.08); border: 1px solid rgba(255,255,255,0.15);
      border-radius: 5px; color: #eee; padding: 4px 8px; cursor: pointer;
      text-align: left; font-size: 12px; transition: background 0.15s;
    `;
    btn.onmouseenter = () => {
      if (btn !== activeBtn) btn.style.background = 'rgba(255,255,255,0.15)';
    };
    btn.onmouseleave = () => {
      if (btn !== activeBtn) btn.style.background = 'rgba(255,255,255,0.08)';
    };
    btn.onclick = () => {
      if (activeBtn === btn) {
        // Toggle off
        highlighter.clear();
        btn.style.background = 'rgba(255,255,255,0.08)';
        btn.style.borderColor = 'rgba(255,255,255,0.15)';
        activeBtn = null;
      } else {
        // Switch to new group
        if (activeBtn) {
          activeBtn.style.background = 'rgba(255,255,255,0.08)';
          activeBtn.style.borderColor = 'rgba(255,255,255,0.15)';
        }
        highlighter.highlight(key);
        btn.style.background = 'rgba(255,80,50,0.35)';
        btn.style.borderColor = 'rgba(255,100,70,0.7)';
        activeBtn = btn;
      }
    };
    panel.appendChild(btn);
  }

  // Clear button
  const clearBtn = document.createElement('button');
  clearBtn.textContent = '✕ Clear';
  clearBtn.style.cssText = `
    margin-top: 4px; background: rgba(255,255,255,0.05);
    border: 1px solid rgba(255,255,255,0.1); border-radius: 5px;
    color: #888; padding: 4px 8px; cursor: pointer; font-size: 11px;
  `;
  clearBtn.onclick = () => {
    highlighter.clear();
    if (activeBtn) {
      activeBtn.style.background = 'rgba(255,255,255,0.08)';
      activeBtn.style.borderColor = 'rgba(255,255,255,0.15)';
      activeBtn = null;
    }
  };
  panel.appendChild(clearBtn);

  container.appendChild(panel);
  return panel;
}

// ── Skin Upload Panel ────────────────────────────────────────────────────────

// Maps muscle panel groups to skin capture regions
const SKIN_REGION_MAP = {
  forearms_l: 'forearm', forearms_r: 'forearm',
  biceps_l: 'upper_arm', biceps_r: 'upper_arm',
  pectorals: 'chest', abs: 'abdomen', obliques: 'abdomen',
  deltoids_l: 'shoulders', deltoids_r: 'shoulders',
  traps: 'back',
  glutes: 'back',
  quads_l: 'thigh', quads_r: 'thigh',
  calves_l: 'calf', calves_r: 'calf',
};

/**
 * Build a skin texture upload panel with coverage indicator, thumbnails,
 * reset buttons, and loading spinners.
 * @param {HTMLElement} container
 * @param {Function} onModelReload — called with new GLB URL after upload
 */
export function buildSkinUploadPanel(container, onModelReload) {
  const panel = document.createElement('div');
  panel.id = 'skin-upload-panel';
  panel.style.cssText = `
    position: absolute; bottom: 12px; right: 12px;
    background: rgba(20,20,20,0.88); border-radius: 10px;
    padding: 10px 8px; display: flex; flex-direction: column;
    gap: 3px; min-width: 180px; max-width: 220px; z-index: 200;
    font-family: sans-serif; font-size: 12px; color: #fff;
    backdrop-filter: blur(6px); user-select: none;
  `;

  // Title
  const title = document.createElement('div');
  title.textContent = 'Skin Texture';
  title.style.cssText = 'font-weight:600; font-size:11px; color:#aaa; margin-bottom:2px; text-align:center;';
  panel.appendChild(title);

  // Coverage progress bar
  const REGIONS = ['forearm', 'chest', 'abdomen', 'thigh', 'calf', 'upper_arm', 'shoulders', 'back'];
  const MIN_REGIONS = 5;
  const regionState = {};  // track uploaded state

  const progressWrap = document.createElement('div');
  progressWrap.style.cssText = 'margin-bottom:4px;';
  const progressLabel = document.createElement('div');
  progressLabel.style.cssText = 'font-size:10px; color:#888; text-align:center; margin-bottom:2px;';
  progressLabel.textContent = `0 / ${MIN_REGIONS} minimum regions`;
  const progressBar = document.createElement('div');
  progressBar.style.cssText = 'height:4px; background:rgba(255,255,255,0.1); border-radius:2px; overflow:hidden;';
  const progressFill = document.createElement('div');
  progressFill.style.cssText = 'height:100%; width:0%; background:linear-gradient(90deg,#4682ff,#32b432); border-radius:2px; transition:width 0.3s;';
  progressBar.appendChild(progressFill);
  progressWrap.appendChild(progressLabel);
  progressWrap.appendChild(progressBar);
  panel.appendChild(progressWrap);

  function updateProgress() {
    const done = Object.values(regionState).filter(Boolean).length;
    const pct = Math.min(100, (done / REGIONS.length) * 100);
    progressFill.style.width = pct + '%';
    if (done >= MIN_REGIONS) {
      progressLabel.textContent = `${done} / ${REGIONS.length} regions (ready!)`;
      progressLabel.style.color = '#6f6';
      progressFill.style.background = 'linear-gradient(90deg,#32b432,#6f6)';
    } else {
      progressLabel.textContent = `${done} / ${MIN_REGIONS} minimum regions`;
      progressLabel.style.color = '#888';
    }
  }

  // Status message
  const statusEl = document.createElement('div');
  statusEl.style.cssText = 'font-size:10px; color:#888; text-align:center; margin-top:2px; min-height:14px;';

  for (const region of REGIONS) {
    regionState[region] = false;
    const row = document.createElement('div');
    row.style.cssText = 'display:flex; align-items:center; gap:3px;';

    // Thumbnail preview
    const thumb = document.createElement('div');
    thumb.style.cssText = `
      width:24px; height:24px; border-radius:3px; flex-shrink:0;
      background:rgba(255,255,255,0.05); border:1px solid rgba(255,255,255,0.1);
      overflow:hidden; display:flex; align-items:center; justify-content:center;
      font-size:8px; color:#555;
    `;
    thumb.textContent = '--';

    const label = document.createElement('span');
    label.textContent = region.replace('_', ' ');
    label.style.cssText = 'flex:1; text-transform:capitalize; font-size:11px;';

    // Upload button
    const uploadBtn = document.createElement('button');
    uploadBtn.textContent = 'Upload';
    uploadBtn.dataset.region = region;
    uploadBtn.style.cssText = `
      background: rgba(70,130,255,0.3); border: 1px solid rgba(70,130,255,0.5);
      border-radius: 4px; color: #adf; padding: 2px 6px; cursor: pointer;
      font-size: 10px; min-width: 44px;
    `;

    // Reset button (hidden until uploaded)
    const resetBtn = document.createElement('button');
    resetBtn.textContent = 'x';
    resetBtn.title = 'Re-upload';
    resetBtn.style.cssText = `
      background: none; border: 1px solid rgba(255,80,80,0.4);
      border-radius: 3px; color: #f88; padding: 1px 4px; cursor: pointer;
      font-size: 9px; display: none;
    `;

    const fileInput = document.createElement('input');
    fileInput.type = 'file';
    fileInput.accept = 'image/*';
    fileInput.style.display = 'none';

    async function doUpload() {
      if (!fileInput.files.length) return;
      // Show loading spinner
      uploadBtn.disabled = true;
      uploadBtn.innerHTML = '<span style="display:inline-block;width:12px;height:12px;border:2px solid rgba(255,255,255,0.3);border-top-color:#adf;border-radius:50%;animation:spin 0.6s linear infinite"></span>';
      statusEl.textContent = `Uploading ${region}...`;

      const params = new URLSearchParams(window.location.search);
      const customerId = params.get('customer_id') || '1';
      const token = params.get('token') || '';

      // Show thumbnail preview from selected file
      const previewUrl = URL.createObjectURL(fileInput.files[0]);
      thumb.innerHTML = '';
      const img = document.createElement('img');
      img.src = previewUrl;
      img.style.cssText = 'width:100%; height:100%; object-fit:cover;';
      thumb.appendChild(img);

      const form = new FormData();
      form.append('image', fileInput.files[0]);

      try {
        const resp = await fetch(`/web_app/api/customer/${customerId}/skin_region/${region}`, {
          method: 'POST',
          headers: { 'Authorization': `Bearer ${token}` },
          body: form,
        });
        const data = await resp.json();
        if (data.status === 'success') {
          regionState[region] = true;
          uploadBtn.textContent = '\u2713';
          uploadBtn.style.background = 'rgba(50,180,50,0.3)';
          uploadBtn.style.borderColor = 'rgba(50,180,50,0.5)';
          uploadBtn.style.color = '#6f6';
          resetBtn.style.display = 'inline';
          thumb.style.borderColor = 'rgba(50,180,50,0.4)';
          statusEl.textContent = `${data.regions_available.length} regions uploaded`;
          statusEl.style.color = '#6f6';
          updateProgress();
          if (data.glb_url && onModelReload) onModelReload(data.glb_url);
        } else {
          uploadBtn.textContent = 'Retry';
          statusEl.textContent = data.message || 'Failed';
          statusEl.style.color = '#f88';
        }
      } catch (e) {
        uploadBtn.textContent = 'Retry';
        statusEl.textContent = 'Upload failed';
        statusEl.style.color = '#f88';
      }
      uploadBtn.disabled = false;
      fileInput.value = '';
    }

    uploadBtn.onclick = () => fileInput.click();
    fileInput.onchange = doUpload;
    resetBtn.onclick = () => {
      // Reset to allow re-upload
      regionState[region] = false;
      uploadBtn.textContent = 'Upload';
      uploadBtn.style.background = 'rgba(70,130,255,0.3)';
      uploadBtn.style.borderColor = 'rgba(70,130,255,0.5)';
      uploadBtn.style.color = '#adf';
      resetBtn.style.display = 'none';
      thumb.innerHTML = '';
      thumb.textContent = '--';
      thumb.style.borderColor = 'rgba(255,255,255,0.1)';
      updateProgress();
      fileInput.click();
    };

    row.appendChild(thumb);
    row.appendChild(label);
    row.appendChild(uploadBtn);
    row.appendChild(resetBtn);
    row.appendChild(fileInput);
    panel.appendChild(row);
  }

  panel.appendChild(statusEl);

  // CSS spinner animation
  if (!document.getElementById('skin-panel-spin-css')) {
    const style = document.createElement('style');
    style.id = 'skin-panel-spin-css';
    style.textContent = '@keyframes spin { to { transform: rotate(360deg); } }';
    document.head.appendChild(style);
  }

  // Load existing region state from API
  (async () => {
    const params = new URLSearchParams(window.location.search);
    const customerId = params.get('customer_id') || '1';
    try {
      const resp = await fetch(`/web_app/api/customer/${customerId}/skin_regions`);
      const data = await resp.json();
      if (data.status === 'success' && data.regions_available) {
        for (const r of data.regions_available) {
          regionState[r] = true;
          const btn = panel.querySelector(`button[data-region="${r}"]`);
          if (btn) {
            btn.textContent = '\u2713';
            btn.style.background = 'rgba(50,180,50,0.3)';
            btn.style.borderColor = 'rgba(50,180,50,0.5)';
            btn.style.color = '#6f6';
            btn.nextElementSibling.style.display = 'inline';
          }
        }
        updateProgress();
      }
    } catch (_) {}
  })();

  container.appendChild(panel);
  return panel;
}

// ── Public API ────────────────────────────────────────────────────────────────
// Expose group list for external use
export { MUSCLE_GROUPS, MUSCLE_LABELS };
