#!/usr/bin/env python3
"""
Fit SMPL body to Ahmed's real tape measurements, export GLB + measurement data
for the interactive 3D measurement viewer.
"""
import sys, os, json, time
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np
from core.smpl_optimizer import optimize_from_profile, smpl_forward, get_faces

# Ahmed's real measurements from DEFAULT_PROFILE
MY_PROFILE = {
    'height_cm':                168,
    'weight_kg':                63,
    'floor_to_knee_cm':         52,
    'torso_length_cm':          50,
    'shoulder_width_cm':        37,
    'arm_length_cm':            80,
    'chest_circumference_cm':   97,
    'waist_circumference_cm':   90,
    'hip_circumference_cm':     92,
    'neck_circumference_cm':    35,
    'thigh_circumference_cm':   53,
    'bicep_circumference_cm':   32,
}


def main():
    print("=" * 60)
    print("  FITTING SMPL TO YOUR BODY MEASUREMENTS")
    print("=" * 60)
    print()
    print(f"  Height: {MY_PROFILE['height_cm']} cm")
    print(f"  Weight: {MY_PROFILE['weight_kg']} kg")
    print(f"  Chest:  {MY_PROFILE['chest_circumference_cm']} cm")
    print(f"  Waist:  {MY_PROFILE['waist_circumference_cm']} cm")
    print()

    t0 = time.time()
    result = optimize_from_profile(MY_PROFILE)
    elapsed = time.time() - t0

    hist = result['loss_history']
    print(f"  Converged: {result['converged']} ({result['n_evals']} evals, {elapsed:.1f}s)")
    print(f"  Loss: {hist[0]:.4f} -> {hist[-1]:.6f}")
    print(f"  Betas: {np.round(result['betas'][:5], 3)}")
    print()

    # Compare measurements
    meas = result['measurements']
    print("-" * 60)
    print(f"  {'Measurement':<22} {'Target':>8} {'SMPL Fit':>9} {'Diff':>8}")
    print("-" * 60)
    for key, label in [
        ('height_cm',              'Height'),
        ('chest_circumference_cm', 'Chest'),
        ('waist_circumference_cm', 'Waist'),
        ('hip_circumference_cm',   'Hip'),
        ('neck_circumference_cm',  'Neck'),
        ('shoulder_width_cm',      'Shoulders'),
        ('torso_length_cm',        'Torso'),
        ('arm_length_cm',          'Arms'),
        ('floor_to_knee_cm',       'Floor→Knee'),
        ('thigh_circumference_cm', 'Thigh'),
        ('calf_circumference_cm',  'Calf'),
        ('bicep_circumference_cm', 'Bicep'),
        ('weight_est_kg',          'Weight est.'),
        ('bmi_est',                'BMI est.'),
    ]:
        target = MY_PROFILE.get(key, None)
        fitted = meas.get(key, 0)
        unit = 'kg' if 'kg' in key else ('' if 'bmi' in key else 'cm')
        if target is not None:
            diff = fitted - target
            print(f"  {label:<22} {target:>7.1f} {unit:>2}  {fitted:>7.1f} {unit:>2}  {diff:>+7.1f}")
        else:
            print(f"  {label:<22} {'—':>10}  {fitted:>7.1f} {unit:>2}")
    print("-" * 60)
    print()

    # Export GLB
    import trimesh
    os.makedirs('web_app/static/meshes', exist_ok=True)

    mesh = trimesh.Trimesh(
        vertices=result['vertices'] / 1000.0,
        faces=result['faces'], process=False)
    mesh.export('web_app/static/meshes/my_body.glb')

    # Also export the average body for comparison
    avg_v, _ = smpl_forward(np.zeros(10))
    avg_mesh = trimesh.Trimesh(
        vertices=avg_v / 1000.0, faces=result['faces'], process=False)
    avg_mesh.export('web_app/static/meshes/avg_body.glb')

    # Export measurement data as JSON for the viewer
    viewer_data = {
        'profile': {k: v for k, v in MY_PROFILE.items()},
        'fitted': meas,
        'rings': result['rings'],
        'betas': [round(float(b), 4) for b in result['betas']],
        'height_m': round(float(result['vertices'][:, 2].max()) / 1000.0, 4),
    }
    with open('web_app/static/meshes/measurement_data.json', 'w') as f:
        json.dump(viewer_data, f, indent=2)

    print("Output:")
    print("  web_app/static/meshes/my_body.glb")
    print("  web_app/static/meshes/avg_body.glb")
    print("  web_app/static/meshes/measurement_data.json")
    print()

    url = "http://192.168.100.16:8000/web_app/static/viewer3d/measurement_viewer.html"
    print(f"Open: {url}")


if __name__ == '__main__':
    main()
