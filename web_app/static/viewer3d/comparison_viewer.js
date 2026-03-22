import * as THREE from 'three';
import { OrbitControls } from 'three/addons/controls/OrbitControls.js';
import { GLTFLoader } from 'three/addons/loaders/GLTFLoader.js';

// Parse URL params
const params = new URLSearchParams(window.location.search);
const leftUrl = params.get('left') || '';
const rightUrl = params.get('right') || '';
document.getElementById('left-label').textContent = params.get('label_left') || 'Before';
document.getElementById('right-label').textContent = params.get('label_right') || 'After';

// Status helper
const statusEl = document.getElementById('status');
function setStatus(msg) { statusEl.textContent = msg; }

// Create a viewer for one panel
function createViewer(canvasId, infoId) {
    const canvas = document.getElementById(canvasId);
    const info = document.getElementById(infoId);

    const scene = new THREE.Scene();
    scene.background = new THREE.Color(0x1a1a2e);

    const renderer = new THREE.WebGLRenderer({ canvas, antialias: true });
    renderer.setPixelRatio(window.devicePixelRatio);
    renderer.toneMapping = THREE.ACESFilmicToneMapping;
    renderer.toneMappingExposure = 1.2;

    const camera = new THREE.PerspectiveCamera(45, 1, 0.1, 100);
    camera.position.set(0, 1, 3);

    const controls = new OrbitControls(camera, canvas);
    controls.enableDamping = true;
    controls.dampingFactor = 0.08;
    controls.target.set(0, 0.9, 0);

    // Lighting (clinical white, matches main viewer)
    const ambient = new THREE.AmbientLight(0xffffff, 0.6);
    scene.add(ambient);
    const key = new THREE.DirectionalLight(0xffffff, 1.0);
    key.position.set(2, 3, 2);
    scene.add(key);
    const fill = new THREE.DirectionalLight(0xffffff, 0.4);
    fill.position.set(-2, 1, -1);
    scene.add(fill);

    // Grid floor
    const grid = new THREE.GridHelper(4, 20, 0x333355, 0x222244);
    scene.add(grid);

    let model = null;
    let meshes = [];

    return { scene, renderer, camera, controls, canvas, info, model, meshes };
}

const left = createViewer('left-canvas', 'left-info');
const right = createViewer('right-canvas', 'right-info');

// Resize handler
function resize() {
    [left, right].forEach(v => {
        const rect = v.canvas.parentElement.getBoundingClientRect();
        v.renderer.setSize(rect.width, rect.height);
        v.camera.aspect = rect.width / rect.height;
        v.camera.updateProjectionMatrix();
    });
}
window.addEventListener('resize', resize);
resize();

// Load GLB into viewer
const loader = new GLTFLoader();

function loadModel(viewer, url) {
    if (!url) {
        viewer.info.textContent = 'No model URL';
        return;
    }
    setStatus(`Loading ${url}...`);
    loader.load(url,
        (gltf) => {
            const model = gltf.scene;
            viewer.scene.add(model);
            viewer.model = model;

            // Center and scale
            const box = new THREE.Box3().setFromObject(model);
            const center = box.getCenter(new THREE.Vector3());
            const size = box.getSize(new THREE.Vector3());
            const maxDim = Math.max(size.x, size.y, size.z);
            const scale = 2.0 / maxDim;
            model.scale.setScalar(scale);
            model.position.sub(center.multiplyScalar(scale));
            model.position.y += size.y * scale / 2;

            // Collect stats
            let vertCount = 0;
            let texRes = 'none';
            model.traverse(child => {
                if (child.isMesh) {
                    viewer.meshes.push(child);
                    vertCount += child.geometry.attributes.position.count;
                    if (child.material && child.material.map) {
                        const img = child.material.map.image;
                        if (img) texRes = `${img.width}x${img.height}`;
                    }
                }
            });
            viewer.info.textContent = `Verts: ${vertCount.toLocaleString()} | Tex: ${texRes}`;
            setStatus('Ready');
        },
        (progress) => {
            if (progress.total) {
                const pct = Math.round(progress.loaded / progress.total * 100);
                setStatus(`Loading... ${pct}%`);
            }
        },
        (error) => {
            viewer.info.textContent = `Error: ${error.message}`;
            setStatus('Load failed');
        }
    );
}

loadModel(left, leftUrl);
loadModel(right, rightUrl);

// Camera sync
let syncEnabled = true;
const syncBtn = document.getElementById('sync-btn');
syncBtn.addEventListener('click', () => {
    syncEnabled = !syncEnabled;
    syncBtn.classList.toggle('active', syncEnabled);
});

// Sync: copy camera state from active panel to other
function syncCameras(source, target) {
    if (!syncEnabled) return;
    target.camera.position.copy(source.camera.position);
    target.camera.quaternion.copy(source.camera.quaternion);
    target.controls.target.copy(source.controls.target);
    target.controls.update();
}

