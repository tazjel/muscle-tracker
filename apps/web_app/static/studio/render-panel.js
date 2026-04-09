/* GTD3D Studio — Render Panel
 * Right sidebar: local render controls + HD RunPod request.
 */
const RenderPanel = {
    localRendered: false,
    hdRequested: false,

    init() {
        this._bind();
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
                if (typeof Studio !== 'undefined') Studio.log('Local render complete');
            });
        }

        if (btnHD) {
            btnHD.addEventListener('click', () => {
                if (this.hdRequested) return;
                this.hdRequested = true;
                btnHD.textContent = 'Requested \u2713';
                btnHD.disabled = true;
                btnHD.style.opacity = '0.6';
                if (typeof Studio !== 'undefined') Studio.log('HD render requested — see Progress tab');
                document.dispatchEvent(new CustomEvent('hd-requested'));
                // Switch to progress tab
                if (typeof Studio !== 'undefined') Studio._activateNav('progress');
            });
        }
    },
};

document.addEventListener('DOMContentLoaded', () => RenderPanel.init());
