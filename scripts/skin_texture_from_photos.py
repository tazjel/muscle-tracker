"""
skin_texture_from_photos.py — Apply YOUR skin tone to a 3D body mesh.

Approach:
  1. Extract skin color from your front/back photos
  2. Color-match a professional PBR skin texture to your tone (LAB space)
  3. Add anatomical variation (darker elbows/knees, lighter palms)
  4. Tile across UV atlas with PBR normal/roughness/AO maps
  5. Export GLB

Usage:
  python scripts/skin_texture_from_photos.py --dir captures/skin_scan/
"""
import sys
import os
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np
import cv2

from core.smpl_fitting import build_body_mesh
from core.mesh_reconstruction import export_glb


SKIN_DIR = os.path.join('apps', 'uploads', 'skin', 'freepbr', 'human-skin1-bl')
SKIN_ALBEDO = os.path.join(SKIN_DIR, 'human-skin1_albedo.png')
SKIN_NORMAL = os.path.join(SKIN_DIR, 'human-skin1_normal-ogl.png')
SKIN_ROUGH  = os.path.join(SKIN_DIR, 'human-skin1_roughness.png')
SKIN_AO     = os.path.join(SKIN_DIR, 'human-skin1_ao.png')


def detect_skin_region(img):
    """Detect skin-colored pixels via HSV thresholding."""
    hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
    mask1 = cv2.inRange(hsv, np.array([0, 20, 50]), np.array([30, 255, 255]))
    mask2 = cv2.inRange(hsv, np.array([160, 20, 50]), np.array([180, 255, 255]))
    mask = cv2.bitwise_or(mask1, mask2)
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (15, 15))
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel)
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel)
    return mask


def extract_skin_color(img):
    """Extract median skin color from a body photo."""
    mask = detect_skin_region(img)
    # Focus on center 60%
    h, w = img.shape[:2]
    mx, my = int(w * 0.2), int(h * 0.1)
    center = np.zeros_like(mask)
    center[my:h - my, mx:w - mx] = 255
    skin = cv2.bitwise_and(mask, center)

    pixels = img[skin > 0]
    if len(pixels) < 100:
        # Fallback: center crop
        s = min(h, w) // 3
        y0, x0 = (h - s) // 2, (w - s) // 2
        pixels = img[y0:y0 + s, x0:x0 + s].reshape(-1, 3)

    # Use median (robust to outliers like clothing edges)
    return np.median(pixels, axis=0).astype(np.uint8)


def color_match_skin(base_texture, target_bgr):
    """
    Shift a PBR skin texture to match a target skin color.
    Uses LAB color space for perceptual accuracy.
    """
    # Convert both to LAB
    base_lab = cv2.cvtColor(base_texture, cv2.COLOR_BGR2LAB).astype(np.float32)
    target_pixel = np.array([[target_bgr]], dtype=np.uint8)
    target_lab = cv2.cvtColor(target_pixel, cv2.COLOR_BGR2LAB).astype(np.float32)[0, 0]

    # Current mean LAB of the base texture
    base_mean = base_lab.mean(axis=(0, 1))

    # Shift: preserve texture detail, change overall color
    shift = target_lab - base_mean
    base_lab[:, :, 0] = np.clip(base_lab[:, :, 0] + shift[0], 0, 255)
    base_lab[:, :, 1] = np.clip(base_lab[:, :, 1] + shift[1], 0, 255)
    base_lab[:, :, 2] = np.clip(base_lab[:, :, 2] + shift[2], 0, 255)

    return cv2.cvtColor(base_lab.astype(np.uint8), cv2.COLOR_LAB2BGR)


def tile_texture(tex, atlas_size, tiles):
    """Tile a texture across an atlas."""
    tile_size = atlas_size // tiles
    small = cv2.resize(tex, (tile_size, tile_size), interpolation=cv2.INTER_LANCZOS4)
    row = np.concatenate([small] * tiles, axis=1)
    atlas = np.concatenate([row] * tiles, axis=0)
    return cv2.resize(atlas, (atlas_size, atlas_size), interpolation=cv2.INTER_LANCZOS4)


def add_anatomical_variation(albedo_atlas, uvs, vertices, atlas_size):
    """
    Add subtle anatomical color variation:
    - Darker: elbows, knees, knuckles, neck creases
    - Lighter: inner arms, palms
    - Reddish: cheeks, lips, fingertips
    Uses vertex height as a simple proxy for body region.
    """
    try:
        from core.texture_factory import generate_anatomical_overlay
        overlay = generate_anatomical_overlay(uvs, atlas_size)
        oh, ow = albedo_atlas.shape[:2]
        overlay = cv2.resize(overlay, (ow, oh), interpolation=cv2.INTER_LINEAR)
        diff = overlay.astype(np.float32) - 128.0
        result = np.clip(
            albedo_atlas.astype(np.float32) + diff * 0.2,
            0, 255
        ).astype(np.uint8)
        print("  Applied anatomical color variation")
        return result
    except Exception as e:
        print(f"  Anatomical overlay skipped: {e}")
        return albedo_atlas


