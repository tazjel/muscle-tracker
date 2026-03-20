"""Generate demo_pbr.glb with real FreePBR skin texture baked into UV atlas.
Run: python scripts/generate_demo_glb.py
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np
import cv2

from core.smpl_fitting import build_body_mesh
from core.uv_unwrap import compute_uvs, DEFAULT_ATLAS
from core.mesh_reconstruction import export_glb, _generate_normal_map

ATLAS_SIZE = 2048
SKIN_ALBEDO = os.path.join('apps', 'uploads', 'skin', 'freepbr',
                            'human-skin1-bl', 'human-skin1_albedo.png')
SKIN_NORMAL = os.path.join('apps', 'uploads', 'skin', 'freepbr',
                            'human-skin1-bl', 'human-skin1_normal-ogl.png')
SKIN_ROUGH  = os.path.join('apps', 'uploads', 'skin', 'freepbr',
                            'human-skin1-bl', 'human-skin1_roughness.png')

print('Building body mesh...')
mesh = build_body_mesh()
verts = mesh['vertices']
faces = mesh['faces']
uvs = compute_uvs(verts, mesh['body_part_ids'], DEFAULT_ATLAS)
print(f'  {len(verts)} verts, {len(faces)} faces')

def tile_texture_to_atlas(tex_path, uvs, atlas_size, tiles=8):
    """Tile a skin texture across the UV atlas based on UV coordinates."""
    tex = cv2.imread(tex_path)
    if tex is None:
        print(f'  WARNING: could not load {tex_path}')
        return None
    tex = cv2.resize(tex, (atlas_size, atlas_size), interpolation=cv2.INTER_LANCZOS4)

    # Create tiled atlas by mapping each UV coordinate to tiled texture
    th, tw = tex.shape[:2]
    atlas = np.zeros((atlas_size, atlas_size, 3), dtype=np.uint8)

    # Build pixel-level atlas from UV coords
    u_coords = (uvs[:, 0] * atlas_size).astype(np.int32).clip(0, atlas_size - 1)
    v_coords = ((1 - uvs[:, 1]) * atlas_size).astype(np.int32).clip(0, atlas_size - 1)

    # Flood fill the atlas using face triangles
    for i, face in enumerate(faces):
        i0, i1, i2 = face
        # UV coords for this triangle in atlas space
        u0, v0 = u_coords[i0], v_coords[i0]
        u1, v1 = u_coords[i1], v_coords[i1]
        u2, v2 = u_coords[i2], v_coords[i2]

        # Sample tex using tiled UVs
        tu0 = int((uvs[i0, 0] * tiles % 1) * tw)
        tv0 = int(((1 - uvs[i0, 1]) * tiles % 1) * th)

        # Fast: just set vertex pixels (rasterization would be slow in Python)
        for (u, v, tu, tv) in [
            (u0, v0, int((uvs[i0,0]*tiles%1)*tw), int(((1-uvs[i0,1])*tiles%1)*th)),
            (u1, v1, int((uvs[i1,0]*tiles%1)*tw), int(((1-uvs[i1,1])*tiles%1)*th)),
            (u2, v2, int((uvs[i2,0]*tiles%1)*tw), int(((1-uvs[i2,1])*tiles%1)*th)),
        ]:
            tu = min(max(tu, 0), tw - 1)
            tv = min(max(tv, 0), th - 1)
            atlas[v, u] = tex[tv, tu]

    # Dilate to fill gaps between triangle pixels
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (7, 7))
    mask = (atlas.sum(axis=2) > 0).astype(np.uint8) * 255
    atlas = cv2.inpaint(atlas, cv2.bitwise_not(mask), 5, cv2.INPAINT_TELEA)
    print(f'  Atlas built from {tex_path} ({tiles}x tiles)')
    return atlas


def tile_simple(tex_path, atlas_size, tiles=8):
    """Simple tile approach: just tile the texture into atlas space (fast)."""
    tex = cv2.imread(tex_path)
    if tex is None:
        print(f'  WARNING: could not load {tex_path}')
        return None
    tile_size = atlas_size // tiles
    tex_small = cv2.resize(tex, (tile_size, tile_size), interpolation=cv2.INTER_LANCZOS4)
    # Tile across atlas
    row = np.concatenate([tex_small] * tiles, axis=1)
    atlas = np.concatenate([row] * tiles, axis=0)
    atlas = cv2.resize(atlas, (atlas_size, atlas_size))
    print(f'  Tiled {tex_path} → {atlas.shape}')
    return atlas


print('Building skin texture atlas...')
# Use simple tiling — fast and clean for skin micro-detail
texture_image = tile_simple(SKIN_ALBEDO, ATLAS_SIZE, tiles=8)

# Warm up the skin tone slightly (FreePBR is neutral-pink, add warm tone)
if texture_image is not None:
    # Slight warm tint: boost red a little, keep green, slight blue reduction
    b, g, r = cv2.split(texture_image.astype(np.float32))
    r = np.clip(r * 1.08, 0, 255)
    b = np.clip(b * 0.92, 0, 255)
    texture_image = cv2.merge([b, g, r]).astype(np.uint8)
    print('  Applied warm skin tint')

print('Building normal map (geometry)...')
normal_map = _generate_normal_map(verts, faces, uvs, atlas_size=ATLAS_SIZE)

print('Loading FreePBR roughness map...')
roughness_map = None
ao_map = None
try:
    from core.texture_factory import generate_roughness_map, generate_ao_map
    roughness_map = generate_roughness_map(uvs, atlas_size=ATLAS_SIZE, vertices=verts)
    if roughness_map is not None and roughness_map.dtype != np.uint8:
        roughness_map = (roughness_map * 255).astype(np.uint8)
    ao_map = generate_ao_map(verts, faces, uvs, atlas_size=ATLAS_SIZE)
    if ao_map is not None and ao_map.dtype != np.uint8:
        ao_map = (ao_map * 255).astype(np.uint8)
    print(f'  PBR maps: roughness={roughness_map.shape}, ao={ao_map.shape}')
except Exception as e:
    print(f'  PBR generation: {e}')

out_path = os.path.join('web_app', 'static', 'viewer3d', 'demo_pbr.glb')
print(f'Exporting {out_path}...')
export_glb(verts, faces, out_path,
           uvs=uvs,
           texture_image=texture_image,
           normal_map=normal_map,
           roughness_map=roughness_map,
           ao_map=ao_map)

size_mb = os.path.getsize(out_path) / 1024 / 1024
print(f'\nDone: {out_path} ({size_mb:.1f} MB)')
print('\nOpen now:')
print('  http://192.168.100.16:8000/web_app/static/viewer3d/index.html?model=demo_pbr.glb')
