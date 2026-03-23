"""
blender_create_template.py — Generate the gtd3d body mesh template from MPFB2.

Run once:
  "C:/Program Files/Blender Foundation/Blender 5.1/blender.exe" --background \
    --python scripts/blender_create_template.py

Outputs:
  meshes/template_verts.npy          — (N, 3) float32 vertex positions (meters)
  meshes/template_faces.npy          — (M, 3) uint32 triangle indices
  meshes/template_uvs.npy            — (N, 2) float32 UV coordinates
  meshes/template_normals.npy        — (N, 3) float32 vertex normals
  meshes/template_joint_landmarks.json — joint cube center positions
  meshes/gtd3d_body_template.glb     — production GLB with PBR skin material
  web_app/static/viewer3d/template_vert_segmentation.json — muscle group vertex indices
"""
import bpy
import bmesh
import numpy as np
import json
import os
import sys
from mathutils import Vector

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MESHES_DIR = os.path.join(PROJECT_ROOT, 'meshes')
VIEWER_DIR = os.path.join(PROJECT_ROOT, 'web_app', 'static', 'viewer3d')

# ── Step 1: Create MPFB human ──────────────────────────────────────────────────

print("=== Step 1: Creating MPFB human ===")
bpy.ops.object.select_all(action='SELECT')
bpy.ops.object.delete()
bpy.ops.mpfb.create_human()

# Find the human mesh
human = None
for obj in bpy.data.objects:
    if obj.type == 'MESH' and len(obj.data.vertices) > 5000:
        human = obj
        break

if not human:
    print("ERROR: No human mesh found")
    sys.exit(1)

print(f"Human mesh: {human.name}, {len(human.data.vertices)} verts")

# ── Step 2: Set male athletic phenotype ────────────────────────────────────────

print("=== Step 2: Setting male athletic phenotype ===")
if human.data.shape_keys:
    for kb in human.data.shape_keys.key_blocks:
        name = kb.name.lower()
        # Boost male keys
        if '$ma' in name and '$fe' not in name:
            kb.value = min(kb.value + 0.3, 1.0)
        # Reduce female keys
        if '$fe' in name and '$ma' not in name:
            kb.value = max(kb.value - 0.3, 0.0)
        # Boost muscle if present
        if '$mu' in name or 'muscle' in name:
            kb.value = min(kb.value + 0.2, 1.0)
        print(f"  Shape key: {kb.name} = {kb.value:.3f}")

# ── Step 3: Extract joint landmarks BEFORE removing helpers ────────────────────

print("=== Step 3: Extracting joint landmarks ===")
joint_landmarks = {}
for vg in human.vertex_groups:
    if vg.name.startswith('joint-'):
        # Get vertices in this group
        verts_in_group = []
        for v in human.data.vertices:
            for g in v.groups:
                if g.group == vg.index:
                    verts_in_group.append(v.co.copy())
                    break
        if verts_in_group:
            # Compute center of the joint cube (8 verts)
            center = Vector((0, 0, 0))
            for co in verts_in_group:
                center += co
            center /= len(verts_in_group)
            joint_landmarks[vg.name] = [center.x, center.y, center.z]

print(f"  Extracted {len(joint_landmarks)} joint landmarks")

# Save joint landmarks
with open(os.path.join(MESHES_DIR, 'template_joint_landmarks.json'), 'w') as f:
    json.dump(joint_landmarks, f, indent=2)

# ── Step 3b: Add MPFB2 standard rig for bone weights ─────────────────────────

print("=== Step 3b: Adding MPFB2 standard rig ===")
bpy.context.view_layer.objects.active = human
human.select_set(True)
try:
    bpy.ops.mpfb.add_standard_rig()
    print("  Standard rig added successfully")
    # Check for new bone weight vertex groups
    bone_vgs = [vg.name for vg in human.vertex_groups if not vg.name.startswith('joint-') and not vg.name.startswith('helper-') and vg.name not in ('body', 'HelperGeometry', 'JointCubes', 'Left', 'Mid', 'Right')]
    print(f"  New bone vertex groups: {len(bone_vgs)}")
    if bone_vgs:
        print(f"  Examples: {sorted(bone_vgs)[:15]}")
