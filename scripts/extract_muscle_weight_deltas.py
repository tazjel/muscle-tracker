"""Extract muscle/weight vertex deltas from MPFB2 human via RNA properties.

MPFB2 stores macros as RNA props: MPFB_HUM_muscle, MPFB_HUM_weight.
After setting these, we must reapply targets and read via evaluated depsgraph.
"""
import bpy
import numpy as np
import json
import os
import traceback

PROJECT_ROOT = "C:/Users/MiEXCITE/Projects/gtd3d"
DELTAS_DIR = os.path.join(PROJECT_ROOT, "meshes", "shape_deltas")
BODY_VERTS = 13380  # body-only verts (before helpers)

def get_eval_verts(obj):
    """Read vertex positions from evaluated (deformed) mesh."""
    depsgraph = bpy.context.evaluated_depsgraph_get()
    obj_eval = obj.evaluated_get(depsgraph)
    mesh_eval = obj_eval.to_mesh()
    n = len(mesh_eval.vertices)
    co = np.empty(n * 3, dtype=np.float64)
    mesh_eval.vertices.foreach_get('co', co)
    obj_eval.to_mesh_clear()
    return co.reshape(-1, 3)

def set_macro_and_update(human, prop_name, value):
    """Set an MPFB2 macro RNA property and reapply targets."""
    human[prop_name] = value
    # Trigger MPFB2 to reapply macro details
    try:
        from bl_ext.user_default.mpfb.services.targetservice import TargetService
        TargetService.reapply_macro_details(human)
    except Exception as e:
        print(f"  reapply_macro_details failed: {e}")
    # Force depsgraph update
    bpy.context.view_layer.update()

try:
    # Clean scene and create human
    bpy.ops.object.select_all(action='SELECT')
    bpy.ops.object.delete()
    bpy.ops.mpfb.create_human()

    human = None
    for obj in bpy.data.objects:
        if obj.type == 'MESH' and len(obj.data.vertices) > 5000:
            human = obj
            break

    if not human:
        raise RuntimeError("No MPFB2 human found")

    total_verts = len(human.data.vertices)
    print(f"HUMAN: {human.name}, {total_verts} verts (body={BODY_VERTS})")

    # Verify RNA props exist
    muscle_val = human.get('MPFB_HUM_muscle', None)
    weight_val = human.get('MPFB_HUM_weight', None)
    print(f"CURRENT: muscle={muscle_val}, weight={weight_val}")

    # --- BASELINE: muscle=0.5, weight=0.5 (defaults) ---
    set_macro_and_update(human, 'MPFB_HUM_muscle', 0.5)
    set_macro_and_update(human, 'MPFB_HUM_weight', 0.5)
    baseline = get_eval_verts(human)[:BODY_VERTS]
    print(f"BASELINE: {baseline.shape}, range=[{baseline.min():.4f}, {baseline.max():.4f}]")

    # --- MUSCLE MAX: muscle=1.0, weight=0.5 ---
    set_macro_and_update(human, 'MPFB_HUM_muscle', 1.0)
    set_macro_and_update(human, 'MPFB_HUM_weight', 0.5)
    muscle_max = get_eval_verts(human)[:BODY_VERTS]
    muscle_delta = muscle_max - baseline
    muscle_maxd = np.abs(muscle_delta).max()
    print(f"MUSCLE_DELTA: max_abs={muscle_maxd:.6f}m, nonzero={np.count_nonzero(np.abs(muscle_delta).max(axis=1) > 1e-6)}")

    # --- WEIGHT MAX: muscle=0.5, weight=1.0 ---
    set_macro_and_update(human, 'MPFB_HUM_muscle', 0.5)
    set_macro_and_update(human, 'MPFB_HUM_weight', 1.0)
    weight_max = get_eval_verts(human)[:BODY_VERTS]
    weight_delta = weight_max - baseline
    weight_maxd = np.abs(weight_delta).max()
    print(f"WEIGHT_DELTA: max_abs={weight_maxd:.6f}m, nonzero={np.count_nonzero(np.abs(weight_delta).max(axis=1) > 1e-6)}")

    # Reset to baseline
    set_macro_and_update(human, 'MPFB_HUM_muscle', 0.5)
    set_macro_and_update(human, 'MPFB_HUM_weight', 0.5)

    # Save deltas if significant
    os.makedirs(DELTAS_DIR, exist_ok=True)
    index_path = os.path.join(DELTAS_DIR, "index.json")

    if os.path.exists(index_path):
        with open(index_path) as f:
            index = json.load(f)
    else:
        index = {}

    saved = 0
    if muscle_maxd > 1e-5:
        npy_name = "macro_muscle.npy"
        np.save(os.path.join(DELTAS_DIR, npy_name), muscle_delta.astype(np.float32))
        index["macro_muscle"] = {
            "file": npy_name,
            "baked_value": 0.5,
            "category": "muscle"
        }
        saved += 1
        print(f"SAVED: {npy_name}")

    if weight_maxd > 1e-5:
        npy_name = "macro_weight.npy"
        np.save(os.path.join(DELTAS_DIR, npy_name), weight_delta.astype(np.float32))
        index["macro_weight"] = {
            "file": npy_name,
            "baked_value": 0.5,
            "category": "weight"
        }
        saved += 1
        print(f"SAVED: {npy_name}")

    with open(index_path, 'w') as f:
        json.dump(index, f, indent=2)

    print(f"DONE: saved {saved} macro deltas, index has {len(index)} entries")

except Exception as e:
    print(f"ERROR: {e}")
    traceback.print_exc()
