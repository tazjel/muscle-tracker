
let scene, camera, renderer, controls, mesh;

function init() {
    scene = new THREE.Scene();
    scene.background = new THREE.Color(0x1a1a2e);

    camera = new THREE.PerspectiveCamera(75, window.innerWidth / window.innerHeight, 0.1, 1000);
    camera.position.z = 200;

    renderer = new THREE.WebGLRenderer({ antialias: true, preserveDrawingBuffer: true });
    renderer.setSize(window.innerWidth, window.innerHeight);
    document.getElementById('canvas-container').appendChild(renderer.domElement);

    controls = new THREE.OrbitControls(camera, renderer.domElement);
    
    const ambientLight = new THREE.AmbientLight(0xffffff, 0.5);
    scene.add(ambientLight);
    
    const directionalLight = new THREE.DirectionalLight(0xffffff, 0.8);
    directionalLight.position.set(1, 1, 1);
    scene.add(directionalLight);

    window.addEventListener('resize', onWindowResize, false);
    
    loadModel();
    animate();
}

function onWindowResize() {
    camera.aspect = window.innerWidth / window.innerHeight;
    camera.updateProjectionMatrix();
    renderer.setSize(window.innerWidth, window.innerHeight);
}

function animate() {
    requestAnimationFrame(animate);
    controls.update();
    renderer.render(scene, camera);
}

function loadModel() {
    const urlParams = new URLSearchParams(window.location.search);
    const objUrl = urlParams.get('obj');
    
    if (!objUrl) {
        document.getElementById('mesh-info').innerText = 'No OBJ URL provided. Use ?obj=path/to/model.obj';
        // Create a placeholder box if no URL
        const geometry = new THREE.BoxGeometry(50, 50, 50);
        const material = new THREE.MeshPhongMaterial({ color: 0x4a9eff, wireframe: false });
        mesh = new THREE.Mesh(geometry, material);
        scene.add(mesh);
        return;
    }

    const loader = new THREE.OBJLoader();
    loader.load(objUrl, 
        function (object) {
            mesh = object;
            mesh.traverse(function (child) {
                if (child instanceof THREE.Mesh) {
                    child.material = new THREE.MeshPhongMaterial({ 
                        color: 0x4a9eff, 
                        side: THREE.DoubleSide,
                        flatShading: true
                    });
                    
                    // Simple height-based coloring
                    const positions = child.geometry.attributes.position;
                    document.getElementById('v-count').innerText = positions.count;
                    document.getElementById('f-count').innerText = positions.count / 3;
                }
            });
            scene.add(mesh);
            document.getElementById('mesh-info').innerText = 'Model Loaded';
        },
        function (xhr) {
            console.log((xhr.loaded / xhr.total * 100) + '% loaded');
        },
        function (error) {
            console.error('An error happened', error);
            document.getElementById('mesh-info').innerText = 'Error loading model';
        }
    );
}

function toggleWireframe() {
    if (!mesh) return;
    mesh.traverse(function (child) {
        if (child instanceof THREE.Mesh) {
            child.material.wireframe = !child.material.wireframe;
        }
    });
}

function resetCamera() {
    camera.position.set(0, 0, 200);
    controls.reset();
}

function takeScreenshot() {
    const link = document.createElement('a');
    link.download = 'muscle_3d_screenshot.png';
    link.href = renderer.domElement.toDataURL('image/png');
    link.click();
}

init();
