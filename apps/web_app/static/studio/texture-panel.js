/* GTD3D Studio — Texture Panel
 * Right sidebar: skin texture capture, PBR generation, room textures, HDRI environments.
 */
const TexturePanel = {
    regions: ['face', 'torso', 'arms', 'legs', 'hands', 'feet'],
    capturedRegions: [],

    init() {
        document.addEventListener('customer-selected', (e) => this.loadRegions(e.detail.id));
    },

    async loadRegions(customerId) {
        const el = document.getElementById('texture-status');
        if (!el) return;
        el.innerHTML = '<div class="spinner"></div>';
        const { ok, data } = await Studio.apiGet(`/api/customer/${customerId}/skin_regions`);
        if (!ok) {
            el.innerHTML = '<div class="empty-state" style="color:var(--error);">Failed to load regions</div>';
            return;
        }
        this.capturedRegions = data.captured || data || [];
        this._renderRegionGrid(this.capturedRegions, customerId);
    },

    _renderRegionGrid(captured, customerId) {
        const el = document.getElementById('texture-status');
        if (!el) return;
        const capturedSet = new Set(Array.isArray(captured) ? captured.map(r => r.region || r) : []);
        const cards = this.regions.map(region => {
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
            <div style="display:grid;grid-template-columns:1fr 1fr;gap:0.5rem;margin-bottom:0.75rem;">
                ${cards.join('')}
            </div>
            <div class="btn-row">
                <button class="btn btn-accent btn-sm" onclick="TexturePanel.viewPBR(${customerId})">View PBR Maps</button>
                <button class="btn btn-sm" onclick="TexturePanel.loadRoomTextures(${customerId})">Room Textures</button>
                <button class="btn btn-sm" onclick="TexturePanel.browseEnvironments()">Environments</button>
            </div>
        `;
    },

    async uploadSkinTexture(customerId, region) {
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
                this.loadRegions(customerId);
            } else {
                Studio.log(`Upload failed: ${data?.error || 'Unknown error'}`, 'error');
            }
        };
        input.click();
    },

    async viewPBR(customerId) {
        const el = document.getElementById('texture-status');
        if (!el) return;
        el.innerHTML = '<div class="spinner"></div>';
        const { ok, data } = await Studio.apiGet(`/api/customer/${customerId}/pbr_textures`);
        if (!ok) {
            el.innerHTML = '<div class="empty-state" style="color:var(--error);">Failed to load PBR status</div>';
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
                <button class="btn btn-sm" onclick="TexturePanel.loadRegions(${customerId})">&#8592; Back</button>
            </div>
            ${generated}
            <div style="display:grid;grid-template-columns:1fr 1fr;gap:0.5rem;">
                ${cards.join('')}
            </div>
        `;
    },

    async loadRoomTextures(customerId) {
        const el = document.getElementById('texture-status');
        if (!el) return;
        el.innerHTML = '<div class="spinner"></div>';
        const { ok, data } = await Studio.apiGet(`/api/customer/${customerId}/room_textures`);
        if (!ok) {
            el.innerHTML = '<div class="empty-state" style="color:var(--error);">Failed to load room textures</div>';
            return;
        }
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
                <button class="btn btn-sm" onclick="TexturePanel.loadRegions(${customerId})">&#8592; Back</button>
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

    async browseEnvironments() {
        const el = document.getElementById('texture-status');
        if (!el) return;
        el.innerHTML = '<div class="spinner"></div>';
        const { ok, data } = await Studio.apiGet('/api/room_assets/hdri');
        if (!ok) {
            el.innerHTML = '<div class="empty-state" style="color:var(--error);">Failed to load environments</div>';
            return;
        }
        const envs = data.environments || data || [];
        const backBtn = Studio.customerId
            ? `<button class="btn btn-sm" onclick="TexturePanel.loadRegions(${Studio.customerId})">&#8592; Back</button>`
            : '';

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
