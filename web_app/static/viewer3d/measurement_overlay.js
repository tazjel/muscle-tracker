/**
 * MeasurementOverlay
 * ─────────────────────────────────────────────────────────────────
 * Renders interactive HTML measurement pins on top of the Three.js viewer.
 * Relies on window.bodyViewer being set by body_viewer.js:
 *   { scene, camera, renderer, mesh, getMeshIntersection(event) }
 *
 * Usage:
 *   MeasurementOverlay.init(document.getElementById('canvas-container'));
 *
 * Interaction:
 *   Click 1 → places first pin (blue)
 *   Click 2 → places second pin (green), draws dashed line + distance badge
 *   Click 3 → clears previous, starts new measurement
 */

const MeasurementOverlay = (() => {
  let _container = null;
  let _tooltip   = null;
  let _badge     = null;
  let _line      = null;
  let _animFrame = null;

  const _pins = [];       // [{worldPos: THREE.Vector3, el: HTMLElement}]

  // ── Helpers ──────────────────────────────────────────────────────────────

  function _worldToScreen(worldPos) {
    if (!window.bodyViewer) return { x: 0, y: 0, visible: false };
    const v = worldPos.clone();
    v.project(window.bodyViewer.camera);
    const canvas = window.bodyViewer.renderer.domElement;
    return {
      x: (v.x *  0.5 + 0.5) * canvas.clientWidth,
      y: (v.y * -0.5 + 0.5) * canvas.clientHeight,
      visible: v.z < 1.0,
    };
  }

  function _dist3D(a, b) {
    return a.distanceTo(b);   // result is in mesh units (mm for this project)
  }

  function _fmtDist(mm) {
    if (mm < 10)  return `${mm.toFixed(1)} mm`;
    if (mm < 100) return `${(mm / 10).toFixed(1)} cm`;
    return `${(mm / 10).toFixed(0)} cm`;
  }

  // ── DOM factory helpers ──────────────────────────────────────────────────

  function _makePin(isSecond) {
    const el = document.createElement('div');
    el.className = 'measurement-pin' + (isSecond ? ' second' : '');
    _container.appendChild(el);
    return el;
  }

  function _makeLine() {
    const el = document.createElement('div');
    el.className = 'measurement-line';
    _container.appendChild(el);
    return el;
  }

  function _makeBadge() {
    const el = document.createElement('div');
    el.className = 'measurement-badge';
    _container.appendChild(el);
    return el;
  }

  function _makeTooltip() {
    const el = document.createElement('div');
    el.className = 'measurement-tooltip';
    el.innerHTML = '<span class="tip-label">Point</span><span class="tip-value">—</span>';
    _container.appendChild(el);
    return el;
  }

  // ── Pin placement ─────────────────────────────────────────────────────────

  function _placePin(worldPos) {
    if (_pins.length >= 2) _clearPins();

    const isSecond = _pins.length === 1;
    const el = _makePin(isSecond);
    _pins.push({ worldPos, el });

    if (_pins.length === 2) {
      _drawMeasurement(_pins[0], _pins[1]);
    }
  }

  function _clearPins() {
    _pins.forEach(p => p.el && p.el.remove());
    _pins.length = 0;
    if (_line)  { _line.remove();  _line  = null; }
    if (_badge) { _badge.remove(); _badge = null; }
  }

  // ── Measurement line + badge ──────────────────────────────────────────────

  function _drawMeasurement(pinA, pinB) {
    if (_line)  { _line.remove();  }
    if (_badge) { _badge.remove(); }
    _line  = _makeLine();
    _badge = _makeBadge();
    const dist = _dist3D(pinA.worldPos, pinB.worldPos);
    _badge.textContent = _fmtDist(dist);
  }

  function _updateLine(pinA, pinB) {
    if (!_line || !_badge) return;
    const sa = _worldToScreen(pinA.worldPos);
    const sb = _worldToScreen(pinB.worldPos);

    if (!sa.visible || !sb.visible) {
      _line.style.display  = 'none';
      _badge.style.display = 'none';
      return;
    }
    _line.style.display  = '';
    _badge.style.display = '';

    const dx = sb.x - sa.x;
    const dy = sb.y - sa.y;
    const len = Math.sqrt(dx * dx + dy * dy);
    const angle = Math.atan2(dy, dx) * 180 / Math.PI;

    _line.style.left      = `${sa.x}px`;
    _line.style.top       = `${sa.y}px`;
    _line.style.width     = `${len}px`;
    _line.style.transform = `rotate(${angle}deg)`;

    _badge.style.left = `${(sa.x + sb.x) / 2}px`;
    _badge.style.top  = `${(sa.y + sb.y) / 2}px`;
  }

  // ── Per-frame update loop ─────────────────────────────────────────────────

  function _update() {
    _pins.forEach((pin, i) => {
      const s = _worldToScreen(pin.worldPos);
      pin.el.style.left    = `${s.x}px`;
      pin.el.style.top     = `${s.y}px`;
      pin.el.style.display = s.visible ? '' : 'none';
    });

    if (_pins.length === 2) {
      _updateLine(_pins[0], _pins[1]);
    }

    _animFrame = requestAnimationFrame(_update);
  }

  // ── Tooltip on mousemove ──────────────────────────────────────────────────

  function _onMouseMove(e) {
    if (!window.bodyViewer || !_tooltip) return;
    const hit = window.bodyViewer.getMeshIntersection(e);
    if (!hit) { _tooltip.classList.remove('visible'); return; }

    const rect = _container.getBoundingClientRect();
    const mx = e.clientX - rect.left;
    const my = e.clientY - rect.top;

    // Keep tooltip inside container
    const ttW = 160, ttH = 56;
    const tx = Math.min(mx + 14, rect.width  - ttW - 4);
    const ty = Math.min(my + 14, rect.height - ttH - 4);

    _tooltip.style.left = `${tx}px`;
    _tooltip.style.top  = `${ty}px`;

    const p = hit.point;
    _tooltip.querySelector('.tip-label').textContent =
      _pins.length === 0 ? 'Click to place pin A' :
      _pins.length === 1 ? 'Click to place pin B' : 'Click to start new';
    _tooltip.querySelector('.tip-value').textContent =
      `(${p.x.toFixed(0)}, ${p.y.toFixed(0)}, ${p.z.toFixed(0)}) mm`;
    _tooltip.classList.add('visible');
  }

  function _onMouseLeave() {
    if (_tooltip) _tooltip.classList.remove('visible');
  }

  // ── Click handler ─────────────────────────────────────────────────────────

  function _onClick(e) {
    if (!window.bodyViewer) return;
    const hit = window.bodyViewer.getMeshIntersection(e);
    if (!hit) return;
    _placePin(hit.point.clone());
  }

  // ── Public API ────────────────────────────────────────────────────────────

  function init(container) {
    _container = container;
    _tooltip   = _makeTooltip();

    _container.addEventListener('click',      _onClick);
    _container.addEventListener('mousemove',  _onMouseMove);
    _container.addEventListener('mouseleave', _onMouseLeave);

    _update();
  }

  function clear() { _clearPins(); }

  function destroy() {
    _clearPins();
    if (_tooltip)   { _tooltip.remove(); _tooltip = null; }
    if (_animFrame) { cancelAnimationFrame(_animFrame); _animFrame = null; }
    if (_container) {
      _container.removeEventListener('click',      _onClick);
      _container.removeEventListener('mousemove',  _onMouseMove);
      _container.removeEventListener('mouseleave', _onMouseLeave);
    }
  }

  return { init, clear, destroy };
})();
