/* GTD3D Studio — Viewport
 * Center column: Three.js 3D viewer.
 * Listens for 'viewport-load' (glb url, reset, wireframe) and 'customer-selected'.
 * THREE, OrbitControls, GLTFLoader are loaded as globals via script tags.
 */
const Viewport = {
    scene: null,
    camera: null,
    renderer: null,
    controls: null,
    currentMesh: null,
    wireframeMode: false,
    _animId: null,
    _resizeObserver: null,

    init() {
        this._setupScene();
        this._animate();
        document.addEventListener('viewport-load',      (e) => this.handleLoad(e.detail));
        document.addEventListener('customer-selected',  (e) => this.loadLatestMesh(e.detail.id));
    },

    // --- Scene setup ---
    _setupScene() {
        const container = document.getElementById('viewport-container');
        if (!container) return;

        const w = container.clientWidth  || 800;
        const h = container.clientHeight || 600;

        // Scene
        this.scene = new THREE.Scene();
        this.scene.background = new THREE.Color(0x0f1117);  // --bg-primary

        // Camera
        this.camera = new THREE.PerspectiveCamera(45, w / h, 0.01, 1000);
        this.camera.position.set(0, 1.5, 3.5);

        // Renderer
        this.renderer = new THREE.WebGLRenderer({ antialias: true, alpha: false });
        this.renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
        this.renderer.setSize(w, h);
        this.renderer.shadowMap.enabled = true;
        this.renderer.shadowMap.type = THREE.PCFSoftShadowMap;
        container.appendChild(this.renderer.domElement);

        // Controls
        this.controls = new THREE.OrbitControls(this.camera, this.renderer.domElement);
        this.controls.enableDamping = true;
        this.controls.dampingFactor = 0.08;
        this.controls.minDistance = 0.5;
        this.controls.maxDistance = 20;
        this.controls.target.set(0, 1, 0);
        this.controls.update();

        // Lights
        const ambient = new THREE.AmbientLight(0xffffff, 0.6);
        this.scene.add(ambient);

        const key = new THREE.DirectionalLight(0xffffff, 1.0);
        key.position.set(3, 6, 4);
        key.castShadow = true;
        key.shadow.mapSize.set(1024, 1024);
        this.scene.add(key);

        const fill = new THREE.DirectionalLight(0x8899ff, 0.3);
        fill.position.set(-4, 2, -2);
        this.scene.add(fill);

        // Grid floor
        const grid = new THREE.GridHelper(4, 20, 0x2e3140, 0x2e3140);
        grid.position.y = 0;
        this.scene.add(grid);

        // Resize handling via ResizeObserver (more reliable than window resize for panels)
        this._resizeObserver = new ResizeObserver(() => this._onResize());
        this._resizeObserver.observe(container);
        window.addEventListener('resize', () => this._onResize());
    },

    _animate() {
        this._animId = requestAnimationFrame(() => this._animate());
        if (this.controls) this.controls.update();
        if (this.renderer && this.scene && this.camera) {
            this.renderer.render(this.scene, this.camera);
        }
    },

    _onResize() {
        const container = document.getElementById('viewport-container');
        if (!container || !this.renderer) return;
        const w = container.clientWidth;
        const h = container.clientHeight;
        if (w === 0 || h === 0) return;
        this.camera.aspect = w / h;
        this.camera.updateProjectionMatrix();
        this.renderer.setSize(w, h);
    },

    // --- GLB loading ---
    async loadGLB(url) {
        if (!this.scene) { Studio.log('Viewport not ready', 'error'); return; }
        Studio.log(`Loading GLB: ${url}`);

        // Remove previous mesh
        if (this.currentMesh) {
            this.scene.remove(this.currentMesh);
            this._disposeMesh(this.currentMesh);
            this.currentMesh = null;
        }

        const loader = new THREE.GLTFLoader();
        loader.load(
            url,
            (gltf) => {
                const model = gltf.scene;

                // Center model at origin
                const box = new THREE.Box3().setFromObject(model);
                const center = box.getCenter(new THREE.Vector3());
                const size   = box.getSize(new THREE.Vector3());
                model.position.sub(center);

                // Lift to sit on Y=0 plane
                model.position.y += size.y / 2;

                // Scale to fit ~2 units tall in view
                const maxDim = Math.max(size.x, size.y, size.z);
                if (maxDim > 0) {
                    const targetHeight = 2.0;
                    model.scale.setScalar(targetHeight / maxDim);
                }

                // Apply wireframe mode if active
                if (this.wireframeMode) this._applyWireframe(model, true);

                this.scene.add(model);
                this.currentMesh = model;

                // Reposition camera
                const scaledH = 2.0;
                this.camera.position.set(0, scaledH * 0.7, scaledH * 1.8);
                this.controls.target.set(0, scaledH * 0.5, 0);
                this.controls.update();

                // Gather mesh stats
                let vertCount = 0, faceCount = 0;
                model.traverse(child => {
                    if (child.isMesh && child.geometry) {
                        const pos = child.geometry.attributes.position;
                        if (pos) vertCount += pos.count;
                        const idx = child.geometry.index;
                        faceCount += idx ? idx.count / 3 : (pos ? pos.count / 3 : 0);
                    }
                });

                this._showInfo(`${vertCount.toLocaleString()} verts · ${Math.round(faceCount).toLocaleString()} faces`);
                this._showTools(true);
                this._showEmpty(false);
                Studio.log(`Mesh loaded — ${vertCount.toLocaleString()} vertices`);
            },
            (progress) => {
                if (progress.total > 0) {
                    const pct = Math.round((progress.loaded / progress.total) * 100);
                    Studio.log(`Loading... ${pct}%`);
                }
            },
            (err) => {
                Studio.log(`GLB load error: ${err.message || err}`, 'error');
            }
        );
    },

    // Free GPU memory
    _disposeMesh(object) {
        object.traverse(child => {
            if (child.isMesh) {
                if (child.geometry) child.geometry.dispose();
                if (child.material) {
                    const mats = Array.isArray(child.material) ? child.material : [child.material];
                    mats.forEach(m => {
                        if (m.map)         m.map.dispose();
                        if (m.normalMap)   m.normalMap.dispose();
                        if (m.roughnessMap) m.roughnessMap.dispose();
                        m.dispose();
                    });
                }
            }
        });
    },

    // --- Latest mesh for customer ---
    async loadLatestMesh(customerId) {
        const { ok, data } = await Studio.apiGet(`/api/customer/${customerId}/meshes`);
        if (!ok) return;
        const meshes = data.meshes || data || [];
        if (meshes.length === 0) return;
        const first = meshes[0];
        const meshId = first.id;
        if (!meshId) return;
        const url = `${Studio.API_BASE}/api/mesh/${meshId}.glb`;
        this.loadGLB(url);
    },

    // --- Event handler ---
    handleLoad(detail) {
        if (!detail) return;
        switch (detail.type) {
            case 'glb':
                if (detail.url) this.loadGLB(detail.url);
                break;
            case 'reset':
                this._resetCamera();
                break;
            case 'wireframe':
                this._toggleWireframe();
                break;
            case 'measure':
                Studio.log('Measure tool: coming in Wave 3');
                break;
            default:
                Studio.log(`Viewport: unknown event type "${detail.type}"`);
        }
    },

    // --- Camera reset ---
    _resetCamera() {
        if (!this.camera || !this.controls) return;
        this.camera.position.set(0, 1.5, 3.5);
        this.controls.target.set(0, 1, 0);
        this.controls.update();
        Studio.log('Viewport reset');
    },

    // --- Wireframe toggle ---
    _toggleWireframe() {
        this.wireframeMode = !this.wireframeMode;
        if (this.currentMesh) {
            this._applyWireframe(this.currentMesh, this.wireframeMode);
        }
        const btn = document.querySelector('#viewport-tools .btn:nth-child(2)');
        if (btn) {
            btn.style.color = this.wireframeMode ? 'var(--accent)' : '';
        }
        Studio.log(`Wireframe: ${this.wireframeMode ? 'on' : 'off'}`);
    },

    _applyWireframe(object, on) {
        object.traverse(child => {
            if (child.isMesh && child.material) {
                const mats = Array.isArray(child.material) ? child.material : [child.material];
                mats.forEach(m => { m.wireframe = on; });
            }
        });
    },

    // --- UI helpers ---
    _showInfo(text) {
        const el = document.getElementById('viewport-info');
        if (!el) return;
        el.textContent = text;
        el.style.display = text ? '' : 'none';
    },

    _showTools(visible) {
        const el = document.getElementById('viewport-tools');
        if (el) el.style.display = visible ? '' : 'none';
    },

    _showEmpty(visible) {
        const el = document.getElementById('viewport-empty');
        if (el) el.style.display = visible ? '' : 'none';
    },
};

document.addEventListener('DOMContentLoaded', () => Viewport.init());
