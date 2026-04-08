/* GTD3D Studio — Scan Panel
 * Left sidebar: scan history, upload (2-image and quad), scan selection.
 * Populates #scan-list (scans) and #mesh-list (meshes).
 * Fires viewport-load event when a GLB is available.
 */
const ScanPanel = {
    scans: [],
    meshes: [],
    selectedScan: null,
    muscleGroups: [],

    // Hidden file inputs, created once at init
    _inputFront: null,
    _inputSide: null,
    _inputQuad: null,

    init() {
        this._createFileInputs();
        this._injectUploadButtons();
        document.addEventListener('customer-selected', (e) => {
            this.scans = [];
            this.meshes = [];
            this.selectedScan = null;
            this.loadScans(e.detail.id);
            this.loadMeshes(e.detail.id);
            this.loadMuscleGroups();
        });
    },

    // --- File inputs (hidden, reused) ---
    _createFileInputs() {
        const make = (id, multiple) => {
            const el = document.createElement('input');
            el.type = 'file';
            el.id = id;
            el.accept = 'image/*';
            el.multiple = multiple;
            el.style.display = 'none';
            document.body.appendChild(el);
            return el;
        };
        this._inputFront = make('_scan-front', false);
        this._inputSide  = make('_scan-side',  false);
        this._inputQuad  = make('_scan-quad',  true);
    },

    // Inject upload buttons into the scan panel body, below #scan-list
    _injectUploadButtons() {
        const panel = document.getElementById('panel-scans');
        if (!panel) return;
        const body = panel.querySelector('.panel-body');
        if (!body) return;

        const btns = document.createElement('div');
        btns.id = 'scan-upload-btns';
        btns.className = 'btn-row';
        btns.style.cssText = 'margin-top:0.5rem;flex-wrap:wrap;';
        btns.innerHTML = `
            <button class="btn btn-sm btn-accent" id="btn-upload-scan" disabled
                onclick="ScanPanel._startUpload()">Upload Scan</button>
            <button class="btn btn-sm" id="btn-upload-quad" disabled
                onclick="ScanPanel._startQuadUpload()">Quad Scan</button>
        `;
        body.appendChild(btns);
    },

    _setUploadEnabled(enabled) {
        const b1 = document.getElementById('btn-upload-scan');
        const b2 = document.getElementById('btn-upload-quad');
        if (b1) b1.disabled = !enabled;
        if (b2) b2.disabled = !enabled;
    },

    // --- Scan list ---
    async loadScans(customerId) {
        const list = document.getElementById('scan-list');
        if (list) list.innerHTML = '<div class="empty-state"><span class="spinner"></span> Loading...</div>';

        const { ok, data } = await Studio.apiGet(`/api/customer/${customerId}/scans`);
        if (!ok) {
            if (list) list.innerHTML = '<div class="empty-state" style="color:var(--error);">Failed to load scans</div>';
            return;
        }
        this.scans = data.scans || data || [];
        this._setUploadEnabled(true);
        this._renderScans();
    },

    _renderScans() {
        const el = document.getElementById('scan-list');
        if (!el) return;
        if (this.scans.length === 0) {
            el.innerHTML = '<div class="empty-state">No scans yet — upload one below</div>';
            return;
        }
        el.innerHTML = this.scans.map(scan => {
            const active = this.selectedScan && this.selectedScan.id === scan.id ? 'active' : '';
            const date = scan.created_on
                ? new Date(scan.created_on).toLocaleDateString()
                : '—';
            const group = scan.muscle_group || 'General';
            const defScore = scan.definition_score != null
                ? scan.definition_score.toFixed(1)
                : null;
            const tagClass = defScore
                ? (defScore >= 7 ? 'tag-ok' : defScore >= 4 ? 'tag-warn' : 'tag-err')
                : 'tag-info';
            const defTag = defScore
                ? `<span class="tag ${tagClass}">${defScore}</span>`
                : '';
            const vol = scan.volume_cm3 != null
                ? `${scan.volume_cm3.toFixed(0)} cm³`
                : '';
            const growth = scan.growth_pct != null
                ? `<span class="tag tag-ok">+${scan.growth_pct.toFixed(1)}%</span>`
                : '';
            return `<div class="list-item ${active}" onclick="ScanPanel.selectScan(${scan.id})">
                <div style="flex:1;min-width:0;">
                    <div style="display:flex;align-items:center;gap:0.4rem;flex-wrap:wrap;">
                        <span>${group}</span>
                        ${defTag}
                        ${growth}
                    </div>
                    <div class="meta">${date}${vol ? ' · ' + vol : ''}</div>
                </div>
            </div>`;
        }).join('');
    },

    // --- Mesh list ---
    async loadMeshes(customerId) {
        const list = document.getElementById('mesh-list');
        if (list) list.innerHTML = '<div class="empty-state"><span class="spinner"></span> Loading...</div>';

        const { ok, data } = await Studio.apiGet(`/api/customer/${customerId}/meshes`);
        if (!ok) {
            if (list) list.innerHTML = '<div class="empty-state" style="color:var(--error);">Failed to load meshes</div>';
            return;
        }
        this.meshes = data.meshes || data || [];
        this._renderMeshes();
    },

    _renderMeshes() {
        const el = document.getElementById('mesh-list');
        if (!el) return;
        if (this.meshes.length === 0) {
            el.innerHTML = '<div class="empty-state">No meshes yet</div>';
            return;
        }
        el.innerHTML = this.meshes.map(mesh => {
            const date = mesh.created_on
                ? new Date(mesh.created_on).toLocaleDateString()
                : '—';
            const verts = mesh.vertex_count ? `${mesh.vertex_count.toLocaleString()} verts` : '';
            const faces = mesh.face_count  ? `${mesh.face_count.toLocaleString()} faces` : '';
            const geo = [verts, faces].filter(Boolean).join(' · ');
            return `<div class="list-item" onclick="ScanPanel.loadMeshById(${mesh.id})">
                <div style="flex:1;min-width:0;">
                    <div>Mesh #${mesh.id}</div>
                    <div class="meta">${date}${geo ? ' · ' + geo : ''}</div>
                </div>
                <button class="btn-icon" title="Load in viewport"
                    onclick="event.stopPropagation();ScanPanel.loadMeshById(${mesh.id})">&#9654;</button>
            </div>`;
        }).join('');
    },

    // --- Muscle groups (right sidebar) ---
    async loadMuscleGroups() {
        const el = document.getElementById('muscle-groups');
        if (!el) return;
        const { ok, data } = await Studio.apiGet('/api/muscle_groups');
        if (!ok) {
            this.muscleGroups = [];
            el.innerHTML = '<div class="empty-state" style="color:var(--error);">Failed to load</div>';
            return;
        }
        this.muscleGroups = data.groups || data || [];
        this._renderMuscleGroups();
    },

    _renderMuscleGroups() {
        const el = document.getElementById('muscle-groups');
        if (!el) return;
        if (this.muscleGroups.length === 0) {
            el.innerHTML = '<div class="empty-state">No muscle groups</div>';
            return;
        }
        // Tally scan counts per group
        const counts = {};
        this.scans.forEach(s => {
            if (s.muscle_group) counts[s.muscle_group] = (counts[s.muscle_group] || 0) + 1;
        });
        el.innerHTML = this.muscleGroups.map(g => {
            const n = counts[g] || 0;
            return `<div class="list-item" onclick="ScanPanel._filterByGroup('${g}')">
                <div style="flex:1;">${g}</div>
                <span class="tag tag-info">${n}</span>
            </div>`;
        }).join('') + `<div class="btn-row" style="padding:0.25rem 0.5rem;">
            <button class="btn btn-sm" onclick="ScanPanel._filterByGroup(null)">Show all</button>
        </div>`;
    },

    _filterByGroup(group) {
        const el = document.getElementById('scan-list');
        if (!el) return;
        if (!group) {
            this._renderScans();
            return;
        }
        const filtered = this.scans.filter(s => s.muscle_group === group);
        if (filtered.length === 0) {
            el.innerHTML = `<div class="empty-state">No scans for ${group}</div>`;
            return;
        }
        const orig = this.scans;
        this.scans = filtered;
        this._renderScans();
        this.scans = orig;
    },

    // --- Selection ---
    selectScan(scanId) {
        const scan = this.scans.find(s => s.id === scanId);
        if (!scan) return;
        this.selectedScan = scan;
        this._renderScans();

        // Show scan details in muscle groups panel
        this._showScanDetails(scan);

        // If there's an associated GLB, load it in the viewport
        if (scan.glb_path || scan.mesh_id) {
            const meshId = scan.mesh_id;
            if (meshId) {
                this.loadMeshById(meshId);
            }
        }
        Studio.log(`Scan selected: ${scan.muscle_group || '#' + scan.id}`);
    },

    _showScanDetails(scan) {
        const el = document.getElementById('muscle-groups');
        if (!el) return;
        const fields = [
            { label: 'Muscle Group', value: scan.muscle_group || '—' },
            { label: 'Volume',       value: scan.volume_cm3 != null ? `${scan.volume_cm3.toFixed(1)} cm³` : '—' },
            { label: 'Circumference', value: scan.circumference_cm != null ? `${scan.circumference_cm.toFixed(1)} cm` : '—' },
            { label: 'Definition',   value: scan.definition_score != null ? scan.definition_score.toFixed(2) : '—' },
            { label: 'Growth',       value: scan.growth_pct != null ? `+${scan.growth_pct.toFixed(1)}%` : '—' },
            { label: 'Date',         value: scan.created_on ? new Date(scan.created_on).toLocaleString() : '—' },
        ];
        el.innerHTML = `
            <div style="padding:0.25rem 0 0.5rem;font-weight:600;font-size:0.8125rem;">Scan #${scan.id}</div>
            ${fields.map(f => `<div style="display:flex;justify-content:space-between;padding:0.2rem 0;font-size:0.8125rem;">
                <span style="color:var(--text-secondary);">${f.label}</span>
                <span>${f.value}</span>
            </div>`).join('')}
            <div class="btn-row" style="margin-top:0.5rem;">
                <button class="btn btn-sm" onclick="ScanPanel.loadMuscleGroups()">Back to Groups</button>
            </div>
        `;
    },

    // Load mesh by ID into viewport
    loadMeshById(meshId) {
        const url = `${Studio.API_BASE}/api/mesh/${meshId}.glb`;
        Studio.showInViewport('glb', url);
        Studio.log(`Loading mesh #${meshId}`);
    },

    // --- Upload: 2-image scan ---
    _startUpload() {
        const customerId = Studio.customerId;
        if (!customerId) { Studio.log('No customer selected', 'error'); return; }

        // Chain: pick front → pick side → upload
        this._inputFront.onchange = () => {
            const front = this._inputFront.files[0];
            if (!front) return;
            this._inputSide.onchange = () => {
                const side = this._inputSide.files[0];
                if (!side) return;
                this.uploadScan(customerId, front, side);
            };
            this._inputSide.click();
        };
        this._inputFront.value = '';
        this._inputFront.click();
    },

    async uploadScan(customerId, frontFile, sideFile) {
        Studio.log('Uploading scan (front + side)...');
        const btn = document.getElementById('btn-upload-scan');
        if (btn) { btn.disabled = true; btn.textContent = 'Uploading...'; }

        const fd = new FormData();
        fd.append('front', frontFile);
        fd.append('side', sideFile);

        try {
            const url = `${Studio.API_BASE}/api/upload_scan/${customerId}`;
            const resp = await fetch(url, { method: 'POST', body: fd });
            const data = await resp.json();
            if (resp.ok) {
                Studio.log('Scan uploaded — reloading...');
                await this.loadScans(customerId);
                await this.loadMeshes(customerId);
            } else {
                Studio.log(`Upload failed: ${data.error || resp.status}`, 'error');
            }
        } catch (e) {
            Studio.log(`Upload error: ${e.message}`, 'error');
        } finally {
            if (btn) { btn.disabled = false; btn.textContent = 'Upload Scan'; }
        }
    },

    // --- Upload: quad scan ---
    _startQuadUpload() {
        const customerId = Studio.customerId;
        if (!customerId) { Studio.log('No customer selected', 'error'); return; }

        this._inputQuad.onchange = () => {
            const files = Array.from(this._inputQuad.files);
            if (files.length < 4) {
                Studio.log('Quad scan requires exactly 4 images', 'error');
                return;
            }
            this.uploadQuadScan(customerId, files[0], files[1], files[2], files[3]);
        };
        this._inputQuad.value = '';
        this._inputQuad.multiple = true;
        this._inputQuad.click();
    },

    async uploadQuadScan(customerId, frontFile, backFile, leftFile, rightFile) {
        Studio.log('Uploading quad scan...');
        const btn = document.getElementById('btn-upload-quad');
        if (btn) { btn.disabled = true; btn.textContent = 'Uploading...'; }

        const fd = new FormData();
        fd.append('front', frontFile);
        fd.append('back',  backFile);
        fd.append('left',  leftFile);
        fd.append('right', rightFile);

        try {
            const url = `${Studio.API_BASE}/api/upload_quad_scan/${customerId}`;
            const resp = await fetch(url, { method: 'POST', body: fd });
            const data = await resp.json();
            if (resp.ok) {
                Studio.log('Quad scan uploaded — reloading...');
                await this.loadScans(customerId);
                await this.loadMeshes(customerId);
            } else {
                Studio.log(`Quad upload failed: ${data.error || resp.status}`, 'error');
            }
        } catch (e) {
            Studio.log(`Quad upload error: ${e.message}`, 'error');
        } finally {
            if (btn) { btn.disabled = false; btn.textContent = 'Quad Scan'; }
        }
    },
};

document.addEventListener('DOMContentLoaded', () => ScanPanel.init());
