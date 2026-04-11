/* GTD3D Studio — Scan Panel
 * Left sidebar: camera feed status + photo upload + scan history.
 */
const ScanPanel = {
    connected: false,
    frameCount: 0,
    fps: 0,
    _fpsTimer: null,
    _currentCustomerId: null,
    scans: [],
    _progressTimer: null,    // timer for polling processing scans
    _processingDots: 0,      // spinner state for progress indicator

    init() {
        this._renderCameraStatus();
        this._renderUploadSection();
        this._renderScanHistory();

        document.addEventListener('customer-selected', (e) => {
            this._currentCustomerId = e.detail.id;
            this.loadScans(e.detail.id);
            // Enable upload button now that a customer is selected
            const btn = document.getElementById('btn-upload-scan');
            if (btn) btn.disabled = false;
        });
    },

    _renderCameraStatus() {
        const el = document.getElementById('camera-status');
        if (!el) return;
        el.innerHTML = `
            <div style="display:flex;align-items:center;gap:8px;margin-bottom:8px;">
                <span id="cam-dot" style="width:8px;height:8px;border-radius:50%;background:#ef4444;display:inline-block;flex-shrink:0;"></span>
                <span id="cam-label">MatePad: Disconnected</span>
            </div>
            <div style="color:var(--text-dim);font-size:12px;margin-bottom:8px;">IP: 192.168.100.2</div>
            <button class="btn" id="btn-cam-connect" title="Start GTD3D APK on MatePad"
                onclick="ScanPanel.toggleConnect()">Connect</button>
            <div style="margin-top:12px;background:rgba(255,255,255,0.03);border:1px dashed rgba(255,255,255,0.1);
                border-radius:4px;padding:24px;text-align:center;color:var(--text-dim);font-size:12px;"
                id="cam-feed-placeholder">No frames received</div>
            <div style="margin-top:8px;display:flex;justify-content:space-between;font-size:11px;color:var(--text-dim);">
                <span id="cam-frame-count">0 frames captured</span>
                <span id="cam-fps" style="display:none;">0 fps</span>
            </div>
        `;
    },

    _renderUploadSection() {
        const el = document.getElementById('scan-upload-section');
        if (!el) return;
        el.innerHTML = `
            <div class="form-group">
                <label class="form-label">Front photo</label>
                <input type="file" id="scan-file-front" accept="image/*"
                    style="font-size:11px;color:var(--text-dim);width:100%;">
            </div>
            <div class="form-group">
                <label class="form-label">Side photo</label>
                <input type="file" id="scan-file-side" accept="image/*"
                    style="font-size:11px;color:var(--text-dim);width:100%;">
            </div>
            <div id="scan-upload-btns" class="btn-row" style="margin-top:0.5rem;">
                <button class="btn btn-accent btn-sm" id="btn-upload-scan" disabled
                    onclick="ScanPanel.uploadScan()">Upload Scan</button>
            </div>
            <div id="scan-upload-status" style="font-size:11px;color:var(--text-dim);margin-top:4px;"></div>
        `;
    },

    _renderScanHistory() {
        const el = document.getElementById('scan-history-list');
        if (!el) return;
        if (Studio.MOCK_MODE) {
            this._renderMockScans();
            return;
        }
        el.innerHTML = '<div class="empty-state">Select a customer to view scans</div>';
    },

    _renderMockScans() {
        const el = document.getElementById('scan-history-list');
        if (!el) return;
        const mockScans = [
            { id: 1, created_at: '2026-03-15T10:30:00', muscle_groups: ['chest', 'bicep'], status: 'done' },
            { id: 2, created_at: '2026-03-22T14:15:00', muscle_groups: ['quads', 'glutes'], status: 'done' },
            { id: 3, created_at: '2026-04-01T09:00:00', muscle_groups: ['back', 'shoulders'], status: 'processing' },
        ];
        this._renderScanList(mockScans);
    },

    async loadScans(customerId) {
        const el = document.getElementById('scan-history-list');
        if (!el) return;

        if (Studio.MOCK_MODE) {
            this._renderMockScans();
            return;
        }

        el.innerHTML = '<div class="empty-state">Loading…</div>';
        const { ok, data } = await Studio.apiGet(`/api/customer/${customerId}/scans`);
        if (!ok) {
            el.innerHTML = '<div class="empty-state" style="color:var(--error);">Failed to load scans</div>';
            return;
        }
        this.scans = data.scans || data || [];
        this._renderScanList(this.scans);

        // Start progress polling if any scan is still processing
        this._stopProgressPoll();
        const hasProcessing = this.scans.some(s => s.status === 'processing');
        if (hasProcessing) {
            this._startProgressPoll(customerId);
        }
    },

    _startProgressPoll(customerId) {
        if (this._progressTimer) return; // already polling
        document.dispatchEvent(new CustomEvent('scan-processing-start'));
        this._progressTimer = setInterval(async () => {
            const { ok, data } = await Studio.apiGet(`/api/customer/${customerId}/scans`);
            if (!ok) return;
            const scans = data.scans || data || [];
            this.scans = scans;
            this._renderScanList(scans);
            // Advance spinner dots
            this._processingDots = (this._processingDots + 1) % 4;
            this._updateProcessingIndicators();
            // Stop when no more scans are processing
            const stillProcessing = scans.some(s => s.status === 'processing');
            if (!stillProcessing) {
                this._stopProgressPoll();
                document.dispatchEvent(new CustomEvent('scan-processing-end'));
            }
        }, 3000);
    },

    _stopProgressPoll() {
        if (this._progressTimer) {
            clearInterval(this._progressTimer);
            this._progressTimer = null;
        }
    },

    _updateProcessingIndicators() {
        const dots = '.'.repeat(this._processingDots + 1);
        document.querySelectorAll('[data-scan-processing]').forEach(el => {
            el.textContent = `Processing${dots}`;
        });
    },

    _renderScanList(scans) {
        const el = document.getElementById('scan-history-list');
        if (!el) return;
        if (scans.length === 0) {
            el.innerHTML = '<div class="empty-state">No scans yet</div>';
            return;
        }
        el.innerHTML = scans.map(s => {
            const date = s.created_at
                ? new Date(s.created_at).toLocaleDateString()
                : 'Unknown date';
            const groups = Array.isArray(s.muscle_groups) ? s.muscle_groups.join(', ') : (s.muscle_groups || '—');
            const status = s.status || 'done';
            const tagClass = status === 'done' || status === 'finalized' ? 'tag-ok'
                : status === 'error' ? 'tag-err' : 'tag-warn';
            const isProcessing = status === 'processing';
            const cid = this._currentCustomerId || '';
            return `<div class="list-item">
                <div style="display:flex;justify-content:space-between;align-items:flex-start;width:100%;">
                    <div>
                        <div style="font-size:0.8125rem;">${date}</div>
                        <div class="meta">${groups}</div>
                        ${isProcessing ? `<div style="font-size:11px;color:var(--accent);margin-top:2px;"
                            data-scan-processing>Processing.</div>` : ''}
                    </div>
                    <div style="display:flex;flex-direction:column;align-items:flex-end;gap:4px;">
                        <span class="tag ${tagClass}">${status}</span>
                        ${cid && !isProcessing ? `<a href="#" style="font-size:11px;color:var(--accent);"
                            onclick="ScanPanel.viewReport(${cid},${s.id});return false;">Report</a>` : ''}
                    </div>
                </div>
            </div>`;
        }).join('');
    },

    async viewReport(customerId, scanId) {
        Studio.log(`Loading report for scan ${scanId}…`);
        const { ok, data } = await Studio.apiGet(`/api/customer/${customerId}/report/${scanId}`);
        if (!ok) {
            Studio.log(`Report load failed: ${(data && data.error) || 'Unknown'}`, 'error');
            return;
        }
        const url = data.url || data.report_url || null;
        if (url) {
            window.open(url, '_blank');
        } else {
            Studio.log('Report generated — no URL returned', 'error');
        }
    },

    async uploadScan() {
        const customerId = this._currentCustomerId;
        if (!customerId) {
            Studio.log('No customer selected', 'error');
            return;
        }
        const frontFile = document.getElementById('scan-file-front')?.files[0];
        const sideFile = document.getElementById('scan-file-side')?.files[0];
        if (!frontFile || !sideFile) {
            Studio.log('Please select both front and side photos', 'error');
            const status = document.getElementById('scan-upload-status');
            if (status) status.textContent = 'Select both front and side photos.';
            return;
        }

        const btn = document.getElementById('btn-upload-scan');
        if (btn) { btn.disabled = true; btn.textContent = 'Uploading…'; }
        const status = document.getElementById('scan-upload-status');
        if (status) status.textContent = 'Uploading…';

        if (Studio.MOCK_MODE) {
            await new Promise(r => setTimeout(r, 800));
            Studio.log('Mock: scan upload simulated');
            if (status) status.textContent = 'Upload complete (mock).';
            if (btn) { btn.disabled = false; btn.textContent = 'Upload Scan'; }
            document.dispatchEvent(new CustomEvent('scan-uploaded', { detail: { customerId } }));
            return;
        }

        this._stopProgressPoll(); // reset before reload

        const formData = new FormData();
        formData.append('front', frontFile);
        formData.append('side', sideFile);

        try {
            const url = `${Studio.API_BASE}/api/upload_scan/${customerId}`;
            const headers = Studio._token ? { 'Authorization': `Bearer ${Studio._token}` } : {};
            const resp = await fetch(url, { method: 'POST', headers, body: formData });
            const data = await resp.json();
            if (resp.ok) {
                Studio.log(`Scan uploaded — id ${data.scan_id || data.id || 'ok'}`);
                if (status) status.textContent = 'Upload complete.';
                await this.loadScans(customerId);
                document.dispatchEvent(new CustomEvent('scan-uploaded', { detail: { customerId, scanId: data.scan_id || data.id } }));
            } else {
                Studio.log(`Upload failed: ${data.error || resp.status}`, 'error');
                if (status) status.textContent = `Upload failed: ${data.error || resp.status}`;
            }
        } catch (e) {
            Studio.log(`Upload error: ${e.message}`, 'error');
            if (status) status.textContent = `Error: ${e.message}`;
        }

        if (btn) { btn.disabled = false; btn.textContent = 'Upload Scan'; }
    },

    // --- Camera connection simulation ---
    toggleConnect() {
        this.connected = !this.connected;
        const dot = document.getElementById('cam-dot');
        const label = document.getElementById('cam-label');
        const btn = document.getElementById('btn-cam-connect');
        const fpsEl = document.getElementById('cam-fps');

        if (this.connected) {
            if (dot) dot.style.background = '#22c55e';
            if (label) label.textContent = 'MatePad: Connected';
            if (btn) btn.textContent = 'Disconnect';
            if (fpsEl) fpsEl.style.display = '';
            this._startFakeFeed();
            Studio.log('Camera connected (simulated)');
        } else {
            if (dot) dot.style.background = '#ef4444';
            if (label) label.textContent = 'MatePad: Disconnected';
            if (btn) btn.textContent = 'Connect';
            if (fpsEl) fpsEl.style.display = 'none';
            this._stopFakeFeed();
            Studio.log('Camera disconnected');
        }
    },

    _startFakeFeed() {
        const placeholder = document.getElementById('cam-feed-placeholder');
        if (placeholder) {
            placeholder.style.color = '#22c55e';
            placeholder.textContent = 'Receiving frames…';
        }
        this._fpsTimer = setInterval(() => {
            this.frameCount += Math.floor(Math.random() * 4) + 1;
            this.fps = Math.floor(Math.random() * 8) + 22;
            const countEl = document.getElementById('cam-frame-count');
            const fpsEl = document.getElementById('cam-fps');
            if (countEl) countEl.textContent = `${this.frameCount} frames captured`;
            if (fpsEl) fpsEl.textContent = `${this.fps} fps`;
        }, 500);
    },

    _stopFakeFeed() {
        if (this._fpsTimer) { clearInterval(this._fpsTimer); this._fpsTimer = null; }
        const placeholder = document.getElementById('cam-feed-placeholder');
        if (placeholder) {
            placeholder.style.color = '';
            placeholder.textContent = 'No frames received';
        }
    },
};

document.addEventListener('DOMContentLoaded', () => ScanPanel.init());
