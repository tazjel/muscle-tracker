"""End-to-end test for MPFB2 template pipeline (S-T5)."""
import sys, os, time
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

results = []

def check(name, fn):
    t0 = time.time()
    try:
        fn()
        dt = time.time() - t0
        results.append((name, 'PASS', dt))
        print(f'  [{name}] PASS ({dt:.2f}s)')
    except Exception as e:
        dt = time.time() - t0
        results.append((name, 'FAIL', dt))
        print(f'  [{name}] FAIL ({dt:.2f}s): {e}')

print('=== MPFB2 Pipeline E2E Test ===\n')

# 1. Deform template
mesh = {}
def test_deform():
    from core.body_deform import deform_template
    m = deform_template({'height_cm': 175, 'chest_circumference_cm': 100})
    assert m['vertices'].shape == (13380, 3), f'Wrong shape: {m["vertices"].shape}'
    assert m['faces'].shape[1] == 3
    assert m['uvs'].shape == (13380, 2)
    assert m['body_part_ids'].max() > 0, 'body_part_ids all zeros'
    assert m['mesh_type'] == 'mpfb2'
    mesh.update(m)
check('deform_template', test_deform)

verts = mesh.get('vertices')
faces = mesh.get('faces')
uvs = mesh.get('uvs')

# 2. Part ID dispatcher
def test_part_ids():
    from core.texture_factory import get_part_ids
    import numpy as np
    p = get_part_ids(13380)
    assert p is not None and len(p) == 13380
    assert len(np.unique(p)) >= 10
    # SMPL path still works
    s = get_part_ids(6890)
    assert s is not None and len(s) == 6890
check('get_part_ids', test_part_ids)

# 3. Roughness map
def test_roughness():
    from core.texture_factory import generate_roughness_map
    rm = generate_roughness_map(uvs, atlas_size=512, vertices=verts)
    assert rm is not None and rm.shape == (512, 512), f'Shape: {rm.shape}'
    assert rm.min() >= 0 and rm.max() <= 1
check('roughness_map', test_roughness)

# 4. AO map
def test_ao():
    from core.texture_factory import generate_ao_map
    ao = generate_ao_map(verts, faces, uvs, atlas_size=512)
    assert ao is not None
check('ao_map', test_ao)

# 5. GLB export
def test_glb():
    from core.mesh_reconstruction import export_glb
    out = os.path.join('meshes', 'test_mpfb2_e2e.glb')
    export_glb(verts, faces, out, uvs=uvs)
    assert os.path.exists(out), 'GLB not created'
    size = os.path.getsize(out)
    assert size > 10000, f'GLB too small: {size}'
    print(f'    GLB size: {size/1024:.0f} KB')
check('export_glb', test_glb)

# Summary
print(f'\n=== Results: {sum(1 for _,s,_ in results if s=="PASS")}/{len(results)} passed ===')
total_time = sum(dt for _,_,dt in results)
print(f'Total time: {total_time:.2f}s')

if any(s == 'FAIL' for _,s,_ in results):
    sys.exit(1)
