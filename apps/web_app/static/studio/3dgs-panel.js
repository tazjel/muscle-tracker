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
        // Listen for SSE mesh_ready events
        document.addEventListener('mesh_ready', (e) => {
            if (this.job && this.job.status === 'processing') {
                Studio.log('3DGS: mesh ready notification received');
            }
        });
    },

    _renderModeBanner() {
        const el = document.getElementById('3dgs-mode-banner');
        if (!el) return;
        if (Studio.MOCK_MODE) {
            el.innerHTML = '<div style="padding:8px;background:rgba(239,68,68,0.1);border:1px solid rgba(239,68,68,0.3);border-radius:4px;font-size:11px;color:#ef4444;margin-bottom:8px;">Enable Live mode to use 3DGS training</div>';
        } else {
            el.innerHTML = '';
        }
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
        if (btn) btn.addEventListener('click', () => this.startTraining());
    },

    async startTraining() {
        if (!this.videoFile) return;
        if (!Studio.customerId) {
            Studio.log('3DGS: select a customer first', 'error');
            return;
        }

        this.job = {
            id: null,
            status: 'uploading',
            startedAt: new Date().toLocaleTimeString(),
            elapsed: 0,
            cost: 0.00,
            videoName: this.videoFile.name,
            gaussians: 0,
        };
        this._renderStatus();
        Studio.log('3DGS: uploading video...');

        const formData = new FormData();
        formData.append('video', this.videoFile);
        formData.append('source', '3dgs_studio');

        try {
            const xhr = new XMLHttpRequest();
            const uploadPromise = new Promise((resolve, reject) => {
                xhr.upload.onprogress = (e) => {
                    if (e.lengthComputable) {
                        const pct = Math.round((e.loaded / e.total) * 100);
                        this.job.status = `uploading (${pct}%)`;
                        this._renderStatus();
                    }
                };
                xhr.onload = () => {
                    if (xhr.status >= 200 && xhr.status < 300) {
                        resolve(JSON.parse(xhr.responseText));
                    } else {
                        reject(new Error(`Upload failed: ${xhr.status}`));
                    }
                };
                xhr.onerror = () => reject(new Error('Upload network error'));
                xhr.open('POST', `${Studio.API_BASE}/api/customer/${Studio.customerId}/upload_video_scan`);
                if (Studio._token) xhr.setRequestHeader('Authorization', `Bearer ${Studio._token}`);
                xhr.send(formData);
            });

            const result = await uploadPromise;
            if (result.session_id) {
                this.job.id = result.session_id;
                this.job.status = 'processing';
                this._renderStatus();
                Studio.log(`3DGS: video uploaded, session ${this.job.id}`);
                this._pollStatus();
            } else {
                this.job.status = 'error';
                this._renderStatus();
                Studio.log(`3DGS: upload failed — ${result.message || 'unknown'}`, 'error');
            }
        } catch (e) {
            this.job.status = 'error';
            this._renderStatus();
            Studio.log(`3DGS: ${e.message}`, 'error');
        }
    },

    _pollTimer: null,

    _pollStatus() {
        if (!this.job || !this.job.id) return;
        this._pollTimer = setInterval(async () => {
            try {
                const { ok, data } = await Studio.apiGet(`/api/customer/${Studio.customerId}/video_scan/${this.job.id}`);
                if (!ok) return;
                const status = data.status || data.session?.status;
                if (status) {
                    this.job.status = status;
                    if (data.gaussians) this.job.gaussians = data.gaussians;
                    if (data.cost) this.job.cost = data.cost;
                    this._renderStatus();
                }
                if (['complete', 'error', 'failed'].includes(status)) {
                    clearInterval(this._pollTimer);
                    this._pollTimer = null;
                    if (status === 'complete') {
                        Studio.log(`3DGS: training complete — ${this.job.gaussians.toLocaleString()} Gaussians`);
                    }
                }
            } catch (e) {
                Studio.log(`3DGS poll error: ${e.message}`, 'warn');
            }
        }, 3000);
    },

    _renderStatus() {
        const el = document.getElementById('3dgs-job-status');
        if (!el) return;

        if (!this.job) {
            el.innerHTML = '<div style="color:var(--text-dim);font-size:13px;">No training job started.</div>';
            return;
        }

        const statusColors = { uploading: '#eab308', training: '#3b82f6', processing: '#3b82f6', complete: '#22c55e', error: '#ef4444', failed: '#ef4444' };
        const color = statusColors[this.job.status] || '#6b7280';
        const label = this.job.status.charAt(0).toUpperCase() + this.job.status.slice(1);

        const row = (k, v) => `<div style="display:flex;justify-content:space-between;padding:4px 0;border-bottom:1px solid rgba(255,255,255,0.05);font-size:12px;">
            <span style="color:var(--text-dim);">${k}</span><span>${v}</span></div>`;

        el.innerHTML = `
            ${row('Status', `<span style="color:${color};font-weight:600;">${label}</span>`)}
            ${this.job.id ? row('Job ID', String(this.job.id).substring(0, 16)) : ''}
            ${row('Video', this.job.videoName)}
            ${row('Time', this.job.elapsed + 's')}
            ${row('Cost', '$' + this.job.cost.toFixed(2))}
            ${this.job.gaussians ? row('Gaussians', this.job.gaussians.toLocaleString()) : ''}
            ${row('Started', this.job.startedAt)}
            ${this.job.status === 'processing' || this.job.status === 'training' ? '<div style="margin-top:8px;"><div style="height:4px;background:rgba(255,255,255,0.1);border-radius:2px;overflow:hidden;"><div style="height:100%;width:55%;background:#3b82f6;border-radius:2px;"></div></div></div>' : ''}
            ${this.job.status === 'complete' ? '<div style="margin-top:8px;padding:6px;background:rgba(34,197,94,0.1);border:1px solid rgba(34,197,94,0.2);border-radius:4px;font-size:11px;color:#22c55e;">Training complete. Gaussians ready.</div>' : ''}
        `;
    },
};

document.addEventListener('DOMContentLoaded', () => GaussianPanel.init());
