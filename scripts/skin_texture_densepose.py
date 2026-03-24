"""
skin_texture_densepose.py — Real skin texture from photos via DensePose.

This is how it's actually done:
  1. DensePose maps every pixel of YOU in the photo → body surface coordinates
  2. Back-project photo colors into a UV texture atlas
  3. Merge front + back views with weighted blending
  4. Convert DensePose atlas → SMPL UV texture
  5. Inpaint gaps, generate PBR maps
  6. Export textured GLB

Usage:
  python scripts/skin_texture_densepose.py --dir captures/skin_scan/
  python scripts/skin_texture_densepose.py front.jpg back.jpg
  python scripts/skin_texture_densepose.py --dir captures/skin_scan/ --backend cloud
"""
import sys
import os
import time
import argparse
import logging

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np
import cv2

logging.basicConfig(level=logging.INFO, format='%(name)s: %(message)s')
logger = logging.getLogger('skin_texture')


def find_photos(args):
    """Find front/back/side photos from args or directory."""
    photos = {}
    directions = ['front', 'back', 'left', 'right']

    if args.dir:
        for f in os.listdir(args.dir):
            fl = f.lower()
            for d in directions:
                if d in fl and fl.endswith(('.jpg', '.jpeg', '.png')):
                    photos[d] = os.path.join(args.dir, f)
                    break
    elif args.images:
        for i, path in enumerate(args.images):
            if i < len(directions):
                photos[directions[i]] = path

    return photos


