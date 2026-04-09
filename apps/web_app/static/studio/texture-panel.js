/* GTD3D Studio — Texture Panel
 * Right sidebar: body-part texture checklist with approve/re-capture actions.
 */
const TexturePanel = {
    _customerId: null,
    _scanId: null,
    _approvals: {},   // loaded from / persisted to localStorage

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

    // Mock statuses used when MOCK_MODE is on
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

    // In-memory region state built from defs + API/mock data
    regions: [],

    init() {
        document.addEventListener('customer-selected', (e) => {
            this._customerId = e.detail.id;
            this._scanId = null;
            this._loadApprovals();
            if (Studio.MOCK_MODE) {
                this._buildRegions(this._MOCK_STATUSES);
                this.render();
            } else {
                this._loadFromAPI(e.detail.id);
            }
        });
        // Start with mock data visible before any customer is selected
        if (Studio.MOCK_MODE) {
            this._buildRegions(this._MOCK_STATUSES);
        } else {
            this._buildRegions({});
        }
        this.render();
    },

    _buildRegions(statusMap) {
        this.regions = this._REGION_DEFS.map(def => ({
            ...def,
            status: statusMap[def.id] || 'pending',
        }));
    },

    // ─── API load ────────────────────────────────────────────────────────────

    async _loadFromAPI(customerId) {
        const el = document.getElementById('texture-parts');
        if (el) el.innerHTML = '<div style="color:var(--text-dim);font-size:12px;">Loading…</div>';

        const { ok, data } = await Studio.apiGet(`/api/customer/${customerId}/scans`);
        if (!ok) {
            Studio.log('Texture: could not load scans', 'error');
            this._buildRegions({});
            this.render();
            return;
        }

        const scans = data.scans || data || [];
        // Use the most recent scan
        const sorted = [...scans].sort((a, b) =>
            new Date(b.created_at || 0) - new Date(a.created_at || 0)
        );
        const latest = sorted[0] || null;
        this._scanId = latest ? (latest.id || latest.session_id || null) : null;

        // Build status map from scan region data if present
        const statusMap = {};
        if (latest && latest.regions) {
            Object.assign(statusMap, latest.regions);
        } else if (latest) {
            // No per-region data — mark all as captured if scan exists, else pending
            this._REGION_DEFS.forEach(d => { statusMap[d.id] = 'captured'; });
        }

        this._buildRegions(statusMap);
        this.render();
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
    },

    _saveApprovals() {
        const key = this._approvalKey(this._customerId, this._scanId);
        try { localStorage.setItem(key, JSON.stringify(this._approvals)); } catch (_) {}
    },

    _isApproved(regionId) {
        return !!this._approvals[regionId];
    },

    // ─── Actions ─────────────────────────────────────────────────────────────

    approve(id) {
        const region = this.regions.find(r => r.id === id);
        if (!region) return;
        region.status = 'approved';
        this._approvals[id] = true;
        this._saveApprovals();
        Studio.log(`Approved texture: ${region.name}`);
        this.render();
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
        this.render();
    },

    resetAll() {
        this.regions.forEach(r => {
            if (r.status === 'approved') r.status = 'captured';
        });
        this._approvals = {};
        this._saveApprovals();
        Studio.log('All approvals reset');
        this.render();
    },

    requestRecapture(id) {
        const region = this.regions.find(r => r.id === id);
        if (!region) return;
        region.status = 'pending';
        Studio.log(`Re-capture requested: ${region.name}`);
        // Emit event so scan panel can prepare for targeted re-capture
        document.dispatchEvent(new CustomEvent('recapture-requested', {
            detail: { region: id, customerId: this._customerId },
        }));
        this.render();
    },

    showPreview(id) {
        const region = this.regions.find(r => r.id === id);
        if (!region || !this._scanId || Studio.MOCK_MODE) return;
        // Construct image URL from scan upload path convention
        const imgUrl = `${Studio.API_BASE}/web_app/uploads/${this._customerId}/${this._scanId}/texture_${id}.jpg`;
        Studio.showInViewport('image', imgUrl);
        Studio.log(`Previewing texture: ${region.name}`);
    },

    // ─── Render ──────────────────────────────────────────────────────────────

    render() {
        const el = document.getElementById('texture-parts');
        if (!el) return;

        const total = this.regions.length;
        const approvedCount = this.regions.filter(r => r.status === 'approved').length;
        const capturedCount = this.regions.filter(r => r.status === 'captured').length;
        const readyCount = approvedCount + capturedCount;

        const rowStyle = 'display:flex;align-items:center;justify-content:space-between;padding:5px 0;border-bottom:1px solid rgba(255,255,255,0.05);font-size:11px;';

        const rows = this.regions.map(r => {
            const color = this._statusColors[r.status] || '#6b7280';
            const label = r.status.charAt(0).toUpperCase() + r.status.slice(1);
            const isGood = r.status === 'captured';
            const isApproved = r.status === 'approved';
            const isBad = !isGood && !isApproved;

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

            return `<div style="${rowStyle}" onclick="TexturePanel.showPreview('${r.id}')" style="cursor:pointer;">
                <span style="flex:1;cursor:pointer;">${r.name}</span>
                <span style="color:${color};width:56px;text-align:center;font-size:10px;">${label}</span>
                <span style="width:96px;text-align:right;">${action}</span>
            </div>`;
        }).join('');

        const batchBar = `
            <div style="display:flex;gap:4px;margin-top:6px;">
                <button class="btn btn-sm btn-accent" style="flex:1;font-size:10px;"
                    onclick="TexturePanel.approveAllCaptured()">Approve All Captured</button>
                <button class="btn btn-sm" style="font-size:10px;"
                    onclick="TexturePanel.resetAll()">Reset All</button>
            </div>`;

        el.innerHTML = `
            <div style="margin-bottom:6px;font-size:12px;color:var(--text-dim);">
                ${approvedCount}/${total} approved &nbsp;·&nbsp; ${readyCount}/${total} ready
            </div>
            ${rows}
            ${batchBar}
        `;
    },
};

document.addEventListener('DOMContentLoaded', () => TexturePanel.init());
