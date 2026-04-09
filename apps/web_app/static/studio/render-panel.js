/* GTD3D Studio — Render Panel
 * Right sidebar: local render controls, HD RunPod request, 3D reconstruction,
 * mesh list, body composition trigger, GPU status.
 */
const RenderPanel = {
    localRendered: false,
    hdRequested: false,
    _currentCustomerId: null,
    _currentScanId: null,
    _gpuTimer: null,
    meshes: [],

    init() {
        this._bind();
        this._renderReconstructSection();
        this._renderMeshList();
        this._renderBodyCompSection();
        this._renderGpuStatus();
        this._startGpuPoll();

        document.addEventListener('customer-selected', (e) => {
            this._currentCustomerId = e.detail.id;
            this._currentScanId = null;
            this._enableActions();
            this.loadMeshes(e.detail.id);
        });

        document.addEventListener('scan-uploaded', (e) => {
            this._currentScanId = (e.detail && e.detail.scanId) || null;
            this._showNewScanPrompt();
        });
    },

    _bind() {
        const btnLocal = document.getElementById('btn-render-local');
        const btnHD = document.getElementById('btn-request-hd');

        if (btnLocal) {
            btnLocal.addEventListener('click', () => {
                this.localRendered = true;
                btnLocal.textContent = 'Rendered \u2713';
                btnLocal.disabled = true;
                btnLocal.style.opacity = '0.6';
                Studio.log('Local render complete');
            });
        }

        if (btnHD) {
            btnHD.addEventListener('click', () => {
                if (this.hdRequested) return;
                this.hdRequested = true;
                btnHD.textContent = 'Requested \u2713';
                btnHD.disabled = true;
                btnHD.style.opacity = '0.6';
                Studio.log('HD render requested — see Progress tab');
                document.dispatchEvent(new CustomEvent('hd-requested'));
                Studio._activateNav('progress');
            });
        }
    },

    _renderReconstructSection() {
        const el = document.getElementById('render-reconstruct-section');
        if (!el) return;
        el.innerHTML = `
            <div style="border-top:1px solid rgba(255,255,255,0.08);margin:8px 0;"></div>
            <div style="font-size:11px;color:var(--text-dim);margin-bottom:6px;">3D RECONSTRUCTION</div>
            <button class="btn btn-sm" id="btn-reconstruct-3d" style="width:100%;margin-bottom:4px;" disabled
                onclick="RenderPanel.reconstruct3D()">Reconstruct 3D</button>
            <div id="reconstruct-prompt" style="font-size:11px;color:var(--accent);margin-top:4px;display:none;">
                New scan available — <a href="#" onclick="RenderPanel.reconstruct3D();return false;">reconstruct?</a>
            </div>
        `;
    },

    _renderMeshList() {
        const el = document.getElementById('render-mesh-list');
        if (!el) return;
        if (Studio.MOCK_MODE) {
            this._renderMockMeshes();
            return;
        }
        el.innerHTML = '<div class="empty-state">Select a customer to view meshes</div>';
    },

    _renderMockMeshes() {
        const el = document.getElementById('render-mesh-list');
        if (!el) return;
        const mockMeshes = [
            { id: 101, created_at: '2026-03-22T14:20:00', label: 'Scan #2 mesh' },
            { id: 102, created_at: '2026-04-01T09:15:00', label: 'Scan #3 mesh' },
        ];
        this._renderMeshItems(mockMeshes);
    },

    async loadMeshes(customerId) {
        const el = document.getElementById('render-mesh-list');
        if (!el) return;

        if (Studio.MOCK_MODE) {
            this._renderMockMeshes();
            return;
        }

        el.innerHTML = '<div class="empty-state">Loading…</div>';
        const { ok, data } = await Studio.apiGet(`/api/customer/${customerId}/meshes`);
        if (!ok) {
            el.innerHTML = '<div class="empty-state" style="color:var(--error);">Failed to load meshes</div>';
            return;
        }
        this.meshes = data.meshes || data || [];
        this._renderMeshItems(this.meshes);
    },

    _renderMeshItems(meshes) {
        const el = document.getElementById('render-mesh-list');
        if (!el) return;
        if (meshes.length === 0) {
            el.innerHTML = '<div class="empty-state">No meshes yet</div>';
            return;
        }
        el.innerHTML = meshes.map(m => {
            const date = m.created_at
                ? new Date(m.created_at).toLocaleDateString()
                : 'Unknown date';
            const label = m.label || m.name || `Mesh #${m.id}`;
            return `<div class="list-item">
                <div style="display:flex;justify-content:space-between;align-items:center;width:100%;">
                    <div>
                        <div style="font-size:0.8125rem;">${label}</div>
                        <div class="meta">${date}</div>
                    </div>
                    <button class="btn btn-sm"
                        onclick="RenderPanel.viewMesh(${m.id})">View 3D</button>
                </div>
            </div>`;
        }).join('');
    },

    viewMesh(meshId) {
        Studio.log(`Loading mesh ${meshId} in viewport…`);
        Studio.showInViewport('glb', `${Studio.API_BASE}/api/mesh/${meshId}.glb`);
    },

    _renderBodyCompSection() {
        const el = document.getElementById('render-bodycomp-section');
        if (!el) return;
        el.innerHTML = `
            <div style="border-top:1px solid rgba(255,255,255,0.08);margin:8px 0;"></div>
            <div style="font-size:11px;color:var(--text-dim);margin-bottom:6px;">BODY COMPOSITION</div>
            <button class="btn btn-sm" id="btn-body-comp" style="width:100%;" disabled
                onclick="RenderPanel.triggerBodyComp()">Analyse Body Composition</button>
            <div id="body-comp-status" style="font-size:11px;color:var(--text-dim);margin-top:4px;"></div>
        `;
    },

    _renderGpuStatus() {
        const el = document.getElementById('render-gpu-status');
        if (!el) return;
        el.innerHTML = `
            <div style="border-top:1px solid rgba(255,255,255,0.08);margin:8px 0;"></div>
            <div style="display:flex;justify-content:space-between;align-items:center;font-size:11px;">
                <span style="color:var(--text-dim);">GPU</span>
                <span id="gpu-status-badge">
                    ${Studio.MOCK_MODE
                        ? '<span class="tag tag-ok">Ready</span>'
                        : '<span style="color:var(--text-dim);">Checking…</span>'}
                </span>
            </div>
        `;
    },

    _startGpuPoll() {
        if (Studio.MOCK_MODE) return;
        const poll = async () => {
            const { ok, data } = await Studio.apiGet('/api/gpu_status');
            const el = document.getElementById('gpu-status-badge');
            if (el && ok) {
                const avail = data.available !== false;
                el.innerHTML = avail
                    ? '<span class="tag tag-ok">Ready</span>'
                    : '<span class="tag tag-warn">Offline</span>';
            }
        };
        poll();
        this._gpuTimer = setInterval(poll, 30000);
    },

    _enableActions() {
        const ids = ['btn-reconstruct-3d', 'btn-body-comp'];
        ids.forEach(id => {
            const btn = document.getElementById(id);
            if (btn) btn.disabled = false;
        });
    },

    _showNewScanPrompt() {
        const el = document.getElementById('reconstruct-prompt');
        if (el) el.style.display = '';
        Studio.log('New scan available — trigger reconstruction from the Render panel');
    },

    async reconstruct3D() {
        const customerId = this._currentCustomerId;
        if (!customerId) { Studio.log('No customer selected', 'error'); return; }

        const btn = document.getElementById('btn-reconstruct-3d');
        if (btn) { btn.disabled = true; btn.textContent = 'Reconstructing…'; }
        const prompt = document.getElementById('reconstruct-prompt');
        if (prompt) prompt.style.display = 'none';

        if (Studio.MOCK_MODE) {
            await new Promise(r => setTimeout(r, 800));
            Studio.log('Mock: 3D reconstruction triggered');
            if (btn) { btn.disabled = false; btn.textContent = 'Reconstruct 3D'; }
            return;
        }

        const body = this._currentScanId ? { scan_id: this._currentScanId } : {};
        const { ok, data } = await Studio.apiPost(`/api/customer/${customerId}/reconstruct_3d`, body);
        if (ok) {
            Studio.log(`3D reconstruction started — job ${data.job_id || data.id || 'ok'}`);
            Studio._activateNav('progress');
        } else {
            Studio.log(`Reconstruction failed: ${(data && data.error) || 'Unknown'}`, 'error');
        }
        if (btn) { btn.disabled = false; btn.textContent = 'Reconstruct 3D'; }
    },

    async triggerBodyComp() {
        const customerId = this._currentCustomerId;
        if (!customerId) { Studio.log('No customer selected', 'error'); return; }

        const btn = document.getElementById('btn-body-comp');
        const status = document.getElementById('body-comp-status');
        if (btn) { btn.disabled = true; btn.textContent = 'Analysing…'; }
        if (status) status.textContent = 'Running analysis…';

        if (Studio.MOCK_MODE) {
            await new Promise(r => setTimeout(r, 800));
            Studio.log('Mock: body composition analysis triggered');
            if (status) status.textContent = 'Analysis complete (mock).';
            if (btn) { btn.disabled = false; btn.textContent = 'Analyse Body Composition'; }
            return;
        }

        const { ok, data } = await Studio.apiPost(`/api/customer/${customerId}/body_composition`, {});
        if (ok) {
            Studio.log(`Body composition analysis started — job ${data.job_id || data.id || 'ok'}`);
            if (status) status.textContent = 'Analysis queued.';
        } else {
            Studio.log(`Body comp failed: ${(data && data.error) || 'Unknown'}`, 'error');
            if (status) status.textContent = 'Failed.';
        }
        if (btn) { btn.disabled = false; btn.textContent = 'Analyse Body Composition'; }
    },
};

document.addEventListener('DOMContentLoaded', () => RenderPanel.init());
