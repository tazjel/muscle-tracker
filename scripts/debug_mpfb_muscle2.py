"""Debug: Find correct way to set MPFB2 muscle/weight and see mesh change."""
import bpy
import numpy as np
import traceback

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

try:
    bpy.ops.object.select_all(action='SELECT')
    bpy.ops.object.delete()
    bpy.ops.mpfb.create_human()

    human = None
    for obj in bpy.data.objects:
        if obj.type == 'MESH' and len(obj.data.vertices) > 5000:
            human = obj
            break

    print(f"HUMAN: {human.name}")

    # Try accessing via RNA property directly (not dict-style)
    print(f"RNA_MUSCLE: {human.MPFB_HUM_muscle}")
    print(f"RNA_WEIGHT: {human.MPFB_HUM_weight}")
    print(f"RNA_GENDER: {human.MPFB_HUM_gender}")

    # Get baseline
    baseline = get_eval_verts(human)

    # Try setting via RNA attribute
    human.MPFB_HUM_muscle = 1.0
    print(f"SET_MUSCLE: {human.MPFB_HUM_muscle}")

    # Try reapply via TargetService
    from bl_ext.user_default.mpfb.services.targetservice import TargetService
    print(f"TS_METHODS: {[m for m in dir(TargetService) if not m.startswith('_') and 'macro' in m.lower() or 'reapply' in m.lower() or 'apply' in m.lower()]}")

    TargetService.reapply_macro_details(human)
    bpy.context.view_layer.update()

    after_muscle = get_eval_verts(human)
    delta = after_muscle - baseline
    print(f"DELTA_AFTER_REAPPLY: max={np.abs(delta).max():.6f}")

    # Try via HumanService
    from bl_ext.user_default.mpfb.services.humanservice import HumanService
    print(f"HS_METHODS: {[m for m in dir(HumanService) if not m.startswith('_')]}")

    # Try set_character_skin or similar
    from bl_ext.user_default.mpfb.entities.objectproperties import GeneralObjectProperties
    print(f"GOP_KEYS: {GeneralObjectProperties.get_keys()}")

    # Try HumanObjectProperties
    try:
        from bl_ext.user_default.mpfb.entities.objectproperties import HumanObjectProperties
        print(f"HOP_KEYS: {HumanObjectProperties.get_keys()}")
        print(f"HOP_MUSCLE: {HumanObjectProperties.get_value('muscle', entity_reference=human)}")
    except Exception as e:
        print(f"HOP_ERR: {e}")

    # Try setting via HumanObjectProperties
    try:
        HumanObjectProperties.set_value('muscle', 1.0, entity_reference=human)
        print(f"HOP_SET_MUSCLE: {HumanObjectProperties.get_value('muscle', entity_reference=human)}")
        TargetService.reapply_macro_details(human)
        bpy.context.view_layer.update()
        after_hop = get_eval_verts(human)
        delta2 = after_hop - baseline
        print(f"DELTA_AFTER_HOP: max={np.abs(delta2).max():.6f}")
    except Exception as e:
        print(f"HOP_SET_ERR: {e}")

except Exception as e:
    print(f"ERROR: {e}")
    traceback.print_exc()
