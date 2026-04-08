/* GTD3D Studio — Device Panel
 * Thin wrapper around the ADB device bridge.
 * Device polling and #device-status updates live in studio.js.
 * This module adds customer-context awareness and a capture trigger button.
 */
const DevicePanel = {
    _captureBtn: null,

    init() {
        this._injectCaptureButton();
        document.addEventListener('customer-selected', () => this._enableCapture());
    },

    // Inject a "Dual Capture" button into the scan upload row after ScanPanel creates it.
    // We wait for the DOM element to appear (ScanPanel.init runs before us due to defer order,
    // but both are deferred — use a short poll to be safe).
    _injectCaptureButton() {
        const attempt = () => {
            const row = document.getElementById('scan-upload-btns');
            if (!row) { setTimeout(attempt, 100); return; }
            if (document.getElementById('btn-dual-capture')) return; // already injected

            const btn = document.createElement('button');
            btn.id = 'btn-dual-capture';
            btn.className = 'btn btn-sm';
            btn.disabled = true;
            btn.title = 'ADB dual-device capture (use GTDdebug CLI)';
            btn.textContent = 'Dual Capture';
            btn.addEventListener('click', () => this.triggerCapture());
            row.appendChild(btn);
            this._captureBtn = btn;
        };
        attempt();
    },

    _enableCapture() {
        if (this._captureBtn) this._captureBtn.disabled = false;
    },

    async triggerCapture() {
        // Future: POST to a GTDdebug proxy endpoint.
        // For now, instruct the operator to use the CLI.
        Studio.log('Dual-device capture: use GTDdebug CLI for now');

        // Show a brief visual acknowledgment on the button
        if (this._captureBtn) {
            const orig = this._captureBtn.textContent;
            this._captureBtn.disabled = true;
            this._captureBtn.textContent = 'Use GTDdebug CLI';
            setTimeout(() => {
                this._captureBtn.textContent = orig;
                this._captureBtn.disabled = false;
            }, 2500);
        }
    },
};

document.addEventListener('DOMContentLoaded', () => DevicePanel.init());