def main():
    import argparse
    parser = argparse.ArgumentParser(description='Apply your skin tone to 3D body')
    parser.add_argument('images', nargs='*', help='front.jpg [back.jpg]')
    parser.add_argument('--dir', '-d', help='Directory with front/back photos')
    parser.add_argument('--atlas', type=int, default=2048)
    parser.add_argument('--tiles', type=int, default=8)
    parser.add_argument('--output', '-o', type=str, default=None)
    parser.add_argument('--profile', type=str, default=None)
    args = parser.parse_args()

    t0 = time.time()

    # ── Step 1: Load photos and extract skin color ────────────────────────────
    print("\n=== Step 1: Extracting your skin color ===")
    front_path = back_path = None

    if args.dir:
        for f in os.listdir(args.dir):
            fl = f.lower()
            if 'front' in fl and fl.endswith(('.jpg', '.jpeg', '.png')):
                front_path = os.path.join(args.dir, f)
            elif 'back' in fl and fl.endswith(('.jpg', '.jpeg', '.png')):
                back_path = os.path.join(args.dir, f)
    elif args.images:
        front_path = args.images[0]
        back_path = args.images[1] if len(args.images) > 1 else None

    if not front_path:
        print("ERROR: Need at least a front photo")
        sys.exit(1)

    front_img = cv2.imread(front_path)
    front_color = extract_skin_color(front_img)
    print(f"  Front skin: BGR({front_color[0]}, {front_color[1]}, {front_color[2]})")

    if back_path:
        back_img = cv2.imread(back_path)
        if back_img is not None:
            back_color = extract_skin_color(back_img)
            print(f"  Back skin:  BGR({back_color[0]}, {back_color[1]}, {back_color[2]})")
            # Average front + back
            target_color = ((front_color.astype(np.float32) + back_color.astype(np.float32)) / 2).astype(np.uint8)
        else:
            target_color = front_color
    else:
        target_color = front_color

    print(f"  Target:     BGR({target_color[0]}, {target_color[1]}, {target_color[2]})")

    # ── Step 2: Color-match PBR skin texture ──────────────────────────────────
    print("\n=== Step 2: Color-matching PBR skin texture ===")
    base_albedo = cv2.imread(SKIN_ALBEDO)
    if base_albedo is None:
        print(f"ERROR: Could not load {SKIN_ALBEDO}")
        sys.exit(1)

    matched_albedo = color_match_skin(base_albedo, target_color)
    print(f"  Shifted FreePBR skin → your tone")

    # Save debug
    debug_dir = os.path.join('meshes', 'debug_textures')
    os.makedirs(debug_dir, exist_ok=True)
    cv2.imwrite(os.path.join(debug_dir, 'color_matched_tile.png'), matched_albedo)

    # ── Step 3: Tile across atlas ─────────────────────────────────────────────
    print(f"\n=== Step 3: Building {args.atlas}x{args.atlas} atlas ({args.tiles}x tiles) ===")
    albedo_atlas = tile_texture(matched_albedo, args.atlas, args.tiles)

    # Normal map (from FreePBR — has real skin pore detail)
    normal_tex = cv2.imread(SKIN_NORMAL)
    normal_atlas = tile_texture(normal_tex, args.atlas, args.tiles) if normal_tex is not None else None

    # Roughness map
    rough_tex = cv2.imread(SKIN_ROUGH, cv2.IMREAD_GRAYSCALE)
    rough_atlas = tile_texture(cv2.cvtColor(rough_tex, cv2.COLOR_GRAY2BGR), args.atlas, args.tiles) if rough_tex is not None else None
    if rough_atlas is not None and len(rough_atlas.shape) == 3:
        rough_atlas = cv2.cvtColor(rough_atlas, cv2.COLOR_BGR2GRAY)

    # AO map
    ao_tex = cv2.imread(SKIN_AO, cv2.IMREAD_GRAYSCALE)
    ao_atlas = tile_texture(cv2.cvtColor(ao_tex, cv2.COLOR_GRAY2BGR), args.atlas, args.tiles) if ao_tex is not None else None
    if ao_atlas is not None and len(ao_atlas.shape) == 3:
        ao_atlas = cv2.cvtColor(ao_atlas, cv2.COLOR_BGR2GRAY)

    print(f"  Albedo:    {albedo_atlas.shape}")
    if normal_atlas is not None:
        print(f"  Normal:    {normal_atlas.shape}")
    if rough_atlas is not None:
        print(f"  Roughness: {rough_atlas.shape}")

    # ── Step 4: Build body mesh ───────────────────────────────────────────────
    print("\n=== Step 4: Building body mesh ===")
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

    # ── Step 5: Add anatomical variation ──────────────────────────────────────
    print("\n=== Step 5: Anatomical variation ===")
    albedo_atlas = add_anatomical_variation(albedo_atlas, uvs, verts, args.atlas)

    # ── Step 6: Generate geometry-based AO if FreePBR AO is missing ──────────
    if ao_atlas is None:
        try:
            from core.texture_factory import generate_ao_map
            ao_atlas = generate_ao_map(verts, faces, uvs, atlas_size=args.atlas)
            if ao_atlas is not None and ao_atlas.dtype != np.uint8:
                ao_atlas = (ao_atlas * 255).astype(np.uint8)
        except Exception:
            pass

    # ── Step 7: Export GLB ────────────────────────────────────────────────────
    out_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'meshes')
    os.makedirs(out_dir, exist_ok=True)
    out_glb = args.output or os.path.join(out_dir, 'skin_textured.glb')

    print(f"\n=== Step 6: Exporting GLB ===")
    export_glb(
        verts, faces, out_glb,
        normals=True,
        uvs=uvs,
        texture_image=albedo_atlas,
        normal_map=normal_atlas,
        roughness_map=rough_atlas,
        ao_map=ao_atlas,
    )
    size_mb = os.path.getsize(out_glb) / 1024 / 1024
    print(f"  GLB: {out_glb} ({size_mb:.1f} MB)")

    # Save debug
    cv2.imwrite(os.path.join(debug_dir, 'albedo_atlas.png'), albedo_atlas)
    if normal_atlas is not None:
        cv2.imwrite(os.path.join(debug_dir, 'normal_atlas.png'), normal_atlas)

    dt = time.time() - t0
    print(f"\n=== Done in {dt:.1f}s ===")
    print(f"  Open: {out_glb}")


if __name__ == '__main__':
    main()
