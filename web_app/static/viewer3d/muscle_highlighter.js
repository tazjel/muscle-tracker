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

// ── Public API ────────────────────────────────────────────────────────────────
// Expose group list for external use
export { MUSCLE_GROUPS, MUSCLE_LABELS };
