"""Generate a demo GLB with embedded PBR maps for the viewer.
Run: python scripts/generate_demo_glb.py
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np
from core.smpl_fitting import build_body_mesh
from core.uv_unwrap import compute_uvs, DEFAULT_ATLAS
from core.mesh_reconstruction import export_glb, _generate_normal_map

print('Building body mesh...')
mesh = build_body_mesh()
verts = mesh['vertices']
faces = mesh['faces']
uvs = compute_uvs(verts, mesh['body_part_ids'], DEFAULT_ATLAS)
print(f'  {len(verts)} vertices, {len(faces)} faces')

print('Generating normal map...')
normal_map = _generate_normal_map(verts, faces, uvs, atlas_size=2048)

print('Generating PBR maps...')
roughness_map = None
ao_map = None
try:
    from core.texture_factory import generate_roughness_map, generate_ao_map
    roughness_map = generate_roughness_map(uvs, atlas_size=2048, vertices=verts)
    if roughness_map is not None and roughness_map.dtype != np.uint8:
        roughness_map = (roughness_map * 255).astype(np.uint8)
    ao_map = generate_ao_map(verts, faces, uvs, atlas_size=2048)
    if ao_map is not None and ao_map.dtype != np.uint8:
        ao_map = (ao_map * 255).astype(np.uint8)
    print(f'  roughness={roughness_map.shape if roughness_map is not None else None}')
    print(f'  ao={ao_map.shape if ao_map is not None else None}')
except Exception as e:
    print(f'  PBR generation failed: {e}')

out_path = os.path.join('web_app', 'static', 'viewer3d', 'demo_pbr.glb')
print(f'Exporting GLB to {out_path}...')
export_glb(verts, faces, out_path,
           uvs=uvs,
           normal_map=normal_map,
           roughness_map=roughness_map,
           ao_map=ao_map)
size_kb = os.path.getsize(out_path) / 1024
print(f'Done: {out_path} ({size_kb:.0f} KB)')
print()
print('Open in viewer:')
print('  http://192.168.100.16:8000/web_app/static/viewer3d/index.html?model=demo_pbr.glb')
