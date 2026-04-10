/* GTD3D Studio — 3D Gaussian Splatting Panel
 * Left sidebar: video upload + train controls.
 * Right sidebar: training job status.
 * Viewport: point cloud viewer for trained Gaussians.
 */
const GaussianPanel = {
    job: null,
    videoFile: null,

    init() {
        this._setupDropzone();
        this._setupButtons();
        this._renderModeBanner();
    },

    _renderModeBanner() {
        const el = document.getElementById('3dgs-mode-banner');
        if (!el) return;
        el.innerHTML = '<div style="padding:8px;background:rgba(239,68,68,0.1);border:1px solid rgba(239,68,68,0.3);border-radius:4px;font-size:11px;color:#ef4444;margin-bottom:8px;">Requires backend — enable Live mode and start py4web</div>';
    },

    _setupDropzone() {
        const dz = document.getElementById('3dgs-dropzone');
        if (!dz) return;

        const fileInput = document.createElement('input');
        fileInput.type = 'file';
        fileInput.accept = 'video/*';
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
        if (!file.type.startsWith('video/')) {
            if (typeof Studio !== 'undefined') Studio.log('3DGS: not a video file', 'error');
            return;
        }
        this.videoFile = file;
        const info = document.getElementById('3dgs-file-info');
        if (info) info.textContent = `${file.name} (${(file.size / 1024 / 1024).toFixed(1)} MB)`;
        const btn = document.getElementById('btn-train-splat');
        if (btn) btn.disabled = false;
        if (typeof Studio !== 'undefined') Studio.log(`3DGS: selected ${file.name}`);
    },

    _setupButtons() {
        const btn = document.getElementById('btn-train-splat');
        if (btn) btn.addEventListener('click', () => this.startMockTraining());
    },

    startMockTraining() {
        if (!this.videoFile) return;
        this.job = {
            id: '3dgs-' + Date.now(),
            status: 'uploading',
            startedAt: new Date().toLocaleTimeString(),
            elapsed: 0,
            cost: 0.00,
            videoName: this.videoFile.name,
            gaussians: 0,
        };
        this._renderStatus();
        if (typeof Studio !== 'undefined') Studio.log('3DGS: uploading video...');

        setTimeout(() => {
            if (!this.job) return;
            this.job.status = 'training';
            this.job.cost = 0.08;
            this.job.elapsed = 15;
            this._renderStatus();
            if (typeof Studio !== 'undefined') Studio.log('3DGS: training started on RunPod');
        }, 2000);

        setTimeout(() => {
            if (!this.job) return;
            this.job.status = 'complete';
            this.job.cost = 0.45;
            this.job.elapsed = 120;
            this.job.gaussians = 160000;
            this._renderStatus();
            if (typeof Studio !== 'undefined') Studio.log('3DGS: training complete — 160K Gaussians, $0.45');
        }, 8000);
    },

    _renderStatus() {
        const el = document.getElementById('3dgs-job-status');
        if (!el) return;

        if (!this.job) {
            el.innerHTML = '<div style="color:var(--text-dim);font-size:13px;">No training job started.</div>';
            return;
        }

        const statusColors = { uploading: '#eab308', training: '#3b82f6', complete: '#22c55e', error: '#ef4444' };
        const color = statusColors[this.job.status] || '#6b7280';
        const label = this.job.status.charAt(0).toUpperCase() + this.job.status.slice(1);

        const row = (k, v) => `<div style="display:flex;justify-content:space-between;padding:4px 0;border-bottom:1px solid rgba(255,255,255,0.05);font-size:12px;">
            <span style="color:var(--text-dim);">${k}</span><span>${v}</span></div>`;

        el.innerHTML = `
            ${row('Status', `<span style="color:${color};font-weight:600;">${label}</span>`)}
            ${row('Job ID', this.job.id.substring(0, 16))}
            ${row('Video', this.job.videoName)}
            ${row('Time', this.job.elapsed + 's')}
            ${row('Cost', '$' + this.job.cost.toFixed(2))}
            ${this.job.gaussians ? row('Gaussians', this.job.gaussians.toLocaleString()) : ''}
            ${row('Started', this.job.startedAt)}
            ${this.job.status === 'training' ? '<div style="margin-top:8px;"><div style="height:4px;background:rgba(255,255,255,0.1);border-radius:2px;overflow:hidden;"><div style="height:100%;width:55%;background:#3b82f6;border-radius:2px;"></div></div></div>' : ''}
            ${this.job.status === 'complete' ? '<div style="margin-top:8px;padding:6px;background:rgba(34,197,94,0.1);border:1px solid rgba(34,197,94,0.2);border-radius:4px;font-size:11px;color:#22c55e;">Training complete. 160K Gaussians ready.</div>' : ''}
        `;
    },
};

document.addEventListener('DOMContentLoaded', () => GaussianPanel.init());
