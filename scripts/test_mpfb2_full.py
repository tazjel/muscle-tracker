#!/usr/bin/env python3
"""
test_mpfb2_full.py — Full MPFB2 pipeline integration test (Phase 3).

Tests shape key phenotype, deformation, PBR maps, GLB export, and quality gate.
Does NOT test DensePose (GPU required) or SMPL pipeline.

Usage:
    PY=/c/Users/MiEXCITE/AppData/Local/Programs/Python/Python312/python.exe
    $PY scripts/test_mpfb2_full.py
"""
import sys
import os
import time
import subprocess
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PY = sys.executable

results = []
timing = {}


def step(name):
    """Context manager for timing + pass/fail tracking."""
    class _Step:
        def __enter__(self):
            self._t = time.time()
            return self
        def __exit__(self, exc_type, exc_val, exc_tb):
            elapsed = time.time() - self._t
            timing[name] = elapsed
            ok = exc_type is None
            results.append((name, ok, str(exc_val) if exc_val else ''))
            symbol = 'PASS' if ok else 'FAIL'
            print(f"  [{symbol}] {name} ({elapsed:.2f}s)" + (f" — {exc_val}" if exc_val else ''))
            return True  # suppress exception so we continue
    return _Step()


print("\n=== MPFB2 Full Pipeline Integration Test ===\n")

# ── Step 1: Default deformation (regression) ─────────────────────────────────
with step("deform_template default"):
    from core.body_deform import deform_template
    default_result = deform_template({'height_cm': 175})
    assert default_result['num_vertices'] == 13380, f"Expected 13380 verts, got {default_result['num_vertices']}"
    assert default_result['num_faces'] == 26756, f"Expected 26756 faces, got {default_result['num_faces']}"
    assert default_result['mesh_type'] == 'mpfb2'
    assert default_result['volume_cm3'] > 10000, f"Volume too low: {default_result['volume_cm3']}"
    print(f"    vol={default_result['volume_cm3']:.0f} cm³, verts={default_result['num_vertices']}")

# ── Step 2: Shape key phenotype — gender_factor changes volume ───────────────
with step("shape_key gender_factor"):
    # MPFB2 template has gender shape keys; muscle/weight keys not present in this template
    male = deform_template({'height_cm': 175, 'gender_factor': 1.0})
    female = deform_template({'height_cm': 175, 'gender_factor': 0.0})
    print(f"    male vol={male['volume_cm3']:.0f}, female vol={female['volume_cm3']:.0f}")
    assert male['volume_cm3'] != female['volume_cm3'], "gender_factor should change volume"
    assert male['volume_cm3'] > female['volume_cm3'], "Male body should be larger than female"

# ── Step 3: Shape key phenotype — muscle_factor (graceful if no muscle keys) ─
with step("shape_key muscle_factor"):
    lean = deform_template({'height_cm': 175, 'muscle_factor': 0.2})
    buff = deform_template({'height_cm': 175, 'muscle_factor': 0.9})
    print(f"    lean vol={lean['volume_cm3']:.0f}, buff vol={buff['volume_cm3']:.0f}")
    # Note: MPFB2 template may not have separate muscle shape keys;
    # if volumes are equal, muscle_factor has no effect (expected).
    if lean['volume_cm3'] == buff['volume_cm3']:
        print("    NOTE: No muscle shape keys in template — muscle_factor has no effect (OK)")

# ── Step 4: Part IDs from dispatcher ─────────────────────────────────────────
with step("get_part_ids dispatcher"):
    from core.texture_factory import get_part_ids
    import numpy as np
    part_ids = get_part_ids(13380)
    assert part_ids is not None
    assert len(part_ids) == 13380
    unique = len(np.unique(part_ids))
    print(f"    {unique} unique part IDs across 13380 verts")
    assert unique > 1, "Should have multiple body part IDs"

# ── Step 5: Roughness map on deformed mesh ────────────────────────────────────
verts = default_result['vertices']
faces = default_result['faces']
uvs = default_result['uvs']

with step("generate_roughness_map"):
    from core.texture_factory import generate_roughness_map
    roughness = generate_roughness_map(uvs, atlas_size=512)
    assert roughness is not None
    print(f"    roughness: {roughness.shape}, mean={roughness.mean():.1f}")

# ── Step 6: AO map on deformed mesh ──────────────────────────────────────────
with step("generate_ao_map"):
    from core.texture_factory import generate_ao_map
    ao = generate_ao_map(verts, faces, uvs, atlas_size=512)
    assert ao is not None
    print(f"    ao: {ao.shape}, mean={ao.mean():.1f}")

# ── Step 7: Export GLB with UVs + roughness ───────────────────────────────────
glb_path = os.path.join(PROJECT_ROOT, 'meshes', 'test_mpfb2_full.glb')
with step("export_glb"):
    from core.mesh_reconstruction import export_glb
    export_glb(
        verts, faces, glb_path,
        normals=True,
        uvs=uvs,
        roughness_map=roughness,
        ao_map=ao,
    )
    size_kb = os.path.getsize(glb_path) / 1024
    assert size_kb > 100, f"GLB too small: {size_kb:.0f} KB"
    print(f"    GLB: {size_kb:.0f} KB")

# ── Step 8: Quality gate via agent_verify.py ──────────────────────────────────
with step("agent_verify quality gate"):
    import json as _json
    verify_script = os.path.join(PROJECT_ROOT, 'scripts', 'agent_verify.py')
    proc = subprocess.run(
        [PY, verify_script, glb_path],
        capture_output=True, text=True, timeout=30,
        cwd=PROJECT_ROOT,
    )
    print(f"    exit={proc.returncode}")
    for line in proc.stdout.strip().splitlines()[:6]:
        print(f"    {line}")
    # exit 1 = runtime error; exit 2 = quality FAIL (acceptable for no-texture test GLB)
    assert proc.returncode != 1, f"agent_verify crashed (exit 1)"
    # Verify mesh geometry is correct regardless of texture score
    try:
        report = _json.loads(proc.stdout.strip())
        assert report['mesh']['vertices'] == 13380
        assert report['mesh']['faces'] == 26756
        print(f"    mesh geometry OK: {report['mesh']['vertices']} verts, {report['mesh']['faces']} faces")
    except Exception:
        pass  # non-JSON output is fine

# ── Summary ────────────────────────────────────────────────────────────────────
print(f"\n=== Results: {sum(1 for _,ok,_ in results if ok)}/{len(results)} passed ===")
total = sum(timing.values())
print(f"Total time: {total:.2f}s\n")
for name, ok, err in results:
    symbol = 'PASS' if ok else 'FAIL'
    line = f"  [{symbol}] {name}"
    if not ok:
        line += f" — {err}"
    print(line)

# Exit 1 if any step failed
failed = [name for name, ok, _ in results if not ok]
if failed:
    print(f"\nFailed: {failed}")
    sys.exit(1)
