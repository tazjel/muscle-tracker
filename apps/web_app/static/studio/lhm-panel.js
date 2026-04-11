/* GTD3D Studio — LHM Panel
 * Left sidebar: single photo upload for LHM++ avatar generation.
 * Right sidebar: generation job status + stats.
 *
 * API:
 *   POST  {Studio.API_BASE}/api/lhm/submit   → {status:'submitted', job_id}
 *   GET   {Studio.API_BASE}/api/lhm/status/<job_id> → {status, result_url?, error?}
 */
const LHMPanel = {
    job: null,
    photoFile: null,
    _pollTimer: null,
    _pollInterval: 5000,  // ms between status polls

    init() {
        this._setupDropzone();
        this._setupButtons();
        this._renderModeBanner();
    },

    _renderModeBanner() {
        const el = document.getElementById('lhm-mode-banner');
        if (!el) return;
        const isLive = typeof Studio !== 'undefined' && Studio.liveMode;
        if (!isLive) {
            el.innerHTML = '<div style="padding:8px;background:rgba(239,68,68,0.1);border:1px solid rgba(239,68,68,0.3);border-radius:4px;font-size:11px;color:#ef4444;margin-bottom:8px;">Requires backend — enable Live mode and start py4web</div>';
        } else {
            el.innerHTML = '';
        }
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
        if (btn) btn.addEventListener('click', () => this.startGeneration());
    },

    // ── Real API submission ──────────────────────────────────────────────────

    startGeneration() {
        if (!this.photoFile) return;

        const isLive = typeof Studio !== 'undefined' && Studio.liveMode;
        if (!isLive) {
            if (typeof Studio !== 'undefined') Studio.log('LHM: Live mode required', 'error');
            this._renderModeBanner();
            return;
        }

        this._cancelPoll();

        this.job = {
            id: null,
            status: 'submitting',
            startedAt: new Date().toLocaleTimeString(),
            elapsed: 0,
            photoName: this.photoFile.name,
            vertex_count: 0,
            face_count: 0,
        };
        this._renderStatus();
        if (typeof Studio !== 'undefined') Studio.log('LHM: submitting to RunPod…');

        const btn = document.getElementById('btn-generate-avatar');
        if (btn) { btn.disabled = true; btn.textContent = 'Submitting…'; }

        const formData = new FormData();
        formData.append('photo', this.photoFile);

        const token = typeof Studio !== 'undefined' ? Studio.token : '';
        const apiBase = typeof Studio !== 'undefined' ? Studio.API_BASE : '';

        fetch(`${apiBase}/api/lhm/submit`, {
            method: 'POST',
            headers: token ? { 'Authorization': `Bearer ${token}` } : {},
            body: formData,
        })
        .then(r => r.json())
        .then(data => {
            if (data.status === 'submitted' && data.job_id) {
                this.job.id = data.job_id;
                this.job.status = 'processing';
                this._renderStatus();
                if (typeof Studio !== 'undefined') Studio.log(`LHM: job ${data.job_id} submitted — polling…`);
                this._startPoll(data.job_id, apiBase, token);
            } else {
                this._onError(data.message || 'Submit failed');
            }
        })
        .catch(err => {
            this._onError('Network error: ' + err.message);
        });
    },

    _startPoll(jobId, apiBase, token) {
        this._cancelPoll();
        const poll = () => {
            fetch(`${apiBase}/api/lhm/status/${jobId}`, {
                headers: token ? { 'Authorization': `Bearer ${token}` } : {},
            })
            .then(r => r.json())
            .then(data => {
                if (!this.job || this.job.id !== jobId) return;  // stale
                this.job.elapsed = data.elapsed || 0;
                this.job.status = data.status;

                if (data.status === 'completed') {
                    this.job.vertex_count = data.vertex_count || 0;
                    this.job.face_count = data.face_count || 0;
                    this._renderStatus();
                    this._onComplete(data.result_url);
                } else if (data.status === 'failed') {
                    this._onError(data.error || 'Job failed on RunPod');
                } else {
                    // pending / processing — keep polling
                    this._renderStatus();
                    this._pollTimer = setTimeout(poll, this._pollInterval);
                }
            })
            .catch(err => {
                if (typeof Studio !== 'undefined') Studio.log(`LHM: poll error — ${err.message}`, 'warn');
                // Retry on transient network errors
                this._pollTimer = setTimeout(poll, this._pollInterval * 2);
            });
        };
        this._pollTimer = setTimeout(poll, this._pollInterval);
    },

    _cancelPoll() {
        if (this._pollTimer) {
            clearTimeout(this._pollTimer);
            this._pollTimer = null;
        }
    },

    _onComplete(meshUrl) {
        if (typeof Studio !== 'undefined') {
            Studio.log(`LHM: avatar ready — loading in viewport`);
            if (typeof Studio.showInViewport === 'function') {
                Studio.showInViewport(meshUrl);
            }
        }
        const btn = document.getElementById('btn-generate-avatar');
        if (btn) { btn.disabled = false; btn.textContent = 'Generate Avatar'; }
        this._renderStatus();
    },

    _onError(msg) {
        if (this.job) this.job.status = 'error';
        this._cancelPoll();
        if (typeof Studio !== 'undefined') Studio.log(`LHM: error — ${msg}`, 'error');
        const btn = document.getElementById('btn-generate-avatar');
        if (btn) { btn.disabled = false; btn.textContent = 'Generate Avatar'; }
        this._renderStatus(msg);
    },

    // ── Status panel ─────────────────────────────────────────────────────────

    _renderStatus(errorMsg) {
        const el = document.getElementById('lhm-job-status');
        if (!el) return;

        if (!this.job) {
            el.innerHTML = '<div style="color:var(--text-dim);font-size:13px;">No avatar generation started.</div>';
            return;
        }

        const statusColors = {
            submitting: '#f59e0b',
            processing: '#3b82f6',
            completed:  '#22c55e',
            complete:   '#22c55e',
            error:      '#ef4444',
            failed:     '#ef4444',
        };
        const color = statusColors[this.job.status] || '#6b7280';
        const label = {
            submitting: 'Submitting',
            processing: 'Processing',
            completed:  'Complete',
            complete:   'Complete',
            error:      'Error',
            failed:     'Failed',
        }[this.job.status] || this.job.status;

        const row = (k, v) => `<div style="display:flex;justify-content:space-between;padding:4px 0;border-bottom:1px solid rgba(255,255,255,0.05);font-size:12px;">
            <span style="color:var(--text-dim);">${k}</span><span>${v}</span></div>`;

        const isProcessing = this.job.status === 'processing' || this.job.status === 'submitting';
        const isDone       = this.job.status === 'completed' || this.job.status === 'complete';
        const isError      = this.job.status === 'error'     || this.job.status === 'failed';

        el.innerHTML = `
            ${row('Status', `<span style="color:${color};font-weight:600;">${label}</span>`)}
            ${this.job.id  ? row('Job ID', this.job.id.substring(0, 16)) : ''}
            ${row('Photo', this.job.photoName)}
            ${row('Time', (this.job.elapsed || 0) + 's')}
            ${this.job.vertex_count ? row('Gaussians', this.job.vertex_count.toLocaleString()) : ''}
            ${row('Started', this.job.startedAt)}
            ${isProcessing ? `<div style="margin-top:8px;"><div style="height:4px;background:rgba(255,255,255,0.1);border-radius:2px;overflow:hidden;"><div style="height:100%;width:70%;background:${color};border-radius:2px;animation:pulse 1.5s infinite;"></div></div></div>` : ''}
            ${isDone ? '<div style="margin-top:8px;padding:6px;background:rgba(34,197,94,0.1);border:1px solid rgba(34,197,94,0.2);border-radius:4px;font-size:11px;color:#22c55e;">Avatar loaded in viewport.</div>' : ''}
            ${isError ? `<div style="margin-top:8px;padding:6px;background:rgba(239,68,68,0.1);border:1px solid rgba(239,68,68,0.2);border-radius:4px;font-size:11px;color:#ef4444;">${errorMsg || 'Generation failed. Check logs.'}</div>` : ''}
        `;
    },
};

document.addEventListener('DOMContentLoaded', () => LHMPanel.init());
