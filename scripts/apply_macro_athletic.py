import sys
import os
import cv2
import trimesh
import argparse

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.skin_texture import process_skin_photo
from core.mesh_reconstruction import export_glb

def main():
    parser = argparse.ArgumentParser(description='Apply macro skin to athletic MPFB mesh.')
    parser.add_argument('--macro', type=str, required=True, help='Path to macro skin image')
    parser.add_argument('--uv-scale', type=float, default=14.0, help='Scale factor for UV tiling')
    args = parser.parse_args()

    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    
    print("\n=== Step 1: Processing Macro Photo into High-Res PBR Maps ===")
    out_dir = os.path.join(project_root, 'meshes', 'debug_textures')
    
    try:
        # Use 2048 for high-res tile
        pbr_paths = process_skin_photo(args.macro, out_dir, size=2048)
        print(f"  Generated 2K tileable maps in {out_dir}")
    except Exception as e:
        print(f"ERROR processing skin photo: {e}")
        sys.exit(1)

    albedo_tile = cv2.imread(pbr_paths['albedo'])
    normal_tile = cv2.imread(pbr_paths['normal'])
    rough_tile = cv2.imread(pbr_paths['roughness'], cv2.IMREAD_GRAYSCALE)

    if albedo_tile is None or normal_tile is None:
        print("ERROR: Failed to load generated skin maps.")
        sys.exit(1)

    print(f"\n=== Step 2: Loading High-Res Male Mesh ===")
    mesh_path = os.path.join(project_root, 'meshes', 'mpfb_male_body.glb')
    if not os.path.exists(mesh_path):
        mesh_path = os.path.join(project_root, 'meshes', 'mpfb_male_body.glb')
        
    try:
        mesh = trimesh.load(mesh_path, force='mesh')
        verts = mesh.vertices
        faces = mesh.faces
        # Automatically flip Y on UVs if needed or just scale
        uvs = mesh.visual.uv * args.uv_scale
        print(f"  Loaded {os.path.basename(mesh_path)}: {len(verts)} verts.")
    except Exception as e:
        print(f"ERROR loading base mesh: {e}")
        sys.exit(1)

    print("\n=== Step 3: Exporting HW-Accelerated GLB ===")
    # Notice we don't tile manually. We just pass the base 2K images and scaled UVs.
    out_glb = os.path.join(project_root, 'meshes', 'macro_skin_body.glb')
    
    export_glb(
        verts, faces, out_glb,
        normals=True,
        uvs=uvs,
        texture_image=albedo_tile,
        normal_map=normal_tile,
        roughness_map=rough_tile,
    )
    
    size_mb = os.path.getsize(out_glb) / 1024 / 1024
    print(f"\nSUCCESS! 3D Body baked to {out_glb} ({size_mb:.1f} MB)")
    print(f"Hardware-native {args.uv_scale}x UV tiling applied. File size reduced massively!")

if __name__ == '__main__':
    main()
