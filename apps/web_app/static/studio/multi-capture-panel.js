/* GTD3D Studio — Multi-Capture Panel
 * Left sidebar: device cards for connected phones.
 * Right sidebar: sync capture controls + gallery.
 * Supports 2 phones now, scales to 4 devices later.
 */
const MultiCapturePanel = {
    devices: [
        { serial: 'R58W41RF6ZK', name: 'Samsung A24 #1', connection: 'WiFi', direction: 'front', status: 'connected', lastFrame: null },
        { serial: 'R58W41REJVD', name: 'Samsung A24 #2', connection: 'USB', direction: 'back', status: 'connected', lastFrame: null },
    ],
    captures: [],

    async init() {
        this._renderModeBanner();
        await this._loadDevices();
        this._setupButtons();
        // Listen for SSE device events
        document.addEventListener('device_connected', (e) => {
            Studio.log(`Device connected: ${e.detail.serial || 'unknown'}`);
            this._loadDevices();
        });
        document.addEventListener('device_disconnected', (e) => {
            Studio.log(`Device disconnected: ${e.detail.serial || 'unknown'}`);
            this._loadDevices();
        });
    },

    async _loadDevices() {
        if (Studio.MOCK_MODE || !Studio.customerId) {
            this._renderDevices();
            return;
        }
        try {
            const { ok, data } = await Studio.apiGet(`/api/customer/${Studio.customerId}/devices`);
            if (ok && data.devices) {
                this.devices = data.devices.map(d => ({
                    serial: d.device_serial || d.serial || '',
                    name: d.device_name || d.name || `Device ${d.id}`,
                    connection: d.connection_type || 'WiFi',
                    direction: d.direction || 'front',
                    status: 'connected',
                    lastFrame: null,
                }));
            }
        } catch (e) {
            Studio.log(`Multi-capture: device load failed — ${e.message}`, 'warn');
        }
        this._renderDevices();
    },

    _renderModeBanner() {
        const el = document.getElementById('multi-capture-mode-banner');
        if (!el) return;
        if (Studio.MOCK_MODE) {
            el.innerHTML = '<div style="padding:8px;background:rgba(239,68,68,0.1);border:1px solid rgba(239,68,68,0.3);border-radius:4px;font-size:11px;color:#ef4444;margin-bottom:8px;">Enable Live mode for real device sync</div>';
        } else {
            el.innerHTML = '';
        }
    },

    _renderDevices() {
        const el = document.getElementById('multi-capture-devices');
        if (!el) return;

        const directions = ['front', 'back', 'left', 'right'];
        const statusColors = { connected: '#22c55e', disconnected: '#ef4444', capturing: '#3b82f6' };

        el.innerHTML = this.devices.map(d => {
            const color = statusColors[d.status] || '#6b7280';
            const dirOptions = directions.map(dir =>
                `<option value="${dir}" ${d.direction === dir ? 'selected' : ''}>${dir.charAt(0).toUpperCase() + dir.slice(1)}</option>`
            ).join('');

            return `<div style="padding:8px;margin-bottom:8px;background:rgba(255,255,255,0.03);border:1px solid rgba(255,255,255,0.08);border-radius:6px;">
                <div style="display:flex;align-items:center;gap:8px;margin-bottom:6px;">
                    <span style="width:8px;height:8px;border-radius:50%;background:${color};display:inline-block;"></span>
                    <span style="font-size:12px;font-weight:600;">${d.name}</span>
                </div>
                <div style="font-size:11px;color:var(--text-dim);margin-bottom:4px;">${d.serial} (${d.connection})</div>
                <div style="display:flex;align-items:center;gap:8px;">
                    <span style="font-size:11px;color:var(--text-dim);">Direction:</span>
                    <select onchange="MultiCapturePanel.setDirection('${d.serial}', this.value)" style="background:rgba(255,255,255,0.06);border:1px solid rgba(255,255,255,0.12);border-radius:4px;color:#e0e0e0;padding:2px 6px;font-size:11px;">
                        ${dirOptions}
                    </select>
                </div>
            </div>`;
        }).join('');

        // Enable sync button if 2+ connected
        const connected = this.devices.filter(d => d.status === 'connected').length;
        const btn = document.getElementById('btn-sync-capture');
        if (btn) btn.disabled = connected < 2;
    },

    setDirection(serial, direction) {
        const device = this.devices.find(d => d.serial === serial);
        if (device) {
            device.direction = direction;
            if (typeof Studio !== 'undefined') Studio.log(`${device.name} → ${direction}`);
        }
    },

    _setupButtons() {
        const btn = document.getElementById('btn-sync-capture');
        if (btn) btn.addEventListener('click', () => this.syncCapture());
    },

    async syncCapture() {
        const connected = this.devices.filter(d => d.status === 'connected');
        if (connected.length < 2) return;

        connected.forEach(d => d.status = 'capturing');
        this._renderDevices();
        Studio.log(`Sync capture: ${connected.length} devices triggered`);

        if (!Studio.MOCK_MODE && Studio.customerId) {
            try {
                const { ok, data } = await Studio.apiPost(`/api/customer/${Studio.customerId}/multi_capture`, {
                    devices: connected.map(d => ({ serial: d.serial, direction: d.direction })),
                });
                if (ok) {
                    const capture = {
                        id: data.capture_id || 'cap-' + Date.now(),
                        timestamp: new Date().toLocaleTimeString(),
                        frames: connected.map(d => ({ serial: d.serial, name: d.name, direction: d.direction })),
                    };
                    this.captures.unshift(capture);
                    Studio.log(`Sync capture complete: ${connected.length} frames`);
                } else {
                    Studio.log(`Sync capture failed: ${data.message || 'unknown'}`, 'error');
                }
            } catch (e) {
                Studio.log(`Sync capture error: ${e.message}`, 'error');
            }
            connected.forEach(d => d.status = 'connected');
            this._renderDevices();
            this._renderGallery();
            return;
        }

        // Mock fallback
        setTimeout(() => {
            const capture = {
                id: 'cap-' + Date.now(),
                timestamp: new Date().toLocaleTimeString(),
                frames: connected.map(d => ({ serial: d.serial, name: d.name, direction: d.direction })),
            };
            this.captures.unshift(capture);
            connected.forEach(d => d.status = 'connected');
            this._renderDevices();
            this._renderGallery();
            Studio.log(`Sync capture complete: ${connected.length} frames from ${connected.map(d => d.direction).join(', ')}`);
        }, 2000);
    },

    _renderGallery() {
        const el = document.getElementById('multi-capture-gallery');
        if (!el) return;

        if (!this.captures.length) {
            el.innerHTML = '';
            return;
        }

        el.innerHTML = '<div style="font-size:11px;color:var(--text-dim);margin-bottom:6px;">Capture History</div>' +
            this.captures.slice(0, 5).map(c => {
                const dirs = c.frames.map(f => f.direction).join(' + ');
                return `<div style="padding:4px 0;border-bottom:1px solid rgba(255,255,255,0.05);font-size:11px;">
                    <span style="color:var(--text-dim);">${c.timestamp}</span> — ${dirs} (${c.frames.length} frames)
                </div>`;
            }).join('');
    },
};

document.addEventListener('DOMContentLoaded', () => MultiCapturePanel.init());