def main():
    parser = argparse.ArgumentParser(description='DensePose skin texture pipeline')
    parser.add_argument('images', nargs='*', help='front.jpg back.jpg [left.jpg right.jpg]')
    parser.add_argument('--dir', '-d', help='Directory with named photos')
    parser.add_argument('--backend', choices=['torchscript', 'detectron2', 'cloud', 'auto'],
                        default='auto', help='DensePose backend')
    parser.add_argument('--atlas', type=int, default=1024, help='Atlas resolution')
    parser.add_argument('--output', '-o', help='Output GLB path')
    parser.add_argument('--profile', type=str, help='Body measurements: height=178,weight=75')
    parser.add_argument('--debug', action='store_true', help='Save intermediate results')
    args = parser.parse_args()

    t0 = time.time()

    # ── Step 1: Find photos ───────────────────────────────────────────────────
    print("\n=== Step 1: Finding photos ===")
    photos = find_photos(args)
    if not photos:
        print("ERROR: No photos found. Use --dir or pass image paths.")
        sys.exit(1)

    for direction, path in photos.items():
        img = cv2.imread(path)
        if img is not None:
            print(f"  {direction}: {path} ({img.shape[1]}x{img.shape[0]})")
        else:
            print(f"  {direction}: {path} (UNREADABLE)")
            del photos[direction]

    # ── Step 2: Check DensePose backend ───────────────────────────────────────
    print("\n=== Step 2: DensePose backend ===")
    from core.densepose_infer import detect_backend, predict_iuv

    backend = args.backend if args.backend != 'auto' else None
    if backend is None:
        backend = detect_backend()

    if backend is None:
        print("ERROR: No DensePose backend available!")
        print()
        print("Install one of these:")
        print()
        print("  Option A — DensePose-TorchScript (easiest, no detectron2):")
        print("    git clone https://github.com/dajes/DensePose-TorchScript third_party/DensePose-TorchScript")
        print()
        print("  Option B — Detectron2 (full, needs CUDA):")
        print("    pip install detectron2")
        print()
        print("  Option C — Cloud GPU (uses RunPod, needs API key):")
        print("    export RUNPOD_API_KEY=your_key")
        print("    export RUNPOD_ENDPOINT=your_endpoint")
        print()
        print("  Option D — Install via setup script:")
        print("    python scripts/setup_densepose.py")
        sys.exit(1)

    print(f"  Backend: {backend}")

    # ── Step 3: Run DensePose inference ───────────────────────────────────────
    print("\n=== Step 3: Running DensePose inference ===")
    debug_dir = os.path.join('meshes', 'debug_textures') if args.debug else None
    if debug_dir:
        os.makedirs(debug_dir, exist_ok=True)

    image_paths = []
    iuv_maps = []

    for direction, path in photos.items():
        print(f"  Processing {direction}...")
        iuv = predict_iuv(path, backend=backend)
        if iuv is not None:
            image_paths.append(path)
            iuv_maps.append(iuv)

            # Coverage stats
            body_pixels = (iuv[:, :, 0] > 0).sum()
            total_pixels = iuv.shape[0] * iuv.shape[1]
            print(f"    Body pixels: {body_pixels}/{total_pixels} ({100*body_pixels/total_pixels:.1f}%)")

            # Debug: save IUV visualization
            if debug_dir:
                # Color-code body parts
                vis = np.zeros((*iuv.shape[:2], 3), dtype=np.uint8)
                for p in range(1, 25):
                    mask = iuv[:, :, 0] == p
                    vis[mask] = [
                        int(((p * 37) % 255)),
                        int(((p * 73) % 255)),
                        int(((p * 113) % 255)),
                    ]
                cv2.imwrite(os.path.join(debug_dir, f'iuv_{direction}.png'), vis)
        else:
            print(f"    FAILED — no IUV map generated")

    if not iuv_maps:
        print("ERROR: DensePose inference failed for all images")
        sys.exit(1)

    # ── Step 4: Build texture atlas ───────────────────────────────────────────
    print(f"\n=== Step 4: Building {args.atlas}x{args.atlas} texture atlas ===")
    from core.densepose_texture import photo_to_body_texture

    result = photo_to_body_texture(
        image_paths, iuv_maps,
        atlas_size=args.atlas,
        output_dir=debug_dir
    )
    print(f"  Coverage: {result['coverage']:.1f}%")

    # ── Step 5: Build body mesh ───────────────────────────────────────────────
    print("\n=== Step 5: Building body mesh ===")
    from core.smpl_fitting import build_body_mesh

    profile = None
    if args.profile:
        profile = {}
        for pair in args.profile.split(','):
            if '=' in pair:
                k, v = pair.split('=', 1)
                k = k.strip()
                if k == 'height': k = 'height_cm'
                elif k == 'weight': k = 'weight_kg'
                elif not k.endswith(('_cm', '_kg')): k = k + '_cm'
                profile[k] = float(v)

    mesh = build_body_mesh(profile)
    verts = mesh['vertices']
    faces = mesh['faces']
    uvs = mesh.get('uvs')

    if uvs is None:
        from core.uv_unwrap import compute_uvs, DEFAULT_ATLAS
        uvs = compute_uvs(verts, mesh['body_part_ids'], DEFAULT_ATLAS)

    print(f"  {mesh['num_vertices']} verts, {mesh['num_faces']} faces")

    # ── Step 6: Generate PBR maps from texture ────────────────────────────────
    print("\n=== Step 6: PBR maps ===")
    from core.skin_texture import _generate_normal_map, _generate_roughness_map

    albedo = result['smpl_uv']
    normal = _generate_normal_map(albedo, strength=1.2)
    roughness = _generate_roughness_map(albedo)

    # AO from mesh geometry
    ao = None
    try:
        from core.texture_factory import generate_ao_map
        ao = generate_ao_map(verts, faces, uvs, atlas_size=args.atlas)
        if ao is not None and ao.dtype != np.uint8:
            ao = (ao * 255).astype(np.uint8)
    except Exception:
        pass

    print(f"  Normal: {normal.shape}, Roughness: {roughness.shape}")

    # ── Step 7: Export GLB ────────────────────────────────────────────────────
    out_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'meshes')
    os.makedirs(out_dir, exist_ok=True)
    out_glb = args.output or os.path.join(out_dir, 'skin_densepose.glb')

    print(f"\n=== Step 7: Exporting GLB ===")
    from core.mesh_reconstruction import export_glb

    export_glb(
        verts, faces, out_glb,
        normals=True,
        uvs=uvs,
        texture_image=albedo,
        normal_map=normal,
        roughness_map=roughness,
        ao_map=ao,
    )
    size_mb = os.path.getsize(out_glb) / 1024 / 1024
    print(f"  GLB: {out_glb} ({size_mb:.1f} MB)")

    dt = time.time() - t0
    print(f"\n=== Done in {dt:.1f}s ===")
    print(f"  Atlas coverage: {result['coverage']:.1f}%")
    print(f"  Open: {out_glb}")


if __name__ == '__main__':
    main()
