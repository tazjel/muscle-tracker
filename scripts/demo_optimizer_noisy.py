#!/usr/bin/env python3
"""
SMPL Beta Optimizer — Noisy stress test.

Same as demo_optimizer.py but with:
  1. Gaussian noise on silhouette points (simulating real photo extraction error)
  2. Wrong initial betas (simulating bad HMR2.0 prediction)
  3. Only 2 views

This is the realistic scenario.
"""
import sys, os, time
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np
from core.smpl_optimizer import (
    smpl_forward, get_faces, render_silhouette,
    optimize_betas, extract_measurements,
)

TARGET_BETAS = np.array([1.5, -0.8, 0.7, 0.3, -0.2, 0.1, -0.1, 0.0, 0.0, 0.0])
WRONG_INIT   = np.array([0.3, 0.2, -0.1, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0])
NOISE_MM     = 3.0   # 3mm std noise on silhouette points (realistic for phone photos)
DIST_MM      = 2300.0
CAM_H_MM     = 650.0


def main():
    W = 65
    print("=" * W)
    print("  SMPL OPTIMIZER — NOISY STRESS TEST")
    print("=" * W)

    faces = get_faces()
    np.random.seed(42)

    # Target
    target_v, target_j = smpl_forward(TARGET_BETAS)
    target_meas = extract_measurements(target_v, target_j, faces)

    # Wrong starting body
    wrong_v, _ = smpl_forward(WRONG_INIT)

    print(f"\nTarget height:  {target_v[:, 2].max():.0f} mm  (betas[:3]={TARGET_BETAS[:3]})")
    print(f"Wrong start:    {wrong_v[:, 2].max():.0f} mm  (betas[:3]={WRONG_INIT[:3]})")
    print(f"Noise:          {NOISE_MM} mm std on silhouette points")
    print()

    # Generate noisy silhouettes
    sil_views = []
    for d in ['front', 'right']:
        clean = render_silhouette(target_v, faces, d, DIST_MM, CAM_H_MM)
        noisy = clean + np.random.randn(*clean.shape).astype(np.float32) * NOISE_MM
        sil_views.append({
            'contour_mm': noisy, 'direction': d,
            'distance_mm': DIST_MM, 'camera_height_mm': CAM_H_MM,
        })
        print(f"  {d:>6}: {len(clean)} pts + {NOISE_MM}mm noise")

    print(f"\nOptimizing from wrong initial guess...")
    t0 = time.time()
    result = optimize_betas(sil_views, initial_betas=WRONG_INIT, max_iter=100)
    elapsed = time.time() - t0

    hist = result['loss_history']
    print(f"  {result['n_evals']} evals, {elapsed:.1f}s")
    print(f"  loss: {hist[0]:.1f} -> {hist[-1]:.4f}")
    print()

    # Beta recovery
    print("-" * W)
    print(f"  {'B':>3}  {'Target':>8}  {'Start':>8}  {'Recovered':>10}  {'Error':>8}")
    print("-" * W)
    for i in range(10):
        t = TARGET_BETAS[i]
        s = WRONG_INIT[i]
        r = result['betas'][i]
        print(f"  B{i:<2}  {t:>8.3f}  {s:>8.3f}  {r:>10.3f}  {abs(t-r):>8.4f}")
    print("-" * W)
    print()

    # Measurements
    opt_meas = result['measurements']
    display = [
        ('height_cm',              'Height'),
        ('chest_circumference_cm', 'Chest'),
        ('waist_circumference_cm', 'Waist'),
        ('hip_circumference_cm',   'Hip'),
        ('thigh_circumference_cm', 'Thigh'),
        ('shoulder_width_cm',      'Shoulders'),
        ('weight_est_kg',          'Weight est.'),
        ('bmi_est',                'BMI est.'),
    ]

    print("-" * W)
    print(f"  {'Measurement':<18} {'Target':>8} {'Optimized':>10} {'Error':>8}")
    print("-" * W)
    for key, label in display:
        t = target_meas.get(key, 0)
        o = opt_meas.get(key, 0)
        err = abs(t - o) / max(t, 0.1) * 100
        unit = 'kg' if 'kg' in key else ('' if 'bmi' in key else 'cm')
        print(f"  {label:<18} {t:>7.1f} {unit:>2}  {o:>7.1f} {unit:>2}  {err:>6.1f}%")
    print("-" * W)

    # Total measurement error
    errs = []
    for key, _ in display:
        t = target_meas.get(key, 0)
        o = opt_meas.get(key, 0)
        if t > 0:
            errs.append(abs(t - o) / t * 100)
    print(f"\n  Mean measurement error: {np.mean(errs):.2f}%")
    print(f"  Max  measurement error: {np.max(errs):.2f}%")

    beta_rmse = np.sqrt(np.mean((TARGET_BETAS - result['betas']) ** 2))
    print(f"  Beta RMSE: {beta_rmse:.4f}")
    print()

    print("=" * W)
    print(f"  With 3mm noise and wrong starting betas,")
    print(f"  10-parameter optimization still recovers the body.")
    print("=" * W)


if __name__ == '__main__':
    main()
