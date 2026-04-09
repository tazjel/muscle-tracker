/* GTD3D Studio — Texture Panel
 * Right sidebar: body-part texture checklist with approve/re-capture actions.
 * Also: skin region capture, PBR generation, room textures, HDRI environments.
 */
const TexturePanel = {
    _customerId: null,
    _scanId: null,
    _approvals: {},   // persisted to localStorage keyed by customerId-scanId-regionId
    _view: 'checklist', // 'checklist' | 'skin' | 'pbr' | 'room' | 'env'

    // 16 body-part regions for texture review
    _REGION_DEFS: [
        { id: 'head',         name: 'Head' },
        { id: 'neck',         name: 'Neck' },
        { id: 'chest',        name: 'Chest' },
        { id: 'back',         name: 'Back' },
        { id: 'abdomen',      name: 'Abdomen' },
        { id: 'upper-arm-l',  name: 'Upper Arm L' },
        { id: 'upper-arm-r',  name: 'Upper Arm R' },
        { id: 'forearm-l',    name: 'Forearm L' },
        { id: 'forearm-r',    name: 'Forearm R' },
        { id: 'hand-l',       name: 'Hand L' },
        { id: 'hand-r',       name: 'Hand R' },
        { id: 'hip',          name: 'Hip' },
        { id: 'thigh-l',      name: 'Thigh L' },
        { id: 'thigh-r',      name: 'Thigh R' },
        { id: 'calf-l',       name: 'Calf L' },
        { id: 'calf-r',       name: 'Calf R' },
    ],

    // Mock statuses (used when MOCK_MODE is on)
    _MOCK_STATUSES: {
        head: 'captured', neck: 'captured', chest: 'captured', back: 'missing',
        abdomen: 'blurry', 'upper-arm-l': 'captured', 'upper-arm-r': 'captured',
        'forearm-l': 'missing', 'forearm-r': 'captured', 'hand-l': 'captured',
        'hand-r': 'captured', hip: 'blurry', 'thigh-l': 'captured',
        'thigh-r': 'captured', 'calf-l': 'missing', 'calf-r': 'captured',
    },

    _statusColors: {
        captured: '#22c55e',
        missing:  '#ef4444',
        blurry:   '#eab308',
        approved: '#6366f1',
        pending:  '#6b7280',
    },

    // Skin region capture (separate from body-part checklist)
    _skinRegions: ['face', 'torso', 'arms', 'legs', 'hands', 'feet'],
    _capturedSkinRegions: [],

    // In-memory region state
    regions: [],

    init() {
        document.addEventListener('customer-selected', (e) => {
            this._customerId = e.detail.id;
            this._scanId = null;
            this._loadApprovals();
            if (Studio.MOCK_MODE) {
                this._buildRegions(this._MOCK_STATUSES);
                this._renderChecklist();
            } else {
                this._loadFromAPI(e.detail.id);
            }
        });
        // Initial render before any customer selected
        if (Studio.MOCK_MODE) {
            this._buildRegions(this._MOCK_STATUSES);
        } else {
            this._buildRegions({});
        }
        this._renderChecklist();
    },

    _buildRegions(statusMap) {
        this.regions = this._REGION_DEFS.map(def => ({
            ...def,
            status: statusMap[def.id] || 'pending',
        }));
    },

    // ─── API load ─────────────────────────────────────────────────────────────

    async _loadFromAPI(customerId) {
        const el = document.getElementById('texture-status');
        if (el) el.innerHTML = '<div class="spinner"></div>';

        const { ok, data } = await Studio.apiGet(`/api/customer/${customerId}/scans`);
        if (!ok) {
            Studio.log('Texture: could not load scans', 'error');
            this._buildRegions({});
            this._renderChecklist();
            return;
        }

        const scans = data.scans || data || [];
        const sorted = [...scans].sort((a, b) =>
            new Date(b.created_at || 0) - new Date(a.created_at || 0)
        );
        const latest = sorted[0] || null;
        this._scanId = latest ? (latest.id || latest.session_id || null) : null;

        const statusMap = {};
        if (latest && latest.regions) {
            Object.assign(statusMap, latest.regions);
        } else if (latest) {
            this._REGION_DEFS.forEach(d => { statusMap[d.id] = 'captured'; });
        }

        this._buildRegions(statusMap);
        this._renderChecklist();
    },

    // ─── Approvals (localStorage) ─────────────────────────────────────────────

    _approvalKey(customerId, scanId) {
        return `tp-approvals-${customerId}-${scanId || 'default'}`;
    },

    _loadApprovals() {
        const key = this._approvalKey(this._customerId, this._scanId);
        try {
            const raw = localStorage.getItem(key);
            this._approvals = raw ? JSON.parse(raw) : {};
        } catch (_) {
            this._approvals = {};
        }
        // Apply stored approvals to current region states
        this.regions.forEach(r => {
            if (this._approvals[r.id] && r.status === 'captured') r.status = 'approved';
        });
    },

    _saveApprovals() {
        const key = this._approvalKey(this._customerId, this._scanId);
        try { localStorage.setItem(key, JSON.stringify(this._approvals)); } catch (_) {}
    },

    // ─── Checklist actions ────────────────────────────────────────────────────

    approve(id) {
        const region = this.regions.find(r => r.id === id);
        if (!region) return;
        region.status = 'approved';
        this._approvals[id] = true;
        this._saveApprovals();
        Studio.log(`Approved texture: ${region.name}`);
        this._renderChecklist();
    },

    approveAllCaptured() {
        let count = 0;
        this.regions.forEach(r => {
            if (r.status === 'captured') {
                r.status = 'approved';
                this._approvals[r.id] = true;
                count++;
            }
        });
        this._saveApprovals();
        Studio.log(`Approved all captured regions (${count})`);
        this._renderChecklist();
    },

    resetAll() {
        this.regions.forEach(r => {
            if (r.status === 'approved') r.status = 'captured';
        });
        this._approvals = {};
        this._saveApprovals();
        Studio.log('All approvals reset');
        this._renderChecklist();
    },

    requestRecapture(id) {
        const region = this.regions.find(r => r.id === id);
        if (!region) return;
        region.status = 'pending';
        Studio.log(`Re-capture requested: ${region.name}`);
        document.dispatchEvent(new CustomEvent('recapture-requested', {
            detail: { region: id, customerId: this._customerId },
        }));
        this._renderChecklist();
    },

    showPreview(id) {
        const region = this.regions.find(r => r.id === id);
        if (!region || !this._scanId || Studio.MOCK_MODE) return;
        const imgUrl = `${Studio.API_BASE}/web_app/uploads/${this._customerId}/${this._scanId}/texture_${id}.jpg`;
        Studio.showInViewport('image', imgUrl);
        Studio.log(`Previewing texture: ${region.name}`);
    },

    // ─── Render: 16-region checklist ─────────────────────────────────────────

    _renderChecklist() {
        const el = document.getElementById('texture-status');
        if (!el) return;

        const total = this.regions.length;
        const approvedCount = this.regions.filter(r => r.status === 'approved').length;
        const capturedCount = this.regions.filter(r => r.status === 'captured').length;
        const readyCount = approvedCount + capturedCount;

        const rows = this.regions.map(r => {
            const color = this._statusColors[r.status] || '#6b7280';
            const label = r.status.charAt(0).toUpperCase() + r.status.slice(1);
            const isGood = r.status === 'captured';
            const isApproved = r.status === 'approved';

            let action;
            if (isApproved) {
                action = '<span style="color:#6366f1;font-size:10px;">Approved</span>';
            } else if (isGood) {
                action = `<button onclick="TexturePanel.approve('${r.id}')"
                    style="background:none;border:1px solid #6366f1;color:#6366f1;border-radius:3px;padding:2px 5px;font-size:10px;cursor:pointer;">Approve</button>`;
            } else {
                action = `<button onclick="TexturePanel.requestRecapture('${r.id}')"
                    style="background:none;border:1px solid #ef4444;color:#ef4444;border-radius:3px;padding:2px 5px;font-size:10px;cursor:pointer;">Re-capture</button>`;
            }

            return `<div style="display:flex;align-items:center;justify-content:space-between;padding:5px 0;border-bottom:1px solid rgba(255,255,255,0.05);font-size:11px;cursor:pointer;"
                         onclick="TexturePanel.showPreview('${r.id}')">
                <span style="flex:1;">${r.name}</span>
                <span style="color:${color};width:54px;text-align:center;font-size:10px;">${label}</span>
                <span style="width:90px;text-align:right;">${action}</span>
            </div>`;
        }).join('');

        el.innerHTML = `
            <div style="margin-bottom:6px;font-size:12px;color:var(--text-secondary);">
                ${approvedCount}/${total} approved &nbsp;·&nbsp; ${readyCount}/${total} ready
            </div>
            ${rows}
            <div style="display:flex;gap:4px;margin-top:8px;">
                <button class="btn btn-sm btn-accent" style="flex:1;font-size:10px;"
                    onclick="TexturePanel.approveAllCaptured()">Approve All Captured</button>
                <button class="btn btn-sm" style="font-size:10px;"
                    onclick="TexturePanel.resetAll()">Reset All</button>
            </div>
            <div style="border-top:1px solid rgba(255,255,255,0.08);margin-top:10px;padding-top:8px;display:flex;gap:4px;flex-wrap:wrap;">
                <button class="btn btn-sm" style="font-size:10px;"
                    onclick="TexturePanel.loadSkinRegions(${this._customerId})">Skin Capture</button>
                <button class="btn btn-sm" style="font-size:10px;"
                    onclick="TexturePanel.viewPBR(${this._customerId})">PBR Maps</button>
                <button class="btn btn-sm" style="font-size:10px;"
                    onclick="TexturePanel.loadRoomTextures(${this._customerId})">Room</button>
                <button class="btn btn-sm" style="font-size:10px;"
                    onclick="TexturePanel.browseEnvironments()">HDRI</button>
            </div>
        `;
    },

    // ─── Skin region capture ──────────────────────────────────────────────────

    async loadSkinRegions(customerId) {
        if (!customerId) return;
        const el = document.getElementById('texture-status');
        if (el) el.innerHTML = '<div class="spinner"></div>';

        if (Studio.MOCK_MODE) {
            this._renderRegionGrid([], customerId);
            return;
        }

        const { ok, data } = await Studio.apiGet(`/api/customer/${customerId}/skin_regions`);
        if (!ok) {
            if (el) el.innerHTML = '<div class="empty-state" style="color:var(--error);">Failed to load regions</div>';
            return;
        }
        this._capturedSkinRegions = data.captured || data || [];
        this._renderRegionGrid(this._capturedSkinRegions, customerId);
    },

    _renderRegionGrid(captured, customerId) {
        const el = document.getElementById('texture-status');
        if (!el) return;
        const capturedSet = new Set(Array.isArray(captured) ? captured.map(r => r.region || r) : []);
        const cards = this._skinRegions.map(region => {
            const isCaptured = capturedSet.has(region);
            const thumb = isCaptured
                ? `<img src="/web_app/api/customer/${customerId}/skin_texture/${region}/thumb" style="width:100%;border-radius:var(--radius-sm);margin-top:0.25rem;" onerror="this.style.display='none'">`
                : '';
            const action = isCaptured
                ? `<button class="btn btn-sm" onclick="TexturePanel.uploadSkinTexture(${customerId}, '${region}')" title="Re-upload">&#8635;</button>`
                : `<button class="btn btn-accent btn-sm" onclick="TexturePanel.uploadSkinTexture(${customerId}, '${region}')">Upload</button>`;
            return `<div class="panel" style="padding:0.5rem;text-align:center;">
                <div style="font-size:0.8125rem;font-weight:600;text-transform:capitalize;">${region}</div>
                <span class="tag ${isCaptured ? 'tag-ok' : 'tag-warn'}" style="margin:0.25rem 0;display:inline-block;">
                    ${isCaptured ? 'Captured' : 'Missing'}
                </span>
                ${thumb}
                <div style="margin-top:0.5rem;">${action}</div>
            </div>`;
        });

        el.innerHTML = `
            <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:0.5rem;">
                <strong style="font-size:0.875rem;">Skin Capture</strong>
                <button class="btn btn-sm" onclick="TexturePanel._renderChecklist()">&#8592; Checklist</button>
            </div>
            <div style="display:grid;grid-template-columns:1fr 1fr;gap:0.5rem;margin-bottom:0.75rem;">
                ${cards.join('')}
            </div>
        `;
    },

    async uploadSkinTexture(customerId, region) {
        if (Studio.MOCK_MODE) { Studio.log(`Upload skin texture (mock): ${region}`); return; }
        const input = document.createElement('input');
        input.type = 'file';
        input.accept = 'image/*';
        input.onchange = async () => {
            if (!input.files.length) return;
            Studio.log(`Uploading ${region} texture…`);
            const formData = new FormData();
            formData.append('file', input.files[0]);
            formData.append('region', region);
            const { ok, data } = await Studio.apiPost(`/api/customer/${customerId}/skin_texture`, formData);
            if (ok) {
                Studio.log(`Uploaded ${region} texture`);
                this.loadSkinRegions(customerId);
            } else {
                Studio.log(`Upload failed: ${data?.error || 'Unknown error'}`, 'error');
            }
        };
        input.click();
    },

    // ─── PBR maps ─────────────────────────────────────────────────────────────

    async viewPBR(customerId) {
        if (!customerId) return;
        const el = document.getElementById('texture-status');
        if (el) el.innerHTML = '<div class="spinner"></div>';

        if (Studio.MOCK_MODE) {
            this._renderPBRPreview({ available: [], maps: [] }, customerId);
            return;
        }

        const { ok, data } = await Studio.apiGet(`/api/customer/${customerId}/pbr_textures`);
        if (!ok) {
            if (el) el.innerHTML = '<div class="empty-state" style="color:var(--error);">Failed to load PBR status</div>';
            return;
        }
        this._renderPBRPreview(data, customerId);
    },

    _renderPBRPreview(data, customerId) {
        const el = document.getElementById('texture-status');
        if (!el) return;
        const types = ['albedo', 'normal', 'roughness', 'ao', 'definition', 'displacement'];
        const available = new Set(data.available || data.maps || []);
        const cards = types.map(type => {
            const isReady = available.has(type);
            const thumb = isReady
                ? `<img src="/web_app/api/customer/${customerId}/pbr_textures/${type}" style="width:100%;border-radius:var(--radius-sm);margin-top:0.25rem;" onerror="this.style.display='none'">`
                : `<div style="height:48px;background:var(--bg-primary);border-radius:var(--radius-sm);margin-top:0.25rem;display:flex;align-items:center;justify-content:center;font-size:0.7rem;color:var(--text-secondary);">Not generated</div>`;
            return `<div class="panel" style="padding:0.5rem;text-align:center;">
                <div style="font-size:0.8125rem;font-weight:600;text-transform:capitalize;">${type}</div>
                <span class="tag ${isReady ? 'tag-ok' : 'tag-warn'}" style="margin:0.25rem 0;display:inline-block;">
                    ${isReady ? 'Ready' : 'Pending'}
                </span>
                ${thumb}
            </div>`;
        });

        const generated = data.generated_at ? `<div style="font-size:0.75rem;color:var(--text-secondary);margin-bottom:0.5rem;">Generated: ${data.generated_at}</div>` : '';

        el.innerHTML = `
            <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:0.5rem;">
                <strong style="font-size:0.875rem;">PBR Texture Maps</strong>
                <button class="btn btn-sm" onclick="TexturePanel._renderChecklist()">&#8592; Back</button>
            </div>
            ${generated}
            <div style="display:grid;grid-template-columns:1fr 1fr;gap:0.5rem;">
                ${cards.join('')}
            </div>
        `;
    },

    // ─── Room textures ────────────────────────────────────────────────────────

    async loadRoomTextures(customerId) {
        if (!customerId) return;
        const el = document.getElementById('texture-status');
        if (el) el.innerHTML = '<div class="spinner"></div>';

        if (Studio.MOCK_MODE) {
            this._renderRoomGrid({ captured: [], surfaces: [] }, customerId);
            return;
        }

        const { ok, data } = await Studio.apiGet(`/api/customer/${customerId}/room_textures`);
        if (!ok) {
            if (el) el.innerHTML = '<div class="empty-state" style="color:var(--error);">Failed to load room textures</div>';
            return;
        }
        this._renderRoomGrid(data, customerId);
    },

    _renderRoomGrid(data, customerId) {
        const el = document.getElementById('texture-status');
        if (!el) return;
        const surfaces = ['floor', 'walls', 'ceiling'];
        const captured = new Set(data.captured || data.surfaces || []);
        const cards = surfaces.map(surface => {
            const isReady = captured.has(surface);
            return `<div class="panel" style="padding:0.5rem;text-align:center;">
                <div style="font-size:0.8125rem;font-weight:600;text-transform:capitalize;">${surface}</div>
                <span class="tag ${isReady ? 'tag-ok' : 'tag-warn'}" style="margin:0.25rem 0;display:inline-block;">
                    ${isReady ? 'Captured' : 'Missing'}
                </span>
                <div style="margin-top:0.5rem;">
                    <button class="btn ${isReady ? 'btn-sm' : 'btn-accent btn-sm'}" onclick="TexturePanel.uploadRoomTexture(${customerId}, '${surface}')">
                        ${isReady ? '&#8635; Re-upload' : 'Upload'}
                    </button>
                </div>
            </div>`;
        });

        el.innerHTML = `
            <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:0.5rem;">
                <strong style="font-size:0.875rem;">Room Textures</strong>
                <button class="btn btn-sm" onclick="TexturePanel._renderChecklist()">&#8592; Back</button>
            </div>
            <div style="display:grid;grid-template-columns:1fr 1fr 1fr;gap:0.5rem;margin-bottom:0.75rem;">
                ${cards.join('')}
            </div>
            <div class="btn-row">
                <button class="btn btn-sm" onclick="TexturePanel.browseEnvironments()">Browse HDRI Environments</button>
            </div>
        `;
    },

    async uploadRoomTexture(customerId, surface) {
        if (Studio.MOCK_MODE) { Studio.log(`Upload room texture (mock): ${surface}`); return; }
        const input = document.createElement('input');
        input.type = 'file';
        input.accept = 'image/*';
        input.onchange = async () => {
            if (!input.files.length) return;
            Studio.log(`Uploading ${surface} texture…`);
            const formData = new FormData();
            formData.append('file', input.files[0]);
            formData.append('surface', surface);
            const { ok, data } = await Studio.apiPost(`/api/customer/${customerId}/room_texture`, formData);
            if (ok) {
                Studio.log(`Uploaded ${surface} texture`);
                this.loadRoomTextures(customerId);
            } else {
                Studio.log(`Upload failed: ${data?.error || 'Unknown error'}`, 'error');
            }
        };
        input.click();
    },

    // ─── HDRI environments ────────────────────────────────────────────────────

    async browseEnvironments() {
        const el = document.getElementById('texture-status');
        if (el) el.innerHTML = '<div class="spinner"></div>';

        if (Studio.MOCK_MODE) {
            this._renderEnvironments([], this._customerId);
            return;
        }

        const { ok, data } = await Studio.apiGet('/api/room_assets/hdri');
        if (!ok) {
            if (el) el.innerHTML = '<div class="empty-state" style="color:var(--error);">Failed to load environments</div>';
            return;
        }
        this._renderEnvironments(data.environments || data || [], this._customerId);
    },

    _renderEnvironments(envs, customerId) {
        const el = document.getElementById('texture-status');
        if (!el) return;
        const backBtn = `<button class="btn btn-sm" onclick="TexturePanel._renderChecklist()">&#8592; Back</button>`;

        if (envs.length === 0) {
            el.innerHTML = `
                <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:0.5rem;">
                    <strong style="font-size:0.875rem;">HDRI Environments</strong>
                    ${backBtn}
                </div>
                <div class="empty-state">No environments available</div>
            `;
            return;
        }

        const cards = envs.map(env => {
            const name = env.name || env;
            const preview = env.preview_url
                ? `<img src="${env.preview_url}" style="width:100%;border-radius:var(--radius-sm);margin-bottom:0.25rem;" onerror="this.style.display='none'">`
                : '';
            return `<div class="panel" style="padding:0.5rem;text-align:center;cursor:pointer;" onclick="Studio.log('Environment: ${name}')">
                ${preview}
                <div style="font-size:0.8125rem;text-transform:capitalize;">${name}</div>
                <span class="tag" style="margin-top:0.25rem;display:inline-block;">${env.type || 'HDRI'}</span>
            </div>`;
        });

        el.innerHTML = `
            <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:0.5rem;">
                <strong style="font-size:0.875rem;">HDRI Environments</strong>
                ${backBtn}
            </div>
            <div style="display:grid;grid-template-columns:1fr 1fr;gap:0.5rem;">
                ${cards.join('')}
            </div>
        `;
    },
};

document.addEventListener('DOMContentLoaded', () => TexturePanel.init());
