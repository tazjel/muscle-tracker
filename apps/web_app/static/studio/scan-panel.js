/* GTD3D Studio — Scan Panel
 * Left sidebar: camera feed status from MatePad GTD3D APK.
 * Camera UI is in the HTML template — this JS is a placeholder for future WebSocket connection.
 */
const ScanPanel = {
    connected: false,
    frameCount: 0,

    init() {
        // placeholder — will connect to MatePad later
    },
};

document.addEventListener('DOMContentLoaded', () => ScanPanel.init());
