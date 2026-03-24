"""Extract muscle/weight deltas using HumanObjectProperties + reapply_macro_details.
Uses full 0→1 range for maximum delta magnitude."""
import bpy
import numpy as np
import json
import os
import traceback

PROJECT_ROOT = "C:/Users/MiEXCITE/Projects/gtd3d"
DELTAS_DIR = os.path.join(PROJECT_ROOT, "meshes", "shape_deltas")
BODY_VERTS = 13380

def get_eval_verts(obj):
    depsgraph = bpy.context.evaluated_depsgraph_get()
    obj_eval = obj.evaluated_get(depsgraph)
    mesh_eval = obj_eval.to_mesh()
    n = len(mesh_eval.vertices)
    co = np.empty(n * 3, dtype=np.float64)
    mesh_eval.vertices.foreach_get('co', co)
    obj_eval.to_mesh_clear()
    return co.reshape(-1, 3)[:BODY_VERTS]

def set_macro(human, hop, ts, name, value):
    hop.set_value(name, value, entity_reference=human)
    ts.reapply_macro_details(human)
    bpy.context.view_layer.update()

try:
    bpy.ops.object.select_all(action='SELECT')
    bpy.ops.object.delete()
    bpy.ops.mpfb.create_human()

    human = None
    for obj in bpy.data.objects:
        if obj.type == 'MESH' and len(obj.data.vertices) > 5000:
            human = obj
            break

    print(f"HUMAN: {human.name}, {len(human.data.vertices)} verts")

    from bl_ext.user_default.mpfb.entities.objectproperties import HumanObjectProperties as HOP
    from bl_ext.user_default.mpfb.services.targetservice import TargetService as TS

    # Print current values
    for k in ['muscle', 'weight', 'gender', 'height', 'african', 'asian', 'caucasian']:
        print(f"  {k}: {HOP.get_value(k, entity_reference=human)}")

    # --- BASELINE at muscle=0.5, weight=0.5 ---
    set_macro(human, HOP, TS, 'muscle', 0.5)
    set_macro(human, HOP, TS, 'weight', 0.5)
    baseline = get_eval_verts(human)
    print(f"BASELINE: shape={baseline.shape}")

    # --- MUSCLE: full range 0.0 → 1.0 ---
    # muscle=0.0 (min)
    set_macro(human, HOP, TS, 'muscle', 0.0)
    muscle_min = get_eval_verts(human)

    # muscle=1.0 (max)
    set_macro(human, HOP, TS, 'muscle', 1.0)
    muscle_max = get_eval_verts(human)

    # Delta per unit: (max - min) represents full 0→1 range
    muscle_delta = muscle_max - muscle_min
    muscle_half = muscle_max - baseline  # 0.5→1.0 half
    print(f"MUSCLE_FULL: max={np.abs(muscle_delta).max():.6f}m, nonzero={np.count_nonzero(np.abs(muscle_delta).max(axis=1) > 1e-5)}")
    print(f"MUSCLE_HALF: max={np.abs(muscle_half).max():.6f}m")

    # Reset muscle
    set_macro(human, HOP, TS, 'muscle', 0.5)

    # --- WEIGHT: full range 0.0 → 1.0 ---
    set_macro(human, HOP, TS, 'weight', 0.0)
    weight_min = get_eval_verts(human)

    set_macro(human, HOP, TS, 'weight', 1.0)
    weight_max = get_eval_verts(human)

    weight_delta = weight_max - weight_min
    weight_half = weight_max - baseline
    print(f"WEIGHT_FULL: max={np.abs(weight_delta).max():.6f}m, nonzero={np.count_nonzero(np.abs(weight_delta).max(axis=1) > 1e-5)}")
    print(f"WEIGHT_HALF: max={np.abs(weight_half).max():.6f}m")

    # Reset
    set_macro(human, HOP, TS, 'weight', 0.5)

    # --- Also try reapply_all_details instead ---
    set_macro(human, HOP, TS, 'muscle', 0.5)
    set_macro(human, HOP, TS, 'weight', 0.5)
    baseline2 = get_eval_verts(human)

    HOP.set_value('muscle', 1.0, entity_reference=human)
    TS.reapply_all_details(human)
    bpy.context.view_layer.update()
    muscle_all = get_eval_verts(human)
    print(f"MUSCLE_REAPPLY_ALL: max={np.abs(muscle_all - baseline2).max():.6f}m")

    # --- SAVE deltas (using full-range delta, baked_value=0 means slider 0→1 maps to min→max) ---
    os.makedirs(DELTAS_DIR, exist_ok=True)
    index_path = os.path.join(DELTAS_DIR, "index.json")
    if os.path.exists(index_path):
        with open(index_path) as f:
            index = json.load(f)
    else:
        index = {}

    saved = 0

    # Save muscle delta (full range, baked at 0.5 baseline)
    if np.abs(muscle_delta).max() > 1e-5:
        npy = "macro_muscle.npy"
        np.save(os.path.join(DELTAS_DIR, npy), muscle_delta.astype(np.float32))
        index["macro_muscle"] = {"file": npy, "baked_value": 0.0, "category": "muscle"}
        saved += 1
        print(f"SAVED: {npy} ({muscle_delta.shape})")

    # Save weight delta (full range, baked at 0.5 baseline)
    if np.abs(weight_delta).max() > 1e-5:
        npy = "macro_weight.npy"
        np.save(os.path.join(DELTAS_DIR, npy), weight_delta.astype(np.float32))
        index["macro_weight"] = {"file": npy, "baked_value": 0.0, "category": "weight"}
        saved += 1
        print(f"SAVED: {npy} ({weight_delta.shape})")

    with open(index_path, 'w') as f:
        json.dump(index, f, indent=2)

    print(f"DONE: {saved} new deltas, {len(index)} total in index")

except Exception as e:
    print(f"ERROR: {e}")
    traceback.print_exc()
