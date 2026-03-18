/**
 * Measurement Overlay Module V5
 * Adds interactive multi-measurement pins, persistent labels, angle mode, clipboard export,
 * body region hover detection, and a live summary panel.
 *
 * Usage: Sonnet's body_viewer.js will call `MeasurementOverlay.init(container)`
 *        after the viewer is ready.
 */

const MeasurementOverlay = {
    container: null,
    measurements: [],       // Array of {pinA, pinB, lineEl, labelEl, distance_mm}
    pendingPin: null,        // Single pin waiting for its pair, or null
    maxMeasurements: 5,
    tooltip: null,
    summaryPanel: null,
    
    angleMode: false,
    pendingAnglePins: [],   // Collects up to 3 pins for angle measurement
    _angleMeasurement: null, // {pins, lines, label, angle}
    _meshBounds: null,       // Cached bounds for region detection

    /**
     * Initialize the overlay system.
     */
    init(container) {
        this.container = container;

        // 1. Create tooltip element
        this.tooltip = document.createElement('div');
        this.tooltip.className = 'measurement-tooltip';
        this.container.appendChild(this.tooltip);

        // 2. Create measurement summary panel
        this.summaryPanel = document.createElement('div');
        this.summaryPanel.className = 'measurement-summary';
        this.summaryPanel.innerHTML = '<h4>Measurements</h4><ul></ul>';
        this.container.appendChild(this.summaryPanel);

        // 3. Register click handler on container for placing pins
        this.container.addEventListener('click', (e) => {
            // Ignore clicks on UI elements or existing pins
            if (e.target.closest('#ui-overlay') || e.target.classList.contains('measurement-pin')) {
                return;
            }

            if (window.bodyViewer && window.bodyViewer.getMeshIntersection) {
                const hit = window.bodyViewer.getMeshIntersection(e);
                if (hit && hit.point) {
                    if (this.angleMode) {
                        this._placeAnglePin(hit.point);
                    } else {
                        this.placePin(hit.point);
                    }
                }
            }
        });

        // 4. Register mousemove handler for tooltip positioning and hover region detection
        this.mouseX = 0;
        this.mouseY = 0;
        let _hoverThrottle = 0;

        this.container.addEventListener('mousemove', (e) => {
            this.mouseX = e.clientX;
            this.mouseY = e.clientY;

            // Position tooltip
            if (this.tooltip.style.display === 'block') {
                this.tooltip.style.left = (this.mouseX + 15) + 'px';
                this.tooltip.style.top = (this.mouseY + 15) + 'px';
            }

            // Region detection throttle
            const now = Date.now();
            if (now - _hoverThrottle < 80) return;  // Throttle to ~12fps
            _hoverThrottle = now;

            if (!window.bodyViewer || !window.bodyViewer.getMeshIntersection) return;

            // Don't show region tooltip during active pin placement
            if (this.pendingPin || (this.angleMode && this.pendingAnglePins.length > 0)) {
                return;
            }

            const hit = window.bodyViewer.getMeshIntersection(e);
            if (hit && hit.point) {
                const region = this._getBodyRegion(hit.point);
                if (region) {
                    this.showTooltip(e.clientX, e.clientY, {
                        label: 'Region',
                        value: region
                    });
                }
            } else {
                // Hide region tooltip if we move off mesh
                if (this.tooltip.innerHTML.includes('Region:')) {
                    this.hideTooltip();
                }
            }
        });

        // 5. Start update loop
        this.update();
    },

    /**
     * Body region detection by height ratio (Y-up coordinate system).
     */
    _getBodyRegion(worldPos) {
        if (!window.bodyViewer || !window.bodyViewer.mesh) return null;

        if (!this._meshBounds) {
            let minY = Infinity, maxY = -Infinity, minX = Infinity, maxX = -Infinity;
            window.bodyViewer.mesh.traverse(child => {
                if (!child.isMesh || !child.geometry) return;
                const pos = child.geometry.attributes.position;
                for (let i = 0; i < pos.count; i++) {
                    const y = pos.getY(i), x = pos.getX(i);
                    if (y < minY) minY = y;
                    if (y > maxY) maxY = y;
                    if (x < minX) minX = x;
                    if (x > maxX) maxX = x;
                }
            });
            this._meshBounds = { minY, maxY, rangeY: maxY - minY, halfW: (maxX - minX) / 2 };
        }

        const b = this._meshBounds;
        if (b.rangeY < 1) return null;
        const ratio = (worldPos.y - b.minY) / b.rangeY;
        const xRatio = Math.abs(worldPos.x) / (b.halfW || 1);

        if (ratio > 0.92) return 'Head';
        if (ratio > 0.85) return 'Neck';
        if (ratio > 0.78) return xRatio > 0.6 ? 'Shoulder' : 'Upper Chest';
        if (ratio > 0.65) return xRatio > 0.7 ? 'Upper Arm' : (ratio > 0.72 ? 'Chest' : 'Waist');
        if (ratio > 0.55) return xRatio > 0.7 ? 'Forearm' : 'Hip';
        if (ratio > 0.45) return 'Upper Thigh';
        if (ratio > 0.30) return 'Thigh';
        if (ratio > 0.15) return 'Calf';
        if (ratio > 0.05) return 'Ankle';
        return 'Foot';
    },

    /**
     * Toggle angle measurement mode.
     */
    toggleAngleMode() {
        this.angleMode = !this.angleMode;
        this.pendingAnglePins = [];
        const btn = document.getElementById('btn-measure-angle');
        if (btn) btn.classList.toggle('active', this.angleMode);
    },

    /**
     * Place a measurement pin at a 3D point on the mesh (Distance mode).
     */
    placePin(worldPosition) {
        if (this.pendingPin === null) {
            if (this.measurements.length >= this.maxMeasurements) {
                this._removeMeasurement(0);
            }
            const pinEl = this._createPinElement();
            this.pendingPin = { worldPos: worldPosition.clone(), element: pinEl };
        } else {
            const pinEl = this._createPinElement();
            const pinB = { worldPos: worldPosition.clone(), element: pinEl };

            const lineEl = document.createElement('div');
            lineEl.className = 'measurement-line';
            this.container.appendChild(lineEl);

            const labelEl = document.createElement('div');
            labelEl.className = 'measurement-label';
            this.container.appendChild(labelEl);

            const dist = this.pendingPin.worldPos.distanceTo(pinB.worldPos);
            labelEl.textContent = dist >= 100
                ? (dist / 10).toFixed(1) + ' cm'
                : dist.toFixed(1) + ' mm';

            this.measurements.push({
                pinA: this.pendingPin,
                pinB: pinB,
                lineEl: lineEl,
                labelEl: labelEl,
                distance_mm: dist,
            });
            this.pendingPin = null;
            this._updateSummary();
        }
    },

    /**
     * Place a pin for angle measurement (up to 3).
     */
    _placeAnglePin(worldPos) {
        if (this.pendingAnglePins.length >= 3) {
            this._clearAnglePins();
        }

        const el = this._createPinElement();
        el.classList.add('angle-pin');
        this.pendingAnglePins.push({ worldPos: worldPos.clone(), element: el });

        if (this.pendingAnglePins.length === 3) {
            const A = this.pendingAnglePins[0].worldPos;
            const B = this.pendingAnglePins[1].worldPos;
            const C = this.pendingAnglePins[2].worldPos;

            const BA = A.clone().sub(B);
            const BC = C.clone().sub(B);
            const dot = BA.dot(BC);
            const cross = BA.length() * BC.length();
            const angleRad = Math.acos(Math.max(-1, Math.min(1, dot / (cross || 1))));
            const angleDeg = (angleRad * 180 / Math.PI).toFixed(1);

            const line1 = document.createElement('div');
            line1.className = 'measurement-line angle-line';
            this.container.appendChild(line1);

            const line2 = document.createElement('div');
            line2.className = 'measurement-line angle-line';
            this.container.appendChild(line2);

            const label = document.createElement('div');
            label.className = 'measurement-label angle-label';
            label.textContent = angleDeg + '°';
            this.container.appendChild(label);

            this._angleMeasurement = {
                pins: this.pendingAnglePins.slice(),
                lines: [line1, line2],
                label: label,
                angle: parseFloat(angleDeg),
            };
            this._updateSummary();
        }
    },

    /**
     * Clear current angle measurement and its pins.
     */
    _clearAnglePins() {
        for (const p of this.pendingAnglePins) {
            p.element.remove();
        }
        this.pendingAnglePins = [];
        if (this._angleMeasurement) {
            this._angleMeasurement.lines.forEach(l => l.remove());
            this._angleMeasurement.label.remove();
            this._angleMeasurement = null;
        }
        this._updateSummary();
    },

    /**
     * Internal helper to create a pin DOM element with click-to-remove logic.
     */
    _createPinElement() {
        const el = document.createElement('div');
        el.className = 'measurement-pin';
        el.addEventListener('click', (e) => {
            e.stopPropagation();
            
            const idx = this.measurements.findIndex(
                m => m.pinA.element === el || m.pinB.element === el
            );
            if (idx >= 0) {
                this._removeMeasurement(idx);
                return;
            }
            
            if (this.pendingPin && this.pendingPin.element === el) {
                el.remove();
                this.pendingPin = null;
                this._updateSummary();
                return;
            }

            if (this._angleMeasurement && this._angleMeasurement.pins.some(p => p.element === el)) {
                this._clearAnglePins();
                return;
            }

            const aIdx = this.pendingAnglePins.findIndex(p => p.element === el);
            if (aIdx >= 0) {
                this._clearAnglePins();
                return;
            }
        });
        this.container.appendChild(el);
        return el;
    },

    /**
     * Remove a specific distance measurement by index.
     */
    _removeMeasurement(index) {
        const m = this.measurements[index];
        if (!m) return;
        m.pinA.element.remove();
        m.pinB.element.remove();
        m.lineEl.remove();
        m.labelEl.remove();
        this.measurements.splice(index, 1);
        this._updateSummary();
    },

    /**
     * Update the floating summary panel with all current measurements.
     */
    _updateSummary() {
        if (!this.summaryPanel) return;
        const ul = this.summaryPanel.querySelector('ul');
        if (!ul) return;

        const items = [];
        this.measurements.forEach((m, i) => {
            const dist = m.distance_mm;
            const formatted = dist >= 100
                ? (dist / 10).toFixed(1) + ' cm'
                : dist.toFixed(1) + ' mm';
            items.push(`<li><span class="msr-idx">${i + 1}</span> ${formatted}</li>`);
        });

        if (this._angleMeasurement) {
            items.push(`<li><span class="msr-idx">∠</span> ${this._angleMeasurement.angle}°</li>`);
        }

        ul.innerHTML = items.join('');
        this.summaryPanel.style.display = items.length > 0 ? 'block' : 'none';
    },

    /**
     * Project a 3D world position to 2D screen coordinates.
     */
    projectToScreen(worldPos) {
        if (!window.bodyViewer || !window.bodyViewer.camera || !window.bodyViewer.renderer) {
            return { x: 0, y: 0, visible: false };
        }

        const vector = worldPos.clone();
        vector.project(window.bodyViewer.camera);
        const canvas = window.bodyViewer.renderer.domElement;

        return {
            x: (vector.x * 0.5 + 0.5) * canvas.clientWidth,
            y: (-vector.y * 0.5 + 0.5) * canvas.clientHeight,
            visible: vector.z < 1,
        };
    },

    /**
     * Update loop — repositions all pins, lines and labels every frame.
     */
    update() {
        if (this.pendingPin) {
            const s = this.projectToScreen(this.pendingPin.worldPos);
            this.pendingPin.element.style.display = s.visible ? 'block' : 'none';
            this.pendingPin.element.style.left = s.x + 'px';
            this.pendingPin.element.style.top = s.y + 'px';
        }

        for (const m of this.measurements) {
            const pA = this.projectToScreen(m.pinA.worldPos);
            const pB = this.projectToScreen(m.pinB.worldPos);

            m.pinA.element.style.display = pA.visible ? 'block' : 'none';
            m.pinA.element.style.left = pA.x + 'px';
            m.pinA.element.style.top = pA.y + 'px';
            m.pinB.element.style.display = pB.visible ? 'block' : 'none';
            m.pinB.element.style.left = pB.x + 'px';
            m.pinB.element.style.top = pB.y + 'px';

            const bothVis = pA.visible && pB.visible;
            m.lineEl.style.display = bothVis ? 'block' : 'none';
            if (bothVis) {
                const dx = pB.x - pA.x, dy = pB.y - pA.y;
                const len = Math.sqrt(dx * dx + dy * dy);
                const angle = Math.atan2(dy, dx);
                m.lineEl.style.width = len + 'px';
                m.lineEl.style.left = pA.x + 'px';
                m.lineEl.style.top = pA.y + 'px';
                m.lineEl.style.transform = `rotate(${angle}rad)`;
            }

            m.labelEl.style.display = bothVis ? 'block' : 'none';
            if (bothVis) {
                m.labelEl.style.left = ((pA.x + pB.x) / 2) + 'px';
                m.labelEl.style.top = ((pA.y + pB.y) / 2 - 20) + 'px';
            }
        }

        for (const p of this.pendingAnglePins) {
            const s = this.projectToScreen(p.worldPos);
            p.element.style.display = s.visible ? 'block' : 'none';
            p.element.style.left = s.x + 'px';
            p.element.style.top = s.y + 'px';
        }

        if (this._angleMeasurement) {
            const am = this._angleMeasurement;
            const sA = this.projectToScreen(am.pins[0].worldPos);
            const sB = this.projectToScreen(am.pins[1].worldPos);
            const sC = this.projectToScreen(am.pins[2].worldPos);
            const allVis = sA.visible && sB.visible && sC.visible;

            am.lines[0].style.display = allVis ? 'block' : 'none';
            if (allVis) {
                const dx = sB.x - sA.x, dy = sB.y - sA.y;
                am.lines[0].style.width = Math.sqrt(dx*dx + dy*dy) + 'px';
                am.lines[0].style.left = sA.x + 'px';
                am.lines[0].style.top = sA.y + 'px';
                am.lines[0].style.transform = `rotate(${Math.atan2(dy, dx)}rad)`;
            }

            am.lines[1].style.display = allVis ? 'block' : 'none';
            if (allVis) {
                const dx = sC.x - sB.x, dy = sC.y - sB.y;
                am.lines[1].style.width = Math.sqrt(dx*dx + dy*dy) + 'px';
                am.lines[1].style.left = sB.x + 'px';
                am.lines[1].style.top = sB.y + 'px';
                am.lines[1].style.transform = `rotate(${Math.atan2(dy, dx)}rad)`;
            }

            am.label.style.display = allVis ? 'block' : 'none';
            if (allVis) {
                am.label.style.left = sB.x + 'px';
                am.label.style.top = (sB.y - 25) + 'px';
            }
        }

        requestAnimationFrame(() => this.update());
    },

    /**
     * Copy all current measurements to clipboard.
     */
    copyToClipboard() {
        const lines = [];
        this.measurements.forEach((m, i) => {
            const dist = m.distance_mm;
            const formatted = dist >= 100 ? (dist / 10).toFixed(1) + ' cm' : dist.toFixed(1) + ' mm';
            lines.push(`Distance ${i + 1}: ${formatted}`);
        });
        if (this._angleMeasurement) {
            lines.push(`Angle: ${this._angleMeasurement.angle}°`);
        }
        if (lines.length === 0) lines.push('No measurements');

        const text = 'GTD3D Measurements\n' + lines.join('\n');
        navigator.clipboard.writeText(text).then(() => {
            this.showTooltip(window.innerWidth / 2, 60, { label: 'Copied', value: lines.length + ' measurement(s)' });
            setTimeout(() => this.hideTooltip(), 1500);
        }).catch(() => {
            const ta = document.createElement('textarea');
            ta.value = text;
            ta.style.cssText = 'position:fixed;opacity:0';
            document.body.appendChild(ta);
            ta.select();
            document.execCommand('copy');
            ta.remove();
        });
    },

    showTooltip(screenX, screenY, data) {
        if (!this.tooltip) return;
        this.tooltip.innerHTML = `<span class="label">${data.label}:</span> <span class="value">${data.value}</span>`;
        this.tooltip.style.display = 'block';
        this.tooltip.style.left = (screenX + 15) + 'px';
        this.tooltip.style.top = (screenY + 15) + 'px';
    },

    hideTooltip() {
        if (this.tooltip) this.tooltip.style.display = 'none';
    },

    /**
     * Remove all pins and measurements.
     */
    clear() {
        while (this.measurements.length > 0) {
            this._removeMeasurement(0);
        }
        if (this.pendingPin) {
            this.pendingPin.element.remove();
            this.pendingPin = null;
        }
        this._clearAnglePins();
        this.angleMode = false;
        this._meshBounds = null;
        this.hideTooltip();
        this._updateSummary();
    },
};