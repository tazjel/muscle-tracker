/**
 * Measurement Overlay Module V2
 * Adds interactive multi-measurement pins and persistent labels on top of the 3D viewer.
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

    /**
     * Initialize the overlay system.
     */
    init(container) {
        this.container = container;
        
        // 1. Create tooltip element (legacy support for hover info if needed)
        this.tooltip = document.createElement('div');
        this.tooltip.className = 'measurement-tooltip';
        this.container.appendChild(this.tooltip);

        // 2. Register click handler on container for placing pins
        this.container.addEventListener('click', (e) => {
            // Ignore clicks on UI elements or existing pins
            if (e.target.closest('#ui-overlay') || e.target.classList.contains('measurement-pin')) {
                return;
            }
            
            if (window.bodyViewer && window.bodyViewer.getMeshIntersection) {
                const hit = window.bodyViewer.getMeshIntersection(e);
                if (hit && hit.point) {
                    this.placePin(hit.point);
                }
            }
        });

        // 3. Register mousemove handler for tooltip positioning
        this.mouseX = 0;
        this.mouseY = 0;
        this.container.addEventListener('mousemove', (e) => {
            this.mouseX = e.clientX;
            this.mouseY = e.clientY;
            
            if (this.tooltip.style.display === 'block') {
                this.tooltip.style.left = (this.mouseX + 15) + 'px';
                this.tooltip.style.top = (this.mouseY + 15) + 'px';
            }
        });

        // 4. Start update loop
        this.update();
    },

    /**
     * Place a measurement pin at a 3D point on the mesh.
     */
    placePin(worldPosition) {
        if (this.pendingPin === null) {
            // First pin of a new measurement
            if (this.measurements.length >= this.maxMeasurements) {
                // Remove oldest measurement to make room
                this._removeMeasurement(0);
            }
            const pinEl = this._createPinElement();
            this.pendingPin = { worldPos: worldPosition.clone(), element: pinEl };
        } else {
            // Second pin — complete the measurement
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
        }
    },

    /**
     * Internal helper to create a pin DOM element with click-to-remove logic.
     */
    _createPinElement() {
        const el = document.createElement('div');
        el.className = 'measurement-pin';
        // Click on pin to remove its measurement
        el.addEventListener('click', (e) => {
            e.stopPropagation();
            const idx = this.measurements.findIndex(
                m => m.pinA.element === el || m.pinB.element === el
            );
            if (idx >= 0) this._removeMeasurement(idx);
            // Also check if it's the pending pin
            if (this.pendingPin && this.pendingPin.element === el) {
                el.remove();
                this.pendingPin = null;
            }
        });
        this.container.appendChild(el);
        return el;
    },

    /**
     * Remove a specific measurement by index.
     */
    _removeMeasurement(index) {
        const m = this.measurements[index];
        if (!m) return;
        m.pinA.element.remove();
        m.pinB.element.remove();
        m.lineEl.remove();
        m.labelEl.remove();
        this.measurements.splice(index, 1);
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
        // Update pending pin
        if (this.pendingPin) {
            const s = this.projectToScreen(this.pendingPin.worldPos);
            this.pendingPin.element.style.display = s.visible ? 'block' : 'none';
            this.pendingPin.element.style.left = s.x + 'px';
            this.pendingPin.element.style.top = s.y + 'px';
        }

        // Update all completed measurements
        for (const m of this.measurements) {
            const pA = this.projectToScreen(m.pinA.worldPos);
            const pB = this.projectToScreen(m.pinB.worldPos);

            // Pins
            m.pinA.element.style.display = pA.visible ? 'block' : 'none';
            m.pinA.element.style.left = pA.x + 'px';
            m.pinA.element.style.top = pA.y + 'px';
            m.pinB.element.style.display = pB.visible ? 'block' : 'none';
            m.pinB.element.style.left = pB.x + 'px';
            m.pinB.element.style.top = pB.y + 'px';

            // Line
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

            // Label at midpoint
            m.labelEl.style.display = bothVis ? 'block' : 'none';
            if (bothVis) {
                m.labelEl.style.left = ((pA.x + pB.x) / 2) + 'px';
                m.labelEl.style.top = ((pA.y + pB.y) / 2 - 20) + 'px';
            }
        }

        requestAnimationFrame(() => this.update());
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
        this.hideTooltip();
    },
};