// Detect which panel is being interacted with
let activeViewer = null;
[left, right].forEach((v, i) => {
    v.canvas.addEventListener('pointerdown', () => { activeViewer = v; });
    v.canvas.addEventListener('wheel', () => { activeViewer = v; });
});

// Wireframe toggle
const wireframeBtn = document.getElementById('wireframe-btn');
let wireframeOn = false;
wireframeBtn.addEventListener('click', () => {
    wireframeOn = !wireframeOn;
    wireframeBtn.classList.toggle('active', wireframeOn);
    [left, right].forEach(v => {
        v.meshes.forEach(m => { m.material.wireframe = wireframeOn; });
    });
});

// Heatmap toggle — fetches per-vertex displacements and applies color
const heatmapBtn = document.getElementById('heatmap-btn');
let heatmapOn = false;
let heatmapData = null;

if (heatmapBtn) {
  heatmapBtn.addEventListener('click', async () => {
    heatmapOn = !heatmapOn;
    heatmapBtn.classList.toggle('active', heatmapOn);

    if (heatmapOn && !heatmapData) {
      // Fetch heatmap data from API
      const meshIdOld = params.get('mesh_id_old');
      const meshIdNew = params.get('mesh_id_new');
      const customerId = params.get('customer_id') || '1';
      const token = params.get('token') || '';

      if (meshIdOld && meshIdNew) {
        try {
          setStatus('Loading heatmap...');
          const resp = await fetch(`/web_app/api/customer/${customerId}/compare_meshes`, {
            method: 'POST',
            headers: {
              'Content-Type': 'application/json',
              'Authorization': `Bearer ${token}`,
            },
            body: JSON.stringify({ mesh_id_old: meshIdOld, mesh_id_new: meshIdNew }),
          });
          heatmapData = await resp.json();
          setStatus('Ready');
        } catch (e) {
          setStatus('Heatmap fetch failed');
          heatmapOn = false;
          heatmapBtn.classList.remove('active');
          return;
        }
      }
    }

    // Apply or remove vertex colors on the right (newer) mesh
    right.meshes.forEach(mesh => {
      if (heatmapOn && heatmapData && heatmapData.status === 'success') {
        const geo = mesh.geometry;
        const count = geo.attributes.position.count;
        const values = heatmapData.heatmap_values || [];

        if (!geo.getAttribute('color')) {
          geo.setAttribute('color', new THREE.BufferAttribute(new Float32Array(count * 3), 3));
        }
        const colors = geo.getAttribute('color');

        for (let i = 0; i < count; i++) {
          const v = i < values.length ? values[i] : 0;
          // Blue (0) → White (0.5) → Red (1) colormap
          if (v < 0.5) {
            const t = v * 2; // 0→1
            colors.setXYZ(i, t, t, 1.0);           // blue → white
          } else {
            const t = (v - 0.5) * 2; // 0→1
            colors.setXYZ(i, 1.0, 1.0 - t, 1.0 - t); // white → red
          }
        }
        colors.needsUpdate = true;
        mesh.material.vertexColors = true;
        mesh.material.needsUpdate = true;
      } else {
        // Remove heatmap
        mesh.material.vertexColors = false;
        mesh.material.needsUpdate = true;
      }
    });
  });
}

// Auto-rotate toggle
const rotateBtn = document.getElementById('rotate-btn');
let autoRotate = false;
rotateBtn.addEventListener('click', () => {
    autoRotate = !autoRotate;
    rotateBtn.classList.toggle('active', autoRotate);
    left.controls.autoRotate = autoRotate;
    right.controls.autoRotate = autoRotate;
    left.controls.autoRotateSpeed = 2.0;
    right.controls.autoRotateSpeed = 2.0;
});

// Divider drag to resize panels
const divider = document.getElementById('divider');
let isDragging = false;
divider.addEventListener('mousedown', () => { isDragging = true; });
window.addEventListener('mouseup', () => { isDragging = false; });
window.addEventListener('mousemove', (e) => {
    if (!isDragging) return;
    const container = document.getElementById('comparison-container');
    const rect = container.getBoundingClientRect();
    const ratio = (e.clientX - rect.left) / rect.width;
    const clamped = Math.max(0.2, Math.min(0.8, ratio));
    document.getElementById('left-panel').style.flex = `${clamped}`;
    document.getElementById('right-panel').style.flex = `${1 - clamped}`;
    resize();
});

// Render loop
function animate() {
    requestAnimationFrame(animate);

    left.controls.update();
    right.controls.update();

    // Sync cameras
    if (activeViewer === left) syncCameras(left, right);
    else if (activeViewer === right) syncCameras(right, left);

    left.renderer.render(left.scene, left.camera);
    right.renderer.render(right.scene, right.camera);
}
animate();