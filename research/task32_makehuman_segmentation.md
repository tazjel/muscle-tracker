# Gamini Research Report — MakeHuman Body Vertex Segmentation

### 1. Vertex Group Source
MakeHuman base mesh vertex assignments are defined in JSON Weights (.jsonw) files within the MPFB2 addon data. 
The definitive mapping for the "Standard" rig is located at:
- [MPFB2 Source:](https://github.com/makehumancommunity/mpfb2/blob/master/src/mpfb/data/rigs/standard/weights.human.json)

### 2. Full Body Part List (MakeHuman Standard Rig)
The "Standard" rig contains ~163 bones. Key deformation bones include:
- **Torso:** hips, spine, spine.001 (lower back), spine.002 (mid back), spine.003 (chest), neck, head
- **Arms:** shoulder.L/R, upper_arm.L/R, forearm.L/R, hand.L/R
- ** Legs:** thigh.L/R, shin.L/R, foot.L/R, toe.L/R
- **Extras:** breast.L/R, face.* (jaw, eyes, lips)

### 3. Mapping Table: MakeHuman Bones → Fitness Muscles
To extract precise muscle groups, we use the highest weight assignment:

|Fitness Muscle | MakeHuman Bones (DEF-prefix) | Notes |
|-------------------|---------------------------------------|-----------------------------------------|
| biceps_l/r | upper_arm.L/R.001 | Front/top weights | 
| forearms_l/r | forearm.L/R | Entire forearm deform chain |
| deltoids_l/r | shoulder.L/R | Includes clavicle/acromion area |
| pectorals | breast.L/R, spine.003 | Mainly front of spine.003 |
| traps | spine.004, neck | Upper back and neck base |
| abs | spine.001, spine.002 | Front vertices only |
| obliques | spine.001 | Side vertices |
| glutes | spine, pelvis.L/R | Back/posterior vertices |
| quads_l/r | thigh.L/R | Front of upper leg |
| calves_l/r | shin.L/R | Back of lower leg |

### 4. MPFB2 Rig Fix (Blender 5.1)
The reason `py.ops.mpfb.add_rig()` may fail is that MPFB2 requires specific rig type operators. The correct operator for the default skeleton is: 
```python
bpy.ops.mpfb.add_standard_rig()
```
**Requirements:** An MPFB2 human mesh must be the **active object** before running the operator.

### 5. Blender Script to Extract Vertex Groups
This script extracts vertex assignments based on the highest weight bone.

```python
import bpy
import json

def extract_segmentation():
    obj = bpy.context.active_object
    if not obj or obj.type != 'MESH':
        print("Remove all other objects and select the human mesh.")
        return
    
    segmentation = {}
    vgroups = obj.vertex_groups
    
    for v in obj.data.vertices:
        if not v.groups: continue
        # Find group with max weight
        best_g = max(v.groups, key=lambda g: g.weight)
        group_name = vgroups[best_g.group].name
        
        if group_name not in segmentation:
            segmentation[group_name] = []
        segmentation[group_name].append(v.index)
    
    with open("task32_segmentation.json", "w") as f:
        json.dump(segmentation, f)
    print("Segmentation exported to task32_segmentation.json")

extract_segmentation()
```