except Exception as e:
    print(f"  WARNING: add_standard_rig failed: {e}")
    print("  Will fall back to spatial segmentation")

# ── Step 4: Remove helper geometry, keep only body ─────────────────────────────

print("=== Step 4: Isolating body mesh ===")
bpy.context.view_layer.objects.active = human
human.select_set(True)
bpy.ops.object.mode_set(mode='EDIT')

bm = bmesh.from_edit_mesh(human.data)
bm.verts.ensure_lookup_table()

# Find the 'body' vertex group index
body_vg_idx = None
for vg in human.vertex_groups:
    if vg.name == 'body':
        body_vg_idx = vg.index
        break

if body_vg_idx is None:
    print("ERROR: 'body' vertex group not found")
    sys.exit(1)

# Get deform layer for vertex groups
deform_layer = bm.verts.layers.deform.active

# Select NON-body vertices for deletion
for v in bm.verts:
    in_body = False
    if deform_layer:
        dvert = v[deform_layer]
        if body_vg_idx in dvert:
            in_body = True
    v.select = not in_body

# Delete selected (non-body) vertices
selected = [v for v in bm.verts if v.select]
print(f"  Removing {len(selected)} helper vertices")
bmesh.ops.delete(bm, geom=selected, context='VERTS')

bm.verts.ensure_lookup_table()
bm.faces.ensure_lookup_table()
bmesh.update_edit_mesh(human.data)
bpy.ops.object.mode_set(mode='OBJECT')

print(f"  Body mesh: {len(human.data.vertices)} verts, {len(human.data.polygons)} faces")

# ── Step 5: Triangulate (GLB needs triangles) ─────────────────────────────────

print("=== Step 5: Triangulating ===")
bpy.ops.object.mode_set(mode='EDIT')
bpy.ops.mesh.select_all(action='SELECT')
bpy.ops.mesh.quads_convert_to_tris(quad_method='BEAUTY', ngon_method='BEAUTY')
bpy.ops.object.mode_set(mode='OBJECT')
print(f"  After triangulation: {len(human.data.polygons)} faces")

# ── Step 6: Apply shape keys to bake geometry ──────────────────────────────────

print("=== Step 6: Baking shape keys ===")
if human.data.shape_keys:
    # Apply all shape keys as the final mesh
    bpy.context.view_layer.objects.active = human
    human.select_set(True)
    bpy.ops.object.shape_key_remove(all=True, apply_mix=True)
    print("  Shape keys applied and removed")

# ── Step 7: Extract mesh data ──────────────────────────────────────────────────

print("=== Step 7: Extracting mesh data ===")
mesh = human.data

num_verts = len(mesh.vertices)
num_faces = len(mesh.polygons)

# Vertices
verts = np.zeros((num_verts, 3), dtype=np.float32)
for i, v in enumerate(mesh.vertices):
    verts[i] = [v.co.x, v.co.y, v.co.z]

# Normals
normals = np.zeros((num_verts, 3), dtype=np.float32)
for i, v in enumerate(mesh.vertices):
    normals[i] = [v.normal.x, v.normal.y, v.normal.z]

# Faces (should all be triangles now)
faces = np.zeros((num_faces, 3), dtype=np.uint32)
for i, f in enumerate(mesh.polygons):
    if len(f.vertices) != 3:
        print(f"  WARNING: face {i} has {len(f.vertices)} verts (expected 3)")
    faces[i] = list(f.vertices[:3])

# UVs
uv_layer = mesh.uv_layers.active
if uv_layer:
    # UV data is per-loop, not per-vertex — we need per-vertex UVs
    # For vertices shared by multiple faces, average the UVs
    uv_sums = np.zeros((num_verts, 2), dtype=np.float64)
    uv_counts = np.zeros(num_verts, dtype=np.int32)
    for poly in mesh.polygons:
        for li in poly.loop_indices:
            loop = mesh.loops[li]
            vi = loop.vertex_index
            uv = uv_layer.data[li].uv
            uv_sums[vi] += [uv[0], uv[1]]
            uv_counts[vi] += 1
    # Avoid division by zero
    uv_counts[uv_counts == 0] = 1
    uvs = (uv_sums / uv_counts[:, None]).astype(np.float32)
    print(f"  UVs: {uvs.shape}, range u=[{uvs[:,0].min():.3f}, {uvs[:,0].max():.3f}] v=[{uvs[:,1].min():.3f}, {uvs[:,1].max():.3f}]")
else:
    print("  WARNING: No UV layer found!")
    uvs = np.zeros((num_verts, 2), dtype=np.float32)

# Save numpy arrays
np.save(os.path.join(MESHES_DIR, 'template_verts.npy'), verts)
np.save(os.path.join(MESHES_DIR, 'template_faces.npy'), faces)
np.save(os.path.join(MESHES_DIR, 'template_uvs.npy'), uvs)
np.save(os.path.join(MESHES_DIR, 'template_normals.npy'), normals)
print(f"  Saved: {num_verts} verts, {num_faces} faces")

# ── Step 8: Create muscle segmentation from vertex groups (bone weights) ──────

print("=== Step 8: Creating muscle segmentation from vertex groups ===")

# The mesh still has MPFB2 vertex groups from the original human creation.
# These include body-part groups and joint groups. Use them for segmentation.
# Map vertex group names (from MPFB2 bone weights) to our 15 fitness muscle groups.
# Based on Gemini Task 32 research: weights.human.json in MPFB2 repo.

BONE_TO_MUSCLE = {
    # Arms - left
    'upperarm01.L': 'biceps_l', 'upperarm02.L': 'biceps_l',
    # Arms - right
    'upperarm01.R': 'biceps_r', 'upperarm02.R': 'biceps_r',
    # Forearms
    'lowerarm01.L': 'forearms_l', 'lowerarm02.L': 'forearms_l', 'wrist.L': 'forearms_l',
    'lowerarm01.R': 'forearms_r', 'lowerarm02.R': 'forearms_r', 'wrist.R': 'forearms_r',
    # Deltoids
    'shoulder01.L': 'deltoids_l', 'clavicle.L': 'deltoids_l',
    'shoulder01.R': 'deltoids_r', 'clavicle.R': 'deltoids_r',
    # Torso (will split front/back by vertex normal Y direction)
    'spine03': 'pectorals',  # chest area — front=pecs, back=traps
    'spine04': 'pectorals',  # upper chest
    'spine05': 'pectorals',  # upper chest/shoulder area
    'breast.L': 'pectorals', 'breast.R': 'pectorals',
    'nipple': 'pectorals', 'nippleTip': 'pectorals',
    'spine01': 'abs',  # lower torso — front=abs, side=obliques, back=traps
    'spine02': 'abs',  # mid torso
    'root': 'glutes',  # base — mostly glutes area
    'neck01': 'traps', 'neck02': 'traps', 'neck03': 'traps',
    # Legs - left
    'upperleg01.L': 'quads_l', 'upperleg02.L': 'quads_l',
    # Legs - right
    'upperleg01.R': 'quads_r', 'upperleg02.R': 'quads_r',
    # Calves
    'lowerleg01.L': 'calves_l', 'lowerleg02.L': 'calves_l',
    'lowerleg01.R': 'calves_r', 'lowerleg02.R': 'calves_r',
    # Glutes
    'pelvis.L': 'glutes', 'pelvis.R': 'glutes',
}

# Torso bones that need front/back/side splitting
TORSO_SPLIT_BONES = {
    'spine03', 'spine04', 'spine05',
    'spine01', 'spine02',
    'root',
}

# Build reverse lookup: vg_index → vertex group name
vg_names = {vg.index: vg.name for vg in human.vertex_groups}

# Log available vertex groups that match bones
matched_vgs = []
for vg in human.vertex_groups:
    if vg.name in BONE_TO_MUSCLE:
        matched_vgs.append(vg.name)
print(f"  Matched {len(matched_vgs)} vertex groups to muscle bones")

# For each vertex, find the bone with highest weight, map to muscle group
segmentation = {
    'biceps_l': [], 'biceps_r': [],
    'forearms_l': [], 'forearms_r': [],
    'deltoids_l': [], 'deltoids_r': [],
    'pectorals': [], 'traps': [],
    'abs': [], 'obliques': [],
    'glutes': [],
    'quads_l': [], 'quads_r': [],
    'calves_l': [], 'calves_r': [],
}
unassigned = []

for vi in range(num_verts):
    v = mesh.vertices[vi]
    if not v.groups:
        unassigned.append(vi)
        continue

    # Accumulate weights per muscle group (a vertex may be influenced by multiple bones)
    muscle_weights = {}
    best_bone_per_muscle = {}
    for g in v.groups:
        gname = vg_names.get(g.group, '')
        muscle = BONE_TO_MUSCLE.get(gname)
        if muscle and g.weight > 0.01:
            muscle_weights[muscle] = muscle_weights.get(muscle, 0.0) + g.weight
            if muscle not in best_bone_per_muscle or g.weight > best_bone_per_muscle[muscle][1]:
                best_bone_per_muscle[muscle] = (gname, g.weight)

    if not muscle_weights:
        unassigned.append(vi)
        continue

    # Pick muscle with highest accumulated weight
    best_muscle = max(muscle_weights, key=muscle_weights.get)
    best_weight = muscle_weights[best_muscle]
    best_bone = best_bone_per_muscle[best_muscle][0]

    # Torso front/back/side splitting using vertex normal direction
    if best_bone in TORSO_SPLIT_BONES:
        ny = normals[vi][1]  # Y normal in Blender (front/back in A-pose)
        nx = abs(normals[vi][0])  # X normal (side)
        abs_ny = abs(ny)

        if best_bone in ('spine03', 'spine04', 'spine05'):
            # Chest area: front=pecs, back=traps
            if ny > 0.2:
                best_muscle = 'pectorals'
            elif ny < -0.2:
                best_muscle = 'traps'
            else:
                best_muscle = 'pectorals'
        elif best_bone in ('spine01', 'spine02'):
            # Mid torso: front=abs, side=obliques, back=traps(lower)
            if nx > abs_ny * 0.8:
                best_muscle = 'obliques'
            elif ny > 0.1:
                best_muscle = 'abs'
            else:
                best_muscle = 'traps'  # lower back → traps region
        elif best_bone == 'root':
            # Base spine: mostly glutes/lower abs
            if ny > 0.3:
                best_muscle = 'abs'
            elif nx > abs_ny * 0.6:
                best_muscle = 'obliques'
            else:
                best_muscle = 'glutes'

    segmentation[best_muscle].append(int(vi))

# Report initial bone-weight assignment
total_assigned = sum(len(v) for v in segmentation.values())
print(f"  Bone-weight assigned: {total_assigned} / {num_verts} vertices ({100*total_assigned/num_verts:.1f}%)")
for group, indices in sorted(segmentation.items()):
    print(f"    {group}: {len(indices)} verts")

# ── Step 8b: Expand thin groups using joint landmarks ──────────────────────────
# Deltoids and glutes have too few verts from bone weights alone.
# Use joint landmark positions to expand these groups with nearby unassigned verts.

assigned_set = set()
for group, indices in segmentation.items():
    for vi in indices:
        assigned_set.add(vi)

# Parse joint positions
joint_pos = {}
for name, coords in joint_landmarks.items():
    joint_pos[name] = np.array(coords, dtype=np.float32)

# Spatial expansion rules for thin groups
EXPAND_RULES = {
    'deltoids_l': {'joints': ['joint-l-shoulder', 'joint-l-clavicle'], 'radius': 0.12},
    'deltoids_r': {'joints': ['joint-r-shoulder', 'joint-r-clavicle'], 'radius': 0.12},
    'glutes': {'joints': ['joint-pelvis', 'joint-l-upper-leg', 'joint-r-upper-leg'], 'radius': 0.12,
               'normal_filter': lambda n: n[1] < 0.1},  # back-facing only
}

# Reassign: steal verts from neighboring groups if they're closer to deltoid/glute joints
vert_to_muscle = {}
for group, indices in segmentation.items():
    for vi in indices:
        vert_to_muscle[vi] = group

