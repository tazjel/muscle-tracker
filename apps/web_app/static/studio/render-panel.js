/* GTD3D Studio — Render Panel
 * Right sidebar: GPU worker status, render presets, job progress, render history.
 */
const RenderPanel = {
    activeJob: null,
    pollTimer: null,

    init() {
        document.addEventListener('customer-selected', () => this._renderControls());
    },

    _renderControls() {
        const el = document.getElementById('render-controls');
        if (!el || !Studio.customerId) return;
        el.innerHTML = `
            <div class="form-group">
                <label class="form-label">Render Preset</label>
                <select class="form-select" id="render-preset">
                    <option value="cinematic">Cinematic (high quality)</option>
                    <option value="standard">Standard</option>
                    <option value="wireframe">Wireframe</option>
                    <option value="textured">Textured</option>
                </select>
            </div>
            <div class="btn-row">
                <button class="btn btn-accent btn-sm" onclick="RenderPanel.startRender()">Render</button>
                <button class="btn btn-sm" onclick="RenderPanel.checkGPU()">Check GPU</button>
            </div>
            <div id="gpu-status" style="margin-top:0.5rem;"></div>
            <div id="render-progress" style="margin-top:0.5rem;"></div>
            <div id="render-history" style="margin-top:0.75rem;"></div>
        `;
        this.checkGPU();
        this._loadRenderHistory();
    },

    async startRender() {
        if (!Studio.customerId) return;
        const preset = document.getElementById('render-preset')?.value || 'standard';
        const progressEl = document.getElementById('render-progress');
        if (progressEl) {
            progressEl.innerHTML = '<div class="spinner"></div>';
        }

        const { ok, data } = await Studio.apiPost(`/api/customer/${Studio.customerId}/render`, { preset });
        if (ok && data.job_id) {
            this.activeJob = data.job_id;
            Studio.log(`Render started: job ${data.job_id} (${preset})`);
            this._pollProgress();
        } else {
            if (progressEl) {
                progressEl.innerHTML = `<span class="tag tag-err">Failed to start render${data?.error ? ': ' + data.error : ''}</span>`;
            }
            Studio.log(`Render failed: ${data?.error || 'Unknown error'}`, 'error');
        }
    },

    async _pollProgress() {
        if (!this.activeJob || !Studio.customerId) return;
        const { ok, data } = await Studio.apiGet(`/api/customer/${Studio.customerId}/render/${this.activeJob}`);
        const el = document.getElementById('render-progress');
        if (!el) return;

        if (!ok) {
            el.innerHTML = '<span class="tag tag-err">Lost connection to render job</span>';
            this.activeJob = null;
            return;
        }

        if (data.status === 'completed') {
            let html = '<span class="tag tag-ok">Complete</span>';
            if (data.filename) {
                html += `<div style="margin-top:0.5rem;">
                    <img src="/web_app/api/render_image/${this.activeJob}/${data.filename}"
                         style="max-width:100%;border-radius:var(--radius-sm);cursor:pointer;"
                         onclick="Studio.showInViewport('render', '/web_app/api/render_image/${this.activeJob}/${data.filename}')"
                         onerror="this.style.display='none'">
                </div>`;
            }
            el.innerHTML = html;
            this.activeJob = null;
            Studio.log('Render complete');
            this._loadRenderHistory();
            return;
        }

        if (data.status === 'failed' || data.status === 'error') {
            el.innerHTML = `<span class="tag tag-err">Render failed${data.error ? ': ' + data.error : ''}</span>`;
            this.activeJob = null;
            return;
        }

        const pct = Math.min(100, Math.max(0, data.progress || 0));
        const eta = data.eta_seconds
            ? ` — ETA ${Math.ceil(data.eta_seconds)}s`
            : '';
        el.innerHTML = `
            <div style="background:var(--bg-primary);border-radius:var(--radius-sm);overflow:hidden;height:8px;">
                <div style="width:${pct}%;height:100%;background:var(--accent);transition:width 0.3s;"></div>
            </div>
            <span style="font-size:0.75rem;color:var(--text-secondary);">${pct}% — ${data.status || 'processing'}${eta}</span>
        `;

        this.pollTimer = setTimeout(() => this._pollProgress(), 3000);
    },

    async checkGPU() {
        const el = document.getElementById('gpu-status');
        const { ok, data } = await Studio.apiGet('/api/gpu_status');
        if (!ok) {
            if (el) el.innerHTML = '<span class="tag tag-err">GPU status unavailable</span>';
            return;
        }
        const available = data.available ?? false;
        const workers = data.workers || 0;
        const vram = data.vram_gb ? ` — ${data.vram_gb}GB VRAM` : '';
        if (el) {
            el.innerHTML = `<span class="tag ${available ? 'tag-ok' : 'tag-warn'}">
                GPU: ${available ? 'Online' : 'Offline'} — ${workers} worker${workers !== 1 ? 's' : ''}${vram}
            </span>`;
        }
        Studio.log(`GPU: ${available ? 'Available' : 'Offline'} — ${workers} workers`);
    },

    async _loadRenderHistory() {
        if (!Studio.customerId) return;
        const { ok, data } = await Studio.apiGet(`/api/customer/${Studio.customerId}/render`);
        if (!ok || !data.jobs?.length) return;
        const el = document.getElementById('render-history');
        if (!el) return;

        const jobs = (data.jobs || []).slice(0, 6);
        const thumbs = jobs.map(job => {
            const thumb = job.filename
                ? `<img src="/web_app/api/render_image/${job.job_id}/${job.filename}"
                        style="width:100%;border-radius:var(--radius-sm);cursor:pointer;"
                        onclick="Studio.showInViewport('render', '/web_app/api/render_image/${job.job_id}/${job.filename}')"
                        onerror="this.style.display='none'">`
                : `<div style="height:48px;background:var(--bg-primary);border-radius:var(--radius-sm);display:flex;align-items:center;justify-content:center;font-size:0.7rem;color:var(--text-secondary);">${job.status || 'unknown'}</div>`;
            return `<div style="text-align:center;">
                ${thumb}
                <div style="font-size:0.7rem;color:var(--text-secondary);margin-top:0.2rem;text-transform:capitalize;">${job.preset || 'standard'}</div>
            </div>`;
        });

        el.innerHTML = `
            <div style="font-size:0.75rem;font-weight:600;color:var(--text-secondary);margin-bottom:0.4rem;">Recent Renders</div>
            <div style="display:grid;grid-template-columns:1fr 1fr 1fr;gap:0.4rem;">
                ${thumbs.join('')}
            </div>
        `;
    },
};
document.addEventListener('DOMContentLoaded', () => RenderPanel.init());
