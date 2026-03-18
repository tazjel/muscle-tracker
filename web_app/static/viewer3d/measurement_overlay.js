/**
 * Measurement Overlay Module
 * Adds interactive measurement pins and distance display on top of the 3D viewer.
 *
 * Usage: Sonnet's body_viewer.js will call `MeasurementOverlay.init(container)`
 *        after the viewer is ready.
 */

const MeasurementOverlay = {
    container: null,      // DOM element to append overlays to
    pins: [],             // Array of {id, worldPos: THREE.Vector3, element: HTMLElement}
    tooltip: null,        // The tooltip HTMLElement
    activeMeasurement: null, // {pinA, pinB, lineElement, distance_mm}

    /**
     * Initialize the overlay system.
     * @param {HTMLElement} container - The viewer container div
     */
    init(container) {
        this.container = container;
        
        // 1. Create tooltip element, append to container
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

        // 4. Start update loop (requestAnimationFrame) to reproject pin positions
        this.update();
    },

    /**
     * Place a measurement pin at a 3D point on the mesh.
     * When two pins are placed, show the distance between them.
     * Clicking a third pin starts a new measurement (removes previous pair).
     */
    placePin(worldPosition) {
        // If we already have 2 pins, clear them to start fresh
        if (this.pins.length >= 2) {
            this.clear();
        }

        // 1. Create a .measurement-pin div
        const pinEl = document.createElement('div');
        pinEl.className = 'measurement-pin';
        this.container.appendChild(pinEl);

        const pin = {
            id: Date.now() + Math.random(),
            worldPos: worldPosition.clone(),
            element: pinEl
        };

        // 2. Store worldPosition
        this.pins.push(pin);

        // 3. If this is the second pin, draw a .measurement-line between them
        //    and calculate distance
        if (this.pins.length === 2) {
            const pinA = this.pins[0];
            const pinB = this.pins[1];
            
            const lineEl = document.createElement('div');
            lineEl.className = 'measurement-line';
            this.container.appendChild(lineEl);
            
            const distance_mm = pinA.worldPos.distanceTo(pinB.worldPos);
            
            this.activeMeasurement = {
                pinA: pinA,
                pinB: pinB,
                lineElement: lineEl,
                distance_mm: distance_mm
            };
            
            // 4. Show distance in tooltip (format: "XX.X mm" or "XX.X cm")
            let displayValue = "";
            if (distance_mm >= 100) {
                displayValue = (distance_mm / 10).toFixed(1) + " cm";
            } else {
                displayValue = distance_mm.toFixed(1) + " mm";
            }
            
            this.showTooltip(this.mouseX, this.mouseY, {
                label: 'Distance',
                value: displayValue
            });
        }
    },

    /**
     * Project a 3D world position to 2D screen coordinates.
     * Call this every frame to keep pins aligned with the rotating model.
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
     * Update loop — repositions all pins and lines every frame.
     */
    update() {
        // For each pin: projectToScreen, update element.style.left/top
        for (const pin of this.pins) {
            const screen = this.projectToScreen(pin.worldPos);
            if (screen.visible) {
                pin.element.style.display = 'block';
                pin.element.style.left = screen.x + 'px';
                pin.element.style.top = screen.y + 'px';
            } else {
                pin.element.style.display = 'none';
            }
        }
        
        // For measurement line: update position/rotation/width between pin positions
        if (this.activeMeasurement) {
            const m = this.activeMeasurement;
            const pA = this.projectToScreen(m.pinA.worldPos);
            const pB = this.projectToScreen(m.pinB.worldPos);
            
            if (pA.visible && pB.visible) {
                m.lineElement.style.display = 'block';
                
                const dx = pB.x - pA.x;
                const dy = pB.y - pA.y;
                const length = Math.sqrt(dx * dx + dy * dy);
                const angle = Math.atan2(dy, dx);
                
                m.lineElement.style.width = length + 'px';
                m.lineElement.style.left = pA.x + 'px';
                m.lineElement.style.top = pA.y + 'px';
                m.lineElement.style.transform = `rotate(${angle}rad)`;
            } else {
                m.lineElement.style.display = 'none';
            }
        }
        
        requestAnimationFrame(() => this.update());
    },

    /**
     * Show tooltip at cursor position with measurement data.
     */
    showTooltip(screenX, screenY, data) {
        if (!this.tooltip) return;
        
        this.tooltip.innerHTML = `<span class="label">${data.label}:</span> <span class="value">${data.value}</span>`;
        this.tooltip.style.display = 'block';
        this.tooltip.style.left = (screenX + 15) + 'px';
        this.tooltip.style.top = (screenY + 15) + 'px';
    },

    hideTooltip() {
        if (this.tooltip) {
            this.tooltip.style.display = 'none';
        }
    },

    /**
     * Remove all pins and measurements.
     */
    clear() {
        // Remove all pin elements and lines from DOM
        for (const pin of this.pins) {
            if (pin.element && pin.element.parentNode) {
                pin.element.parentNode.removeChild(pin.element);
            }
        }
        this.pins = [];
        
        if (this.activeMeasurement && this.activeMeasurement.lineElement) {
            const line = this.activeMeasurement.lineElement;
            if (line.parentNode) {
                line.parentNode.removeChild(line);
            }
        }
        this.activeMeasurement = null;
        
        this.hideTooltip();
    },
};