/* GTD3D Studio — Device Panel
 * Device bridge status, ADB actions, pose check, muscle classification.
 * Dual Capture button injected into scan-panel's upload row.
 */
const DevicePanel = {
    _captureBtn: null,
    _currentCustomerId: null,
    _healthTimer: null,
    _scanActive: false,      // true while a scan is processing (drives adaptive poll rate)
    _serverOnline: null,     // last known server state (null = unknown)

    init() {
        this._injectCaptureButton();
        this._renderDeviceStatus();
        this._renderActionButtons();
        this._renderServerBadge();
        this._pollHealth();

        document.addEventListener('customer-selected', (e) => {
            this._currentCustomerId = e.detail.id;
            this._enableCapture();
            this._enableActions();
        });

        // Track scan-active state for adaptive polling
        document.addEventListener('scan-processing-start', () => {
            this._scanActive = true;
            this._resetPollTimer();
        });
        document.addEventListener('scan-processing-end', () => {
            this._scanActive = false;
            this._resetPollTimer();
        });
    },

    // Inject "Dual Capture" into scan-panel's upload row (waits for DOM element).
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

    _renderDeviceStatus() {
        const el = document.getElementById('device-status-section');
        if (!el) return;

        if (Studio.MOCK_MODE) {
            el.innerHTML = `
                <div style="display:flex;align-items:center;gap:8px;">
                    <span style="width:8px;height:8px;border-radius:50%;background:#22c55e;display:inline-block;flex-shrink:0;"></span>
                    <span style="font-size:0.8125rem;">2 devices connected</span>
                </div>
                <div style="font-size:11px;color:var(--text-dim);margin-top:4px;">Samsung A24 × 2</div>
            `;
            return;
        }

        el.innerHTML = `
            <div id="device-status" style="display:flex;align-items:center;gap:8px;">
                <span class="dot dot-off"></span>
                <span style="font-size:0.8125rem;">Checking devices…</span>
            </div>
        `;
    },

    _renderServerBadge() {
        // Inject "Server: …" badge into the device-status panel header if present
        const panelHeader = document.querySelector('#panel-device-status .panel-header');
        if (!panelHeader || document.getElementById('server-conn-badge')) return;
        const badge = document.createElement('span');
        badge.id = 'server-conn-badge';
        badge.style.cssText = 'margin-left:auto;font-size:11px;';
        badge.innerHTML = Studio.MOCK_MODE
            ? '<span style="color:#a3a3a3;">mock</span>'
            : '<span style="color:#a3a3a3;">…</span>';
        panelHeader.appendChild(badge);
    },

    _updateServerBadge(online) {
        const badge = document.getElementById('server-conn-badge');
        if (!badge) return;
        if (Studio.MOCK_MODE) {
            badge.innerHTML = '<span style="color:#a3a3a3;">mock</span>';
            return;
        }
        badge.innerHTML = online
            ? '<span style="color:#22c55e;">&#x25cf; Connected</span>'
            : '<span style="color:#ef4444;">&#x25cf; Disconnected</span>';
    },

    _renderActionButtons() {
        const el = document.getElementById('device-actions-section');
        if (!el) return;
        el.innerHTML = `
            <div style="border-top:1px solid rgba(255,255,255,0.08);margin:8px 0;"></div>
            <div style="font-size:11px;color:var(--text-dim);margin-bottom:6px;">ANALYSIS ACTIONS</div>
            <button class="btn btn-sm" id="btn-pose-check" style="width:100%;margin-bottom:6px;" disabled
                onclick="DevicePanel.poseCheck()">Pose Check</button>
            <button class="btn btn-sm" id="btn-classify-muscle" style="width:100%;margin-bottom:8px;" disabled
                onclick="DevicePanel.classifyMuscle()">Classify Muscle</button>
            <div style="border-top:1px solid rgba(255,255,255,0.08);margin:8px 0;"></div>
            <div style="display:flex;justify-content:space-between;align-items:center;font-size:11px;">
                <span style="color:var(--text-dim);">Server health</span>
                <span id="device-health-badge">
                    ${Studio.MOCK_MODE ? '<span class="tag tag-ok">OK</span>' : '<span style="color:var(--text-dim);">…</span>'}
                </span>
            </div>
            <div id="device-action-result" style="font-size:11px;color:var(--text-dim);margin-top:6px;"></div>
        `;
    },

    _pollHealth() {
        if (Studio.MOCK_MODE) {
            this._updateServerBadge(null);
            return;
        }
        const poll = async () => {
            try {
                const resp = await fetch(`${Studio.API_BASE}/api/health`).catch(() => null);
                const online = !!(resp && resp.ok);
                if (online !== this._serverOnline) {
                    this._serverOnline = online;
                    this._updateServerBadge(online);
                }
                const badge = document.getElementById('device-health-badge');
                if (badge) {
                    badge.innerHTML = online
                        ? '<span class="tag tag-ok">OK</span>'
                        : '<span class="tag tag-err">Offline</span>';
                }
            } catch (e) {
                this._serverOnline = false;
                this._updateServerBadge(false);
                const badge = document.getElementById('device-health-badge');
                if (badge) badge.innerHTML = '<span class="tag tag-err">Offline</span>';
            }
        };
        poll();
        // Adaptive interval: 3 s when scan is active, 30 s when idle
        const interval = this._scanActive ? 3000 : 30000;
        this._healthTimer = setInterval(poll, interval);
    },

    _resetPollTimer() {
        if (this._healthTimer) { clearInterval(this._healthTimer); this._healthTimer = null; }
        this._pollHealth();
    },

    _enableCapture() {
        if (this._captureBtn) this._captureBtn.disabled = false;
    },

    _enableActions() {
        ['btn-pose-check', 'btn-classify-muscle'].forEach(id => {
            const btn = document.getElementById(id);
            if (btn) btn.disabled = false;
        });
    },

    async triggerCapture() {
        Studio.log('Dual-device capture: use GTDdebug CLI for now');
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

    async poseCheck() {
        const btn = document.getElementById('btn-pose-check');
        const result = document.getElementById('device-action-result');
        if (btn) { btn.disabled = true; btn.textContent = 'Checking…'; }

        if (Studio.MOCK_MODE) {
            await new Promise(r => setTimeout(r, 600));
            Studio.log('Mock: pose check — Good pose detected');
            if (result) result.textContent = 'Pose: Good (mock)';
            if (btn) { btn.disabled = false; btn.textContent = 'Pose Check'; }
            return;
        }

        // POST a placeholder frame payload — real integration would send a captured frame blob
        const { ok, data } = await Studio.apiPost('/api/pose_check', { customer_id: this._currentCustomerId });
        if (ok) {
            const label = data.pose || data.result || 'OK';
            Studio.log(`Pose check: ${label}`);
            if (result) result.textContent = `Pose: ${label}`;
        } else {
            Studio.log(`Pose check failed: ${(data && data.error) || 'Unknown'}`, 'error');
            if (result) result.textContent = 'Pose check failed.';
        }
        if (btn) { btn.disabled = false; btn.textContent = 'Pose Check'; }
    },

    async classifyMuscle() {
        const btn = document.getElementById('btn-classify-muscle');
        const result = document.getElementById('device-action-result');
        if (btn) { btn.disabled = true; btn.textContent = 'Classifying…'; }

        if (Studio.MOCK_MODE) {
            await new Promise(r => setTimeout(r, 600));
            Studio.log('Mock: muscle classification — Bicep / Chest detected');
            if (result) result.textContent = 'Muscle: Bicep, Chest (mock)';
            if (btn) { btn.disabled = false; btn.textContent = 'Classify Muscle'; }
            return;
        }

        const { ok, data } = await Studio.apiPost('/api/classify_muscle', { customer_id: this._currentCustomerId });
        if (ok) {
            const groups = Array.isArray(data.muscle_groups) ? data.muscle_groups.join(', ') : (data.result || 'OK');
            Studio.log(`Muscle classification: ${groups}`);
            if (result) result.textContent = `Muscle: ${groups}`;
        } else {
            Studio.log(`Classify failed: ${(data && data.error) || 'Unknown'}`, 'error');
            if (result) result.textContent = 'Classification failed.';
        }
        if (btn) { btn.disabled = false; btn.textContent = 'Classify Muscle'; }
    },
};

document.addEventListener('DOMContentLoaded', () => DevicePanel.init());
