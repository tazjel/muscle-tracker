#!/usr/bin/env python3
"""
SMPL Beta Optimizer — Proof of Concept

Proves that optimizing 10 SMPL shape parameters recovers a full body
from just 2 silhouettes, with accurate measurements.

No photos, no GPU, no server needed. Runs in ~3 seconds.

Usage:
    python scripts/demo_optimizer.py
"""
import sys, os, time
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np
from core.smpl_optimizer import (
    smpl_forward, get_faces, render_silhouette,
    optimize_betas, extract_measurements,
)

# -- Config --------------------------------------------------------------------

# Target body: tall, lean, distinct proportions
TARGET_BETAS = np.array([1.5, -0.8, 0.7, 0.3, -0.2, 0.0, 0.0, 0.0, 0.0, 0.0])

# Camera setup (matches dual-capture rig)
DIST_MM = 2300.0
CAM_H_MM = 650.0

# Views to use for fitting
VIEWS = ['front', 'right']


def main():
    W = 65  # output width

    print("=" * W)
    print("  SMPL BETA OPTIMIZER — PROOF OF CONCEPT")
    print("=" * W)
    print()

    faces = get_faces()

    # -- Target body -----------------------------------------------------------
    target_verts, target_joints = smpl_forward(TARGET_BETAS)
    target_meas = extract_measurements(target_verts, target_joints, faces)

    print(f"TARGET:  Custom body (betas[0:3] = {TARGET_BETAS[:3]})")
    print(f"         Height = {target_verts[:, 2].max():.0f} mm")
    print(f"START:   Average body (betas = all zeros)")
    print(f"VIEWS:   {' + '.join(VIEWS)} (synthetic silhouettes)")
    print()

    # -- Generate synthetic silhouettes ----------------------------------------
    sil_views = []
    for direction in VIEWS:
        contour = render_silhouette(target_verts, faces, direction, DIST_MM, CAM_H_MM)
        sil_views.append({
            'contour_mm':       contour,
            'direction':        direction,
            'distance_mm':      DIST_MM,
            'camera_height_mm': CAM_H_MM,
        })
        print(f"  {direction:>6} silhouette: {len(contour):>4} boundary points")

    print()
    print(f"Optimizing 10 body-shape parameters...")

    # -- Run optimizer ---------------------------------------------------------
    t0 = time.time()
    result = optimize_betas(sil_views, initial_betas=np.zeros(10), max_iter=100)
    elapsed = time.time() - t0

    hist = result['loss_history']
    print(f"  converged: {result['converged']}  "
          f"({result['n_evals']} evaluations, {elapsed:.1f}s)")
    print(f"  loss: {hist[0]:.1f} -> {hist[-1]:.4f}")
    print()

    # -- Beta recovery ---------------------------------------------------------
    print("-" * W)
    print(f"  {'B':>3}  {'Target':>8}  {'Recovered':>10}  {'Abs Error':>10}")
    print("-" * W)
    for i in range(10):
        t = TARGET_BETAS[i]
        r = result['betas'][i]
        print(f"  B{i:<2}  {t:>8.3f}  {r:>10.3f}  {abs(t - r):>10.4f}")
    print("-" * W)
    print()

    # -- Measurement comparison ------------------------------------------------
    opt_meas = result['measurements']

    # Keys to display and their labels
    display = [
        ('height_cm',                'Height'),
        ('chest_circumference_cm',   'Chest circ.'),
        ('waist_circumference_cm',   'Waist circ.'),
        ('hip_circumference_cm',     'Hip circ.'),
        ('neck_circumference_cm',    'Neck circ.'),
        ('shoulder_width_cm',        'Shoulder width'),
        ('torso_length_cm',          'Torso length'),
        ('arm_length_cm',            'Arm length'),
        ('floor_to_knee_cm',         'Floor to knee'),
        ('thigh_circumference_cm',   'Thigh circ.'),
        ('calf_circumference_cm',    'Calf circ.'),
        ('bicep_circumference_cm',   'Bicep circ.'),
        ('forearm_circumference_cm', 'Forearm circ.'),
        ('weight_est_kg',            'Weight (est.)'),
        ('bmi_est',                  'BMI (est.)'),
    ]

    print("-" * W)
    print(f"  {'Measurement':<22} {'Target':>8} {'Optimized':>10} {'Error':>8}")
    print("-" * W)
    for key, label in display:
        t = target_meas.get(key, 0)
        o = opt_meas.get(key, 0)
        if t > 0:
            err_pct = abs(t - o) / t * 100
            err_str = f"{err_pct:.1f}%"
        else:
            err_str = "-"
        unit = 'kg' if 'kg' in key else ('' if 'bmi' in key else 'cm')
        print(f"  {label:<22} {t:>7.1f} {unit:>2}  {o:>7.1f} {unit:>2}  {err_str:>7}")
    print("-" * W)
    print()

    # -- Export GLBs -----------------------------------------------------------
    try:
        import trimesh
        os.makedirs('meshes', exist_ok=True)

        target_mesh = trimesh.Trimesh(
            vertices=target_verts / 1000.0, faces=faces, process=False)
        target_mesh.export('meshes/optimizer_target.glb')

        opt_mesh = trimesh.Trimesh(
            vertices=result['vertices'] / 1000.0, faces=faces, process=False)
        opt_mesh.export('meshes/optimizer_result.glb')

        avg_verts, _ = smpl_forward(np.zeros(10))
        avg_mesh = trimesh.Trimesh(
            vertices=avg_verts / 1000.0, faces=faces, process=False)
        avg_mesh.export('meshes/optimizer_average.glb')

        print("Output files:")
        print("  meshes/optimizer_target.glb    ground truth body")
        print("  meshes/optimizer_result.glb    recovered from 2 silhouettes")
        print("  meshes/optimizer_average.glb   average body (starting point)")
    except ImportError:
        print("(trimesh not installed - GLB export skipped)")

    # -- Matplotlib visual (optional) ------------------------------------------
    try:
        import matplotlib
        matplotlib.use('Agg')
        import matplotlib.pyplot as plt

        avg_verts, _ = smpl_forward(np.zeros(10))
        fig, axes = plt.subplots(1, len(VIEWS), figsize=(7 * len(VIEWS), 9))
        if len(VIEWS) == 1:
            axes = [axes]

        for idx, direction in enumerate(VIEWS):
            ax = axes[idx]
            target_sil = render_silhouette(target_verts, faces, direction, DIST_MM, CAM_H_MM)
            avg_sil    = render_silhouette(avg_verts, faces, direction, DIST_MM, CAM_H_MM)
            opt_sil    = render_silhouette(result['vertices'], faces, direction, DIST_MM, CAM_H_MM)

            ax.plot(avg_sil[:, 0], -avg_sil[:, 1],
                    'r--', alpha=0.4, lw=1, label='Average (start)')
            ax.plot(target_sil[:, 0], -target_sil[:, 1],
                    'g-', lw=2.0, label='Target (truth)')
            ax.plot(opt_sil[:, 0], -opt_sil[:, 1],
                    'b--', lw=1.5, label='Optimized')

            ax.set_title(f'{direction.title()} View', fontsize=14)
            ax.set_aspect('equal')
            ax.legend(fontsize=11, loc='lower right')
            ax.grid(True, alpha=0.2)

        fig.suptitle(
            '10 parameters recover full body shape from 2 silhouettes',
            fontsize=13, fontweight='bold', y=0.98)
        plt.tight_layout(rect=[0, 0, 1, 0.96])
        plt.savefig('optimizer_proof.png', dpi=150, bbox_inches='tight')
        print(f"  optimizer_proof.png            visual comparison")
    except ImportError:
        print("  (matplotlib not available - visual skipped)")
    except Exception as e:
        print(f"  (visual failed: {e})")

    # -- Summary ---------------------------------------------------------------
    print()
    print("=" * W)
    print("  Old: silhouette_matcher.py")
    print(f"    Parameters:   20,670 (free-form vertices)")
    print(f"    Constraints:  none")
    print(f"    Measurements: not extractable")
    print()
    print("  New: smpl_optimizer.py")
    print(f"    Parameters:   10 (SMPL betas)")
    print(f"    Constraints:  always anatomically valid")
    print(f"    Measurements: {len(opt_meas)} extracted from mesh geometry")
    print(f"    Time:         {elapsed:.1f}s")
    print("=" * W)


if __name__ == '__main__':
    main()