REASSIGN_RULES = {
    'deltoids_l': {
        'joints': ['joint-l-shoulder'],
        'radius': 0.13,
        'steal_from': {'pectorals', 'traps', 'biceps_l'},
    },
    'deltoids_r': {
        'joints': ['joint-r-shoulder'],
        'radius': 0.13,
        'steal_from': {'pectorals', 'traps', 'biceps_r'},
    },
    'glutes': {
        'joints': ['joint-pelvis', 'joint-l-upper-leg', 'joint-r-upper-leg'],
        'radius': 0.13,
        'steal_from': {'quads_l', 'quads_r', 'obliques', 'abs', 'traps'},
        'normal_filter': lambda n: n[1] < 0.15,  # back/side facing only
    },
}

for target_group, rule in REASSIGN_RULES.items():
    centers = [joint_pos[j] for j in rule['joints'] if j in joint_pos]
    if not centers:
        continue
    center = np.mean(centers, axis=0)
    radius = rule['radius']
    nf = rule.get('normal_filter')
    steal_from = rule['steal_from']
    stolen = 0
    for vi in range(num_verts):
        current = vert_to_muscle.get(vi)
        if current not in steal_from:
            continue
        d = np.linalg.norm(verts[vi] - center)
        if d < radius:
            if nf and not nf(normals[vi]):
                continue
            # Remove from current group, add to target
            segmentation[current].remove(vi)
            segmentation[target_group].append(vi)
            vert_to_muscle[vi] = target_group
            stolen += 1
    if stolen > 0:
        print(f"  Reassigned to {target_group}: +{stolen} verts (total {len(segmentation[target_group])})")

# Final report
total_assigned = sum(len(v) for v in segmentation.values())
print(f"  Final assigned: {total_assigned} / {num_verts} vertices ({100*total_assigned/num_verts:.1f}%)")
print(f"  Unassigned: {num_verts - total_assigned} (head, hands, feet — not muscle groups)")
for group, indices in sorted(segmentation.items()):
    print(f"    {group}: {len(indices)} verts")

# Save segmentation JSON
seg_path = os.path.join(VIEWER_DIR, 'template_vert_segmentation.json')
with open(seg_path, 'w') as f:
    json.dump(segmentation, f)
print(f"  Saved: {seg_path}")

# ── Step 9: Add PBR skin material ─────────────────────────────────────────────

print("=== Step 9: Setting up PBR skin material ===")

# Clear existing materials
human.data.materials.clear()

mat = bpy.data.materials.new(name="GTD3D_Skin")
mat.use_nodes = True
nodes = mat.node_tree.nodes
links = mat.node_tree.links
nodes.clear()

# Principled BSDF
bsdf = nodes.new('ShaderNodeBsdfPrincipled')
bsdf.location = (0, 0)
bsdf.inputs['Base Color'].default_value = (0.76, 0.57, 0.45, 1.0)  # Warm skin tone
bsdf.inputs['Roughness'].default_value = 0.65
bsdf.inputs['Metallic'].default_value = 0.0
# Subsurface scattering for skin
bsdf.inputs['Subsurface Weight'].default_value = 0.15
bsdf.inputs['Subsurface Radius'].default_value = (0.9, 0.6, 0.4)

# Output
output = nodes.new('ShaderNodeOutputMaterial')
output.location = (300, 0)
links.new(bsdf.outputs['BSDF'], output.inputs['Surface'])

human.data.materials.append(mat)

# ── Step 10: Export GLB ────────────────────────────────────────────────────────

print("=== Step 10: Exporting GLB ===")

# Select only the body mesh
bpy.ops.object.select_all(action='DESELECT')
human.select_set(True)
bpy.context.view_layer.objects.active = human

# Scale to reasonable size (MPFB default is ~1.7m which is fine)
glb_path = os.path.join(MESHES_DIR, 'gtd3d_body_template.glb')
bpy.ops.export_scene.gltf(
    filepath=glb_path,
    export_format='GLB',
    use_selection=True,
)

file_size = os.path.getsize(glb_path) / 1024
print(f"  Exported: {glb_path} ({file_size:.0f} KB)")

# ── Done ───────────────────────────────────────────────────────────────────────

print("\n=== TEMPLATE GENERATION COMPLETE ===")
print(f"  Vertices: {num_verts}")
print(f"  Faces: {num_faces}")
print(f"  Joint landmarks: {len(joint_landmarks)}")
print(f"  Muscle groups: {len(segmentation)}")
print(f"  Files saved to: {MESHES_DIR}")
print(f"  Segmentation saved to: {seg_path}")
