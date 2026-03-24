"""Debug: Find MPFB2 muscle/weight properties and extract via two-human comparison."""
import bpy
import numpy as np
import traceback

PROJECT_ROOT = "C:/Users/MiEXCITE/Projects/gtd3d"

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

    # Check custom properties for muscle/weight
    print("CUSTOM_PROPS:")
    for key in human.keys():
        val = human[key]
        if isinstance(val, (int, float, str)):
            s = str(val)
            if 'mu' in key.lower() or 'we' in key.lower() or 'gen' in key.lower() or 'macro' in key.lower():
                print(f"  {key} = {s}")

    # Check data custom props
    print("DATA_PROPS:")
    for key in human.data.keys():
        val = human.data[key]
        s = str(val)
        if len(s) < 200:
            print(f"  {key} = {s[:100]}")

    # Try MPFB2 human properties service
    try:
        from bl_ext.user_default.mpfb.services.humanservice import HumanService
        print("HumanService methods:", [m for m in dir(HumanService) if not m.startswith('_') and 'macro' in m.lower() or 'muscle' in m.lower() or 'target' in m.lower() or 'phenotype' in m.lower()])
    except Exception as e:
        print(f"HumanService: {e}")

    # Try object properties
    try:
        from bl_ext.user_default.mpfb.entities.objectproperties import GeneralObjectProperties
        print("GeneralObjectProperties:", dir(GeneralObjectProperties))
    except Exception as e:
        print(f"ObjectProperties: {e}")

    # Check for MPFB2-specific RNA properties
    print("MPFB_RNA_PROPS:")
    for prop in human.bl_rna.properties:
        if 'mpfb' in prop.identifier.lower() or 'muscle' in prop.identifier.lower() or 'weight' in prop.identifier.lower():
            print(f"  {prop.identifier}: {prop.type}")

    # Try to find the modeling panel properties
    # MPFB2 stores macro values as custom properties on the mesh object
    print("ALL_CUSTOM_PROPS:")
    for key in sorted(human.keys()):
        val = human[key]
        if isinstance(val, (int, float)):
            print(f"  {key} = {val}")

except Exception as e:
    print(f"ERROR: {e}")
    traceback.print_exc()
