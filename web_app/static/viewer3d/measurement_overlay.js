/**
 * Measurement Overlay Module V6
 * Adds interactive multi-measurement pins, persistent labels, angle mode, clipboard export,
 * body region hover detection, live summary panel, and localStorage persistence.
 */

const MeasurementOverlay = {
    container: null,
    measurements: [],       // Array of {pinA, pinB, lineEl, labelEl, distance_mm, name}
    pendingPin: null,        // Single pin waiting for its pair, or null
    maxMeasurements: 5,
    tooltip: null,
    summaryPanel: null,
    
    angleMode: false,
    pendingAnglePins: [],   // Collects up to 3 pins for angle measurement
    _angleMeasurement: null, // {pins, lines, label, angle}
    _meshBounds: null,       // Cached bounds for region detection

    init(container) {
        this.container = container;
        this.tooltip = document.createElement('div');
        this.tooltip.className = 'measurement-tooltip';
        this.container.appendChild(this.tooltip);

        this.summaryPanel = document.createElement('div');
        this.summaryPanel.className = 'measurement-summary';
        this.summaryPanel.innerHTML = '<h4>Measurements</h4><ul></ul>';
        this.container.appendChild(this.summaryPanel);

        this.container.addEventListener('click', (e) => {
            if (e.target.closest('#ui-overlay') || e.target.classList.contains('measurement-pin') || e.target.closest('.measurement-summary')) {
                return;
            }
            if (window.bodyViewer && window.bodyViewer.getMeshIntersection) {
                const hit = window.bodyViewer.getMeshIntersection(e);
                if (hit && hit.point) {
                    if (this.angleMode) { this._placeAnglePin(hit.point); }
                    else { this.placePin(hit.point); }
                }
            }
        });

        this.mouseX = 0; this.mouseY = 0;
        let _hoverThrottle = 0;
        this.container.addEventListener('mousemove', (e) => {
            this.mouseX = e.clientX; this.mouseY = e.clientY;
            if (this.tooltip.style.display === 'block') {
                this.tooltip.style.left = (this.mouseX + 15) + 'px';
                this.tooltip.style.top = (this.mouseY + 15) + 'px';
            }
            const now = Date.now();
            if (now - _hoverThrottle < 80) return;
            _hoverThrottle = now;
            if (!window.bodyViewer || !window.bodyViewer.getMeshIntersection) return;
            if (this.pendingPin || (this.angleMode && this.pendingAnglePins.length > 0)) return;
            const hit = window.bodyViewer.getMeshIntersection(e);
            if (hit && hit.point) {
                const region = this._getBodyRegion(hit.point);
                if (region) { this.showTooltip(e.clientX, e.clientY, { label: 'Region', value: region }); }
            } else if (this.tooltip.innerHTML.includes('Region:')) {
                this.hideTooltip();
            }
        });

        this._restoreFromStorage();
        this.update();
    },    _getBodyRegion(worldPos) {
        if (!window.bodyViewer || !window.bodyViewer.mesh) return null;
        if (!this._meshBounds) {
            let minY = Infinity, maxY = -Infinity, minX = Infinity, maxX = -Infinity;
            window.bodyViewer.mesh.traverse(child => {
                if (!child.isMesh || !child.geometry) return;
                const pos = child.geometry.attributes.position;
                for (let i = 0; i < pos.count; i++) {
                    const y = pos.getY(i), x = pos.getX(i);
                    if (y < minY) minY = y; if (y > maxY) maxY = y;
                    if (x < minX) minX = x; if (x > maxX) maxX = x;
                }
            });
            this._meshBounds = { minY, maxY, rangeY: maxY - minY, halfW: (maxX - minX) / 2 };
        }
        const b = this._meshBounds; if (b.rangeY < 1) return null;
        const ratio = (worldPos.y - b.minY) / b.rangeY;
        const xRatio = Math.abs(worldPos.x) / (b.halfW || 1);
        if (ratio > 0.92) return 'Head'; if (ratio > 0.85) return 'Neck';
        if (ratio > 0.78) return xRatio > 0.6 ? 'Shoulder' : 'Upper Chest';
        if (ratio > 0.65) return xRatio > 0.7 ? 'Upper Arm' : (ratio > 0.72 ? 'Chest' : 'Waist');
        if (ratio > 0.55) return xRatio > 0.7 ? 'Forearm' : 'Hip';
        if (ratio > 0.45) return 'Upper Thigh'; if (ratio > 0.30) return 'Thigh';
        if (ratio > 0.15) return 'Calf'; if (ratio > 0.05) return 'Ankle';
        return 'Foot';
    },

    toggleAngleMode() {
        this.angleMode = !this.angleMode; this.pendingAnglePins = [];
        const btn = document.getElementById('btn-measure-angle');
        if (btn) btn.classList.toggle('active', this.angleMode);
    },

    placePin(worldPosition) {
        if (this.pendingPin === null) {
            if (this.measurements.length >= this.maxMeasurements) this._removeMeasurement(0);
            const pinEl = this._createPinElement();
            this.pendingPin = { worldPos: worldPosition.clone(), element: pinEl };
        } else {
            const pinEl = this._createPinElement();
            const pinB = { worldPos: worldPosition.clone(), element: pinEl };
            const lineEl = document.createElement('div'); lineEl.className = 'measurement-line'; this.container.appendChild(lineEl);
            const labelEl = document.createElement('div'); labelEl.className = 'measurement-label'; this.container.appendChild(labelEl);
            const dist = this.pendingPin.worldPos.distanceTo(pinB.worldPos);
            const formatted = dist >= 100 ? (dist / 10).toFixed(1) + ' cm' : dist.toFixed(1) + ' mm';
            labelEl.textContent = formatted;
            const m = { pinA: this.pendingPin, pinB: pinB, lineEl, labelEl, distance_mm: dist, name: '' };
            this.measurements.push(m); this.pendingPin = null;
            const idx = this.measurements.length - 1;
            labelEl.addEventListener('dblclick', (ev) => { ev.stopPropagation(); this._renameMeasurement(idx); });
            this._updateSummary(); this._saveToStorage();
        }
    },

    _renameMeasurement(idx) {
        const m = this.measurements[idx]; if (!m) return;
        const labelEl = m.labelEl;
        const input = document.createElement('input');
        input.type = 'text'; input.className = 'measurement-name-input';
        input.value = m.name || ''; input.placeholder = 'Name this measurement';
        input.style.cssText = 'width:100px;font-size:11px;background:#1e2035;color:#e0e0e0;border:1px solid #4a9eff;border-radius:3px;padding:2px 4px;text-align:center;';
        labelEl.textContent = ''; labelEl.appendChild(input); input.focus(); input.select();
        const commit = () => {
            m.name = input.value.trim();
            const formatted = m.distance_mm >= 100 ? (m.distance_mm / 10).toFixed(1) + ' cm' : m.distance_mm.toFixed(1) + ' mm';
            labelEl.textContent = m.name ? `${m.name}: ${formatted}` : formatted;
            this._updateSummary(); this._saveToStorage();
        };
        input.addEventListener('blur', commit);
        input.addEventListener('keydown', (e) => {
            if (e.key === 'Enter') { commit(); input.blur(); }
            if (e.key === 'Escape') { input.blur(); }
        });
    },    _placeAnglePin(worldPos) {
        if (this.pendingAnglePins.length >= 3) this._clearAnglePins();
        const el = this._createPinElement(); el.classList.add('angle-pin');
        this.pendingAnglePins.push({ worldPos: worldPos.clone(), element: el });
        if (this.pendingAnglePins.length === 3) {
            const A = this.pendingAnglePins[0].worldPos, B = this.pendingAnglePins[1].worldPos, C = this.pendingAnglePins[2].worldPos;
            const BA = A.clone().sub(B), BC = C.clone().sub(B);
            const angleDeg = (Math.acos(Math.max(-1, Math.min(1, BA.dot(BC) / (BA.length() * BC.length() || 1)))) * 180 / Math.PI).toFixed(1);
            const l1 = document.createElement('div'); l1.className = 'measurement-line angle-line'; this.container.appendChild(l1);
            const l2 = document.createElement('div'); l2.className = 'measurement-line angle-line'; this.container.appendChild(l2);
            const label = document.createElement('div'); label.className = 'measurement-label angle-label'; label.textContent = angleDeg + '°'; this.container.appendChild(label);
            this._angleMeasurement = { pins: this.pendingAnglePins.slice(), lines: [l1, l2], label, angle: parseFloat(angleDeg) };
            this._updateSummary(); this._saveToStorage();
        }
    },

    _clearAnglePins() {
        for (const p of this.pendingAnglePins) p.element.remove();
        this.pendingAnglePins = [];
        if (this._angleMeasurement) { this._angleMeasurement.lines.forEach(l => l.remove()); this._angleMeasurement.label.remove(); this._angleMeasurement = null; }
        this._updateSummary(); this._saveToStorage();
    },

    _createPinElement() {
        const el = document.createElement('div'); el.className = 'measurement-pin';
        el.addEventListener('click', (e) => {
            e.stopPropagation();
            const idx = this.measurements.findIndex(m => m.pinA.element === el || m.pinB.element === el);
            if (idx >= 0) { this._removeMeasurement(idx); return; }
            if (this.pendingPin && this.pendingPin.element === el) { el.remove(); this.pendingPin = null; this._updateSummary(); this._saveToStorage(); return; }
            if (this._angleMeasurement && this._angleMeasurement.pins.some(p => p.element === el)) { this._clearAnglePins(); return; }
            const aIdx = this.pendingAnglePins.findIndex(p => p.element === el);
            if (aIdx >= 0) this._clearAnglePins();
        });
        this.container.appendChild(el); return el;
    },

    _removeMeasurement(index) {
        const m = this.measurements[index]; if (!m) return;
        m.pinA.element.remove(); m.pinB.element.remove(); m.lineEl.remove(); m.labelEl.remove();
        this.measurements.splice(index, 1); this._updateSummary(); this._saveToStorage();
    },

    _updateSummary() {
        if (!this.summaryPanel) return;
        const ul = this.summaryPanel.querySelector('ul'); if (!ul) return;
        ul.innerHTML = '';
        this.measurements.forEach((m, i) => {
            const dist = m.distance_mm;
            const formatted = dist >= 100 ? (dist / 10).toFixed(1) + ' cm' : dist.toFixed(1) + ' mm';
            const label = m.name ? `${m.name}: ${formatted}` : formatted;
            const li = document.createElement('li');
            li.innerHTML = `<span class="msr-idx">${i + 1}</span> ${label} <span class="msr-del">×</span>`;
            li.addEventListener('click', () => this._highlightMeasurement(i));
            li.querySelector('.msr-del').addEventListener('click', (ev) => { ev.stopPropagation(); this._removeMeasurement(i); });
            ul.appendChild(li);
        });
        if (this._angleMeasurement) {
            const li = document.createElement('li');
            li.innerHTML = `<span class="msr-idx">∠</span> ${this._angleMeasurement.angle}° <span class="msr-del">×</span>`;
            li.querySelector('.msr-del').addEventListener('click', (ev) => { ev.stopPropagation(); this._clearAnglePins(); });
            ul.appendChild(li);
        }
        this.summaryPanel.style.display = (this.measurements.length > 0 || this._angleMeasurement) ? 'block' : 'none';
    },

    _highlightMeasurement(idx) {
        const m = this.measurements[idx]; if (!m) return;
        [m.pinA.element, m.pinB.element].forEach(el => { el.classList.add('pin-highlight'); setTimeout(() => el.classList.remove('pin-highlight'), 800); });
        if (m.labelEl) { m.labelEl.classList.add('label-highlight'); setTimeout(() => m.labelEl.classList.remove('label-highlight'), 800); }
    },    _saveToStorage() {
        try {
            const data = {
                measurements: this.measurements.map(m => ({
                    a: {x: m.pinA.worldPos.x, y: m.pinA.worldPos.y, z: m.pinA.worldPos.z},
                    b: {x: m.pinB.worldPos.x, y: m.pinB.worldPos.y, z: m.pinB.worldPos.z},
                    distance_mm: m.distance_mm, name: m.name || '',
                })),
                angle: this._angleMeasurement ? {
                    pins: this._angleMeasurement.pins.map(p => ({ x: p.worldPos.x, y: p.worldPos.y, z: p.worldPos.z })),
                    angle: this._angleMeasurement.angle,
                } : null,
            };
            localStorage.setItem('gtd3d_measurements', JSON.stringify(data));
        } catch (e) {}
    },

    _restoreFromStorage() {
        try {
            const raw = localStorage.getItem('gtd3d_measurements'); if (!raw) return;
            const data = JSON.parse(raw);
            if (data.measurements) for (const m of data.measurements) { if (this.measurements.length >= this.maxMeasurements) break; this._restoreMeasurement(m.a, m.b, m.distance_mm, m.name || ''); }
            if (data.angle && data.angle.pins && data.angle.pins.length === 3) { this.angleMode = true; for (const p of data.angle.pins) this._placeAnglePin(this._vec3(p)); this.angleMode = false; }
            this._updateSummary();
        } catch (e) {}
    },

    _restoreMeasurement(posA, posB, distance_mm, name) {
        const elA = this._createPinElement(); const elB = this._createPinElement();
        const lineEl = document.createElement('div'); lineEl.className = 'measurement-line'; this.container.appendChild(lineEl);
        const labelEl = document.createElement('div'); labelEl.className = 'measurement-label';
        const formatted = distance_mm >= 100 ? (distance_mm / 10).toFixed(1) + ' cm' : distance_mm.toFixed(1) + ' mm';
        labelEl.textContent = name ? `${name}: ${formatted}` : formatted; this.container.appendChild(labelEl);
        const m = { pinA: { worldPos: this._vec3(posA), element: elA }, pinB: { worldPos: this._vec3(posB), element: elB }, lineEl, labelEl, distance_mm, name: name || '' };
        this.measurements.push(m);
        const idx = this.measurements.length - 1;
        labelEl.addEventListener('dblclick', (ev) => { ev.stopPropagation(); this._renameMeasurement(idx); });
    },

    _vec3(obj) {
        const v = {x: obj.x, y: obj.y, z: obj.z};
        v.clone = () => this._vec3(v);
        v.sub = (o) => this._vec3({x: v.x - o.x, y: v.y - o.y, z: v.z - o.z});
        v.dot = (o) => v.x*o.x + v.y*o.y + v.z*o.z;
        v.length = () => Math.sqrt(v.x*v.x + v.y*v.y + v.z*v.z);
        return v;
    },

    projectToScreen(worldPos) {
        if (!window.bodyViewer || !window.bodyViewer.camera || !window.bodyViewer.renderer) return { x: 0, y: 0, visible: false };
        const v = worldPos.clone();
        if (v.project) v.project(window.bodyViewer.camera);
        else { const v3 = new THREE.Vector3(v.x, v.y, v.z); v3.project(window.bodyViewer.camera); v.x = v3.x; v.y = v3.y; v.z = v3.z; }
        const c = window.bodyViewer.renderer.domElement;
        return { x: (v.x * 0.5 + 0.5) * c.clientWidth, y: (-v.y * 0.5 + 0.5) * c.clientHeight, visible: v.z < 1 };
    },

    update() {
        if (this.pendingPin) {
            const s = this.projectToScreen(this.pendingPin.worldPos);
            this.pendingPin.element.style.display = s.visible ? 'block' : 'none';
            this.pendingPin.element.style.left = s.x + 'px'; this.pendingPin.element.style.top = s.y + 'px';
        }
        for (const m of this.measurements) {
            const pA = this.projectToScreen(m.pinA.worldPos); const pB = this.projectToScreen(m.pinB.worldPos);
            m.pinA.element.style.display = pA.visible ? 'block' : 'none'; m.pinA.element.style.left = pA.x + 'px'; m.pinA.element.style.top = pA.y + 'px';
            m.pinB.element.style.display = pB.visible ? 'block' : 'none'; m.pinB.element.style.left = pB.x + 'px'; m.pinB.element.style.top = pB.y + 'px';
            const both = pA.visible && pB.visible; m.lineEl.style.display = both ? 'block' : 'none';
            if (both) {
                const dx = pB.x - pA.x, dy = pB.y - pA.y;
                m.lineEl.style.width = Math.sqrt(dx*dx + dy*dy) + 'px'; m.lineEl.style.left = pA.x + 'px'; m.lineEl.style.top = pA.y + 'px'; m.lineEl.style.transform = `rotate(${Math.atan2(dy, dx)}rad)`;
            }
            m.labelEl.style.display = both ? 'block' : 'none';
            if (both) { m.labelEl.style.left = ((pA.x + pB.x) / 2) + 'px'; m.labelEl.style.top = ((pA.y + pB.y) / 2 - 20) + 'px'; }
        }
        for (const p of this.pendingAnglePins) {
            const s = this.projectToScreen(p.worldPos); p.element.style.display = s.visible ? 'block' : 'none'; p.element.style.left = s.x + 'px'; p.element.style.top = s.y + 'px';
        }
        if (this._angleMeasurement) {
            const am = this._angleMeasurement; const sA = this.projectToScreen(am.pins[0].worldPos); const sB = this.projectToScreen(am.pins[1].worldPos); const sC = this.projectToScreen(am.pins[2].worldPos);
            const all = sA.visible && sB.visible && sC.visible; am.lines[0].style.display = all ? 'block' : 'none'; am.lines[1].style.display = all ? 'block' : 'none';
            if (all) {
                let dx = sB.x - sA.x, dy = sB.y - sA.y; am.lines[0].style.width = Math.sqrt(dx*dx+dy*dy)+'px'; am.lines[0].style.left = sA.x+'px'; am.lines[0].style.top = sA.y+'px'; am.lines[0].style.transform = `rotate(${Math.atan2(dy,dx)}rad)`;
                dx = sC.x - sB.x; dy = sC.y - sB.y; am.lines[1].style.width = Math.sqrt(dx*dx+dy*dy)+'px'; am.lines[1].style.left = sB.x+'px'; am.lines[1].style.top = sB.y+'px'; am.lines[1].style.transform = `rotate(${Math.atan2(dy,dx)}rad)`;
            }
            am.label.style.display = all ? 'block' : 'none'; if (all) { am.label.style.left = sB.x+'px'; am.label.style.top = (sB.y-25)+'px'; }
        }
        requestAnimationFrame(() => this.update());
    },

    copyToClipboard() {
        const lines = []; this.measurements.forEach((m, i) => { const dist = m.distance_mm; const formatted = dist >= 100 ? (dist / 10).toFixed(1) + ' cm' : dist.toFixed(1) + ' mm'; const label = m.name || `Distance ${i + 1}`; lines.push(`${label}: ${formatted}`); });
        if (this._angleMeasurement) lines.push(`Angle: ${this._angleMeasurement.angle}°`);
        const text = 'GTD3D Measurements\n' + (lines.length ? lines.join('\n') : 'No measurements');
        navigator.clipboard.writeText(text).then(() => { this.showTooltip(window.innerWidth / 2, 60, { label: 'Copied', value: lines.length + ' measurement(s)' }); setTimeout(() => this.hideTooltip(), 1500); }).catch(() => { const ta = document.createElement('textarea'); ta.value = text; ta.style.cssText = 'position:fixed;opacity:0'; document.body.appendChild(ta); ta.select(); document.execCommand('copy'); ta.remove(); });
    },

    showTooltip(screenX, screenY, data) {
        if (!this.tooltip) return; this.tooltip.innerHTML = `<span class="label">${data.label}:</span> <span class="value">${data.value}</span>`;
        this.tooltip.style.display = 'block'; this.tooltip.style.left = (screenX + 15) + 'px'; this.tooltip.style.top = (screenY + 15) + 'px';
    },

    hideTooltip() { if (this.tooltip) this.tooltip.style.display = 'none'; },

    clear() {
        while (this.measurements.length > 0) this._removeMeasurement(0);
        if (this.pendingPin) { this.pendingPin.element.remove(); this.pendingPin = null; }
        this._clearAnglePins(); this.angleMode = false; this._meshBounds = null; this.hideTooltip(); this._updateSummary(); this._saveToStorage();
    },
};