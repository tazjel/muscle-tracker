/* GTD3D Studio — LHM Panel
 * Left sidebar: single photo upload for LHM++ avatar generation.
 * Right sidebar: generation job status + stats.
 */
const LHMPanel = {
    job: null,
    photoFile: null,

    init() {
        this._setupDropzone();
        this._setupButtons();
    },

    _setupDropzone() {
        const dz = document.getElementById('lhm-dropzone');
        if (!dz) return;

        const fileInput = document.createElement('input');
        fileInput.type = 'file';
        fileInput.accept = 'image/*';
        fileInput.style.display = 'none';
        dz.parentElement.appendChild(fileInput);

        dz.addEventListener('click', () => fileInput.click());
        dz.addEventListener('dragover', (e) => { e.preventDefault(); dz.style.borderColor = '#3b82f6'; });
        dz.addEventListener('dragleave', () => { dz.style.borderColor = 'rgba(255,255,255,0.15)'; });
        dz.addEventListener('drop', (e) => {
            e.preventDefault();
            dz.style.borderColor = 'rgba(255,255,255,0.15)';
            if (e.dataTransfer.files.length) this._selectFile(e.dataTransfer.files[0]);
        });
        fileInput.addEventListener('change', () => {
            if (fileInput.files.length) this._selectFile(fileInput.files[0]);
        });
    },

    _selectFile(file) {
        if (!file.type.startsWith('image/')) {
            if (typeof Studio !== 'undefined') Studio.log('LHM: not an image file', 'error');
            return;
        }
        this.photoFile = file;
        const info = document.getElementById('lhm-file-info');
        if (info) info.textContent = `${file.name} (${(file.size / 1024).toFixed(0)} KB)`;
        const btn = document.getElementById('btn-generate-avatar');
        if (btn) btn.disabled = false;
        if (typeof Studio !== 'undefined') Studio.log(`LHM: selected ${file.name}`);
    },

    _setupButtons() {
        const btn = document.getElementById('btn-generate-avatar');
        if (btn) btn.addEventListener('click', () => this.startMockGeneration());
    },

    startMockGeneration() {
        if (!this.photoFile) return;
        this.job = {
            id: 'lhm-' + Date.now(),
            status: 'processing',
            startedAt: new Date().toLocaleTimeString(),
            elapsed: 0,
            cost: 0.00,
            photoName: this.photoFile.name,
            vertices: 0,
            gaussians: 0,
        };
        this._renderStatus();
        if (typeof Studio !== 'undefined') Studio.log('LHM: generating avatar...');

        setTimeout(() => {
            if (!this.job) return;
            this.job.status = 'complete';
            this.job.cost = 0.03;
            this.job.elapsed = 2;
            this.job.vertices = 12480;
            this.job.gaussians = 160000;
            this._renderStatus();
            if (typeof Studio !== 'undefined') Studio.log('LHM: avatar generated — 160K Gaussians, 2s, $0.03');
        }, 4000);
    },

    _renderStatus() {
        const el = document.getElementById('lhm-job-status');
        if (!el) return;

        if (!this.job) {
            el.innerHTML = '<div style="color:var(--text-dim);font-size:13px;">No avatar generation started.</div>';
            return;
        }

        const statusColors = { processing: '#3b82f6', complete: '#22c55e', error: '#ef4444' };
        const color = statusColors[this.job.status] || '#6b7280';
        const label = this.job.status.charAt(0).toUpperCase() + this.job.status.slice(1);

        const row = (k, v) => `<div style="display:flex;justify-content:space-between;padding:4px 0;border-bottom:1px solid rgba(255,255,255,0.05);font-size:12px;">
            <span style="color:var(--text-dim);">${k}</span><span>${v}</span></div>`;

        el.innerHTML = `
            ${row('Status', `<span style="color:${color};font-weight:600;">${label}</span>`)}
            ${row('Job ID', this.job.id.substring(0, 16))}
            ${row('Photo', this.job.photoName)}
            ${row('Time', this.job.elapsed + 's')}
            ${row('Cost', '$' + this.job.cost.toFixed(2))}
            ${this.job.vertices ? row('Vertices', this.job.vertices.toLocaleString()) : ''}
            ${this.job.gaussians ? row('Gaussians', this.job.gaussians.toLocaleString()) : ''}
            ${row('Started', this.job.startedAt)}
            ${this.job.status === 'processing' ? '<div style="margin-top:8px;"><div style="height:4px;background:rgba(255,255,255,0.1);border-radius:2px;overflow:hidden;"><div style="height:100%;width:70%;background:#3b82f6;border-radius:2px;animation:pulse 1.5s infinite;"></div></div></div>' : ''}
            ${this.job.status === 'complete' ? '<div style="margin-top:8px;padding:6px;background:rgba(34,197,94,0.1);border:1px solid rgba(34,197,94,0.2);border-radius:4px;font-size:11px;color:#22c55e;">Avatar ready. View in viewport.</div>' : ''}
        `;
    },
};

document.addEventListener('DOMContentLoaded', () => LHMPanel.init());
