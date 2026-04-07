import sys
import os
import cv2
import numpy as np
import sqlite3
import argparse

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.smpl_fitting import build_body_mesh
from core.uv_unwrap import compute_uvs, DEFAULT_ATLAS
from core.skin_texture import process_skin_photo
from core.mesh_reconstruction import export_glb

def get_customer_profile(db_path, customer_id=1):
    import json
    
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    row = conn.execute("SELECT * FROM customer WHERE id=?", (customer_id,)).fetchone()
    
    profile = {}
    if row:
        profile = dict(row)
        
    # If height is missing or NULL, fallback to JSON
    if profile.get('height_cm') is None:
        json_path = os.path.join(os.path.dirname(db_path), 'scripts', 'dev_profiles', 'default_human_profile.json')
        if os.path.exists(json_path):
            with open(json_path, 'r') as f:
                json_data = json.load(f)
                profile.update(json_data)
                
    return profile if profile else None

def tile_texture(tex, atlas_size, tiles):
    """Tile a texture across an atlas seamlessly."""
    tile_size = atlas_size // tiles
    small = cv2.resize(tex, (tile_size, tile_size), interpolation=cv2.INTER_LANCZOS4)
    row = np.concatenate([small] * tiles, axis=1)
    atlas = np.concatenate([row] * tiles, axis=0)
    return cv2.resize(atlas, (atlas_size, atlas_size), interpolation=cv2.INTER_LANCZOS4)

def main():
    parser = argparse.ArgumentParser(description='Apply macro skin photo to 3D mesh.')
    parser.add_argument('--macro', type=str, required=True, help='Path to macro skin image')
    parser.add_argument('--db', type=str, default='database.db', help='Path to database')
    parser.add_argument('--atlas', type=int, default=4096, help='Atlas size (4K for high detail)')
    parser.add_argument('--tiles', type=int, default=16, help='Number of tiles across the atlas')
    args = parser.parse_args()

    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    db_path = os.path.join(project_root, args.db)
    
    print("\n=== Step 1: Loading Customer Profile ===")
    profile = get_customer_profile(db_path, 1)
    if profile:
        print(f"  Loaded Customer 1: {profile.get('name', 'Unknown')}, Height: {profile.get('height_cm')}cm")
    else:
        print("  Could not find Customer 1, using default.")
        profile = None

    print("\n=== Step 2: Processing Macro Photo into Seamless PBR Tiles ===")
    out_dir = os.path.join(project_root, 'meshes', 'debug_textures')
    
    # Process into albedo, normal, roughness
    try:
        pbr_paths = process_skin_photo(args.macro, out_dir, size=512)
        print(f"  Generated tileable maps in {out_dir}")
    except Exception as e:
        print(f"ERROR processing skin photo: {e}")
        sys.exit(1)

    albedo_tile = cv2.imread(pbr_paths['albedo'])
    normal_tile = cv2.imread(pbr_paths['normal'])
    rough_tile = cv2.imread(pbr_paths['roughness'], cv2.IMREAD_GRAYSCALE)

    if albedo_tile is None or normal_tile is None:
        print("ERROR: Failed to load generated skin maps.")
        sys.exit(1)

    print(f"\n=== Step 3: Tiling PBR maps across {args.atlas}x{args.atlas} Atlas ({args.tiles}x tiles) ===")
    albedo_atlas = tile_texture(albedo_tile, args.atlas, args.tiles)
    normal_atlas = tile_texture(normal_tile, args.atlas, args.tiles)
    
    rough_atlas = None
    if rough_tile is not None:
        rough_atlas_bgr = tile_texture(cv2.cvtColor(rough_tile, cv2.COLOR_GRAY2BGR), args.atlas, args.tiles)
        rough_atlas = cv2.cvtColor(rough_atlas_bgr, cv2.COLOR_BGR2GRAY)

    print("  Atlases generated.")

    print("\n=== Step 4: Generating Customer Mesh ===")
    try:
        # Some fields might be None in DB, clean them up for build_body_mesh
        if profile:
            profile = {k: v for k, v in profile.items() if v is not None}
        mesh = build_body_mesh(profile)
    except Exception as e:
        print(f"Error building mesh: {e}")
        mesh = build_body_mesh(None)

    verts = mesh['vertices']
    faces = mesh['faces']
    uvs = mesh.get('uvs')
    if uvs is None:
        from core.uv_unwrap import compute_uvs, DEFAULT_ATLAS
        uvs = compute_uvs(verts, mesh['body_part_ids'], DEFAULT_ATLAS)
    
    print(f"  Mesh: {len(verts)} verts, {len(faces)} faces.")

    # Anatomy variations
    print("\n=== Step 5: Applying Anatomical Color Variations ===")
    try:
        from core.texture_factory import generate_anatomical_overlay
        overlay = generate_anatomical_overlay(uvs, args.atlas)
        oh, ow = albedo_atlas.shape[:2]
        overlay = cv2.resize(overlay, (ow, oh), interpolation=cv2.INTER_LINEAR)
        diff = overlay.astype(np.float32) - 128.0
        albedo_atlas = np.clip(
            albedo_atlas.astype(np.float32) + diff * 0.2,
            0, 255
        ).astype(np.uint8)
        print("  Applied anatomical shading (joints, etc).")
    except Exception as e:
        print(f"  Anatomical overlay skipped: {e}")

    print("\n=== Step 6: Exporting Final GLB ===")
    out_glb = os.path.join(project_root, 'meshes', 'macro_skin_body.glb')
    
    export_glb(
        verts, faces, out_glb,
        normals=True,
        uvs=uvs,
        texture_image=albedo_atlas,
        normal_map=normal_atlas,
        roughness_map=rough_atlas,
    )
    
    size_mb = os.path.getsize(out_glb) / 1024 / 1024
    print(f"\nSUCCESS! 3D Body baked with Macro Skin: {out_glb} ({size_mb:.1f} MB)")

if __name__ == '__main__':
    main()
