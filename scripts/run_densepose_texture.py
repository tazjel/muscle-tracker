"""
run_densepose_texture.py — End-to-end: photos → DensePose IUV → KDTree NN texture → GLB.

This is the standalone pipeline script. No MCP, no cloud — runs locally.

Usage:
  python scripts/run_densepose_texture.py
  python scripts/run_densepose_texture.py --views front back
  python scripts/run_densepose_texture.py --atlas 2048 --output meshes/my_body.glb
"""
import sys
import os
import time
import argparse
import logging

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import cv2
import numpy as np

logging.basicConfig(level=logging.INFO, format='%(name)s: %(message)s')
logger = logging.getLogger('densepose_texture')

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCAN_DIR = os.path.join(PROJECT_ROOT, 'captures', 'skin_scan')
DEBUG_DIR = os.path.join(PROJECT_ROOT, 'meshes', 'debug_textures')
MESHES_DIR = os.path.join(PROJECT_ROOT, 'meshes')


def main():
    parser = argparse.ArgumentParser(description='DensePose skin texture pipeline')
    parser.add_argument('--views', nargs='+', default=['front', 'back', 'left', 'right'],
                        help='Which views to process')
    parser.add_argument('--scan-dir', default=SCAN_DIR, help='Directory with photos')
    parser.add_argument('--atlas', type=int, default=1024, help='Atlas resolution')
    parser.add_argument('--output', '-o', default=os.path.join(MESHES_DIR, 'skin_densepose.glb'),
                        help='Output GLB path')
    parser.add_argument('--debug', action='store_true', default=True,
                        help='Save debug images')
    parser.add_argument('--verify', action='store_true',
                        help='Run quality verification after export (exit 2 on FAIL)')
    args = parser.parse_args()

    t0 = time.time()
    os.makedirs(DEBUG_DIR, exist_ok=True)
    os.makedirs(os.path.dirname(args.output), exist_ok=True)

    # ── Step 1: Find photos ─────────────────────────────────────────────
    print("\n=== Step 1: Finding photos ===")
    photo_paths = {}
    photo_images = {}
    for view in args.views:
        path = os.path.join(args.scan_dir, f'{view}.jpg')
        if not os.path.exists(path):
            path = os.path.join(args.scan_dir, f'{view}.png')
        if os.path.exists(path):
            img = cv2.imread(path)
            if img is not None:
                photo_paths[view] = path
                photo_images[view] = img
                print(f"  {view}: {path} ({img.shape[1]}x{img.shape[0]})")
            else:
                print(f"  {view}: UNREADABLE")
        else:
            print(f"  {view}: not found")

    if not photo_paths:
        print("ERROR: No photos found")
        sys.exit(1)

    # ── Step 2: DensePose inference ─────────────────────────────────────
    print("\n=== Step 2: DensePose inference ===")
    from core.densepose_infer import predict_iuv

    iuv_maps = {}
    for view, path in photo_paths.items():
        print(f"  Processing {view}...")
        iuv = predict_iuv(path, backend='torchscript')
        if iuv is not None:
            iuv_maps[view] = iuv
            body_pix = (iuv[:, :, 0] > 0).sum()
            total_pix = iuv.shape[0] * iuv.shape[1]
            parts = np.unique(iuv[:, :, 0])
            print(f"    Body: {body_pix}/{total_pix} ({100*body_pix/total_pix:.1f}%), parts: {len(parts)-1}")

            if args.debug:
                vis = np.zeros((*iuv.shape[:2], 3), dtype=np.uint8)
                for p in range(1, 25):
                    mask = iuv[:, :, 0] == p
                    vis[mask] = [int((p*37) % 255), int((p*73) % 255), int((p*113) % 255)]
                cv2.imwrite(os.path.join(DEBUG_DIR, f'iuv_{view}.png'), vis)
        else:
            print(f"    FAILED")

    if not iuv_maps:
        print("ERROR: DensePose failed for all images")
        sys.exit(1)

    # ── Step 3: Build body mesh ─────────────────────────────────────────
    print("\n=== Step 3: Building body mesh ===")
    from core.smpl_fitting import build_body_mesh

    mesh = build_body_mesh()
    verts = mesh['vertices']
    faces = mesh['faces']
    uvs = mesh.get('uvs')
    print(f"  {mesh['num_vertices']} verts, {mesh['num_faces']} faces")

    if uvs is None:
        from core.uv_unwrap import compute_uvs, DEFAULT_ATLAS
        uvs = compute_uvs(verts, mesh.get('body_part_ids'), DEFAULT_ATLAS)

    # ── Step 3b: Harmonize view colors (fix seam between front/back) ────
    print(f"\n=== Step 3b: LAB color harmonization (anchor=front) ===")

    def harmonize_to_anchor(source_bgr, anchor_bgr, iuv_src, iuv_anc):
        """Match source photo's color distribution to anchor in LAB space.
        Only uses body pixels (from DensePose) to compute statistics."""
        src_lab = cv2.cvtColor(source_bgr, cv2.COLOR_BGR2LAB).astype(np.float32)
        anc_lab = cv2.cvtColor(anchor_bgr, cv2.COLOR_BGR2LAB).astype(np.float32)

        # Use only body pixels for stats (DensePose part > 0)
        src_body = iuv_src[:, :, 0] > 0
        anc_body = iuv_anc[:, :, 0] > 0

        if src_body.sum() < 100 or anc_body.sum() < 100:
            return source_bgr  # not enough body pixels

        for ch in range(3):
            src_vals = src_lab[:, :, ch][src_body]
            anc_vals = anc_lab[:, :, ch][anc_body]
            src_mu, src_sigma = src_vals.mean(), max(src_vals.std(), 1e-3)
            anc_mu, anc_sigma = anc_vals.mean(), max(anc_vals.std(), 1e-3)
            src_lab[:, :, ch] = (src_lab[:, :, ch] - src_mu) * (anc_sigma / src_sigma) + anc_mu

        result = cv2.cvtColor(np.clip(src_lab, 0, 255).astype(np.uint8), cv2.COLOR_LAB2BGR)
        return result

    # Pass 1: Harmonize all views to front (global color balance)
    anchor_view = 'front'
    if anchor_view in photo_images and anchor_view in iuv_maps:
        anchor_img = photo_images[anchor_view]
        anchor_iuv = iuv_maps[anchor_view]
        for view in photo_images:
            if view == anchor_view:
                continue
            if view in iuv_maps:
                original = photo_images[view]
                harmonized = harmonize_to_anchor(original, anchor_img, iuv_maps[view], anchor_iuv)
                diff = np.abs(harmonized.astype(float) - original.astype(float)).mean()
                photo_images[view] = harmonized
                print(f"  {view} → anchor({anchor_view}): mean shift={diff:.1f}")

    # Pass 2: Harmonize left/right to back (fix side-back overlap seam)
    # After pass 1, all views approximate front's color. But left/right and back
    # still differ from each other locally. A second pass makes them agree better.
    if 'back' in photo_images and 'back' in iuv_maps:
        for side_view in ['left', 'right']:
            if side_view in photo_images and side_view in iuv_maps:
                original = photo_images[side_view]
                harmonized = harmonize_to_anchor(
                    original, photo_images['back'],
                    iuv_maps[side_view], iuv_maps['back']
                )
                diff = np.abs(harmonized.astype(float) - original.astype(float)).mean()
                # Blend 50/50: keep some of pass-1 correction, add pass-2
                photo_images[side_view] = cv2.addWeighted(harmonized, 0.5, original, 0.5, 0)
                print(f"  {side_view} → anchor(back): mean shift={diff:.1f} (50% blend)")

    # ── Step 4: Direct photo → mesh texture via KDTree NN matching ─────
    print(f"\n=== Step 4: KDTree NN texture bake (direct from photos) ===")
    from core.texture_bake import bake_from_photos_nn, build_seam_mask, smooth_seam
    from core.densepose_texture import inpaint_atlas

    # Build photo dict (only views with IUV data)
    photo_dict = {v: photo_images[v] for v in iuv_maps if v in photo_images}

    albedo, weight = bake_from_photos_nn(
        verts, faces, uvs,
        photo_dict, iuv_maps,
        texture_size=args.atlas
    )

    coverage = (weight > 0).sum() / (args.atlas * args.atlas) * 100
    print(f"  UV texture coverage: {coverage:.1f}%")

    # Inpaint uncovered regions
    albedo = inpaint_atlas(albedo, weight)

    # ── Step 4a: Smooth front/back seam in UV space ──
    print("\n=== Step 4a: Seam smoothing (Gaussian blend at front/back boundary) ===")
    seam_mask = build_seam_mask(verts, faces, uvs, texture_size=args.atlas)
    albedo = smooth_seam(albedo, seam_mask, blur_radius=31)
    if args.debug:
        seam_vis = (seam_mask * 255).astype(np.uint8)
        cv2.imwrite(os.path.join(DEBUG_DIR, 'seam_mask.png'), seam_vis)
        print(f"  Seam mask saved to {os.path.join(DEBUG_DIR, 'seam_mask.png')}")

    # ── Step 4b: Enhance texture contrast + brightness ──
    print("\n=== Step 4b: CLAHE contrast + brightness boost ===")
    # Convert to LAB, apply CLAHE to L channel, boost L, convert back
    lab = cv2.cvtColor(albedo, cv2.COLOR_BGR2LAB)
    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
    lab[:, :, 0] = clahe.apply(lab[:, :, 0])
    # Brightness boost: lift L channel by 20% (clamp at 255)
    l_float = lab[:, :, 0].astype(np.float32)
    l_float = np.clip(l_float * 1.20 + 10, 0, 255)
    lab[:, :, 0] = l_float.astype(np.uint8)
    albedo_enhanced = cv2.cvtColor(lab, cv2.COLOR_LAB2BGR)

    # Blend: 70% enhanced + 30% original (preserve skin tone, boost detail)
    albedo = cv2.addWeighted(albedo_enhanced, 0.7, albedo, 0.3, 0)
    mean_brightness = albedo.mean()
    print(f"  CLAHE + brightness boost → mean={mean_brightness:.0f}/255")

    # ── Step 5: PBR maps ────────────────────────────────────────────────
    print("\n=== Step 5: Generating PBR maps ===")
    from core.skin_texture import _generate_normal_map, _generate_roughness_map

    normal = _generate_normal_map(albedo, strength=1.0)
    roughness = _generate_roughness_map(albedo)
    print(f"  Albedo: {albedo.shape}, Normal: {normal.shape}, Roughness: {roughness.shape}")

    # AO from mesh
    ao = None
    try:
        from core.texture_factory import generate_ao_map
        ao = generate_ao_map(verts, faces, uvs, atlas_size=args.atlas)
        if ao is not None and ao.dtype != np.uint8:
            ao = (ao * 255).astype(np.uint8)
        print(f"  AO: {ao.shape}")
    except Exception as e:
        print(f"  AO skipped: {e}")

    # Save debug textures
    if args.debug:
        cv2.imwrite(os.path.join(DEBUG_DIR, 'albedo_nn.png'), albedo)
        cv2.imwrite(os.path.join(DEBUG_DIR, 'normal_nn.png'), normal)
        cv2.imwrite(os.path.join(DEBUG_DIR, 'roughness_nn.png'), roughness)
        if ao is not None:
            cv2.imwrite(os.path.join(DEBUG_DIR, 'ao_nn.png'), ao)

    # ── Step 6: Export GLB ──────────────────────────────────────────────
    print(f"\n=== Step 6: Exporting GLB ===")
    from core.mesh_reconstruction import export_glb

    export_glb(
        verts, faces, args.output,
        normals=True,
        uvs=uvs,
        texture_image=albedo,  # BGR — cv2.imencode handles BGR→RGB in PNG
        normal_map=normal,
        roughness_map=roughness,
        ao_map=ao,
    )
    size_mb = os.path.getsize(args.output) / 1024 / 1024
    print(f"  GLB: {args.output} ({size_mb:.1f} MB)")

    dt = time.time() - t0
    print(f"\n=== Done in {dt:.1f}s ===")
    print(f"  Texture coverage: {coverage:.1f}%")
    print(f"  Output: {args.output}")
    print(f"\n  View: http://192.168.100.16:8000/web_app/static/viewer3d/index.html?model=/api/mesh/skin_densepose.glb")

    # ── Step 7: Verify output quality ──
    if args.verify:
        from core.glb_inspector import score_glb
        result = score_glb(args.output)
        print(f"\n=== Verify: {result['verdict']} (score: {result['scores']['overall']}) ===")
        for issue in result['issues']:
            print(f"  ! {issue}")
        if result['suggestion'] != "Texture quality looks good.":
            print(f"  > {result['suggestion']}")
        if result['verdict'] == 'FAIL':
            sys.exit(2)  # exit code 2 = quality failure


if __name__ == '__main__':
    main()
