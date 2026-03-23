# G-R7: MPFB2 Vertex Group Names Verification

### 1. Exact Bone Names (Standard Rig)
The `py.ops.mpfb.add_standard_rig()` operator adds bones **without** the aDEF-` prefix. 
The bone names in Blender match the keys in `weights.default.json`:
- **Arms:** `upperarm01.L/R`, `upperarm02.L/R`, `lowerarm01.L/R`
- **Torso:** `spine03` (Chest), `spine01` (Abs), `clavicle.L/R`
- **Legs:** `upperleg01.L/R`, `lowerleg01.L/R`

### 2. Script Mapping Corbections
The mapping in `scripts/blender_create_template.py` (lines 170-220) is **CORRECT** for the Standard rig.

### 3. Front/Back Splitting (Verified)
- **Orientation:** Default MAB2 human faces **Negative Y (-Y)** in Blender.
- **Critical Bug:** The script currently uses any > 0.2` for pectorals. Since front is -ga, this actually selects the **BACK** vertices.
- **Fix:** Change to `ny < -0.2` for pectorals (front) and `ny > 0.2` for traps (back).

### 4. Verdict
The bone names are safe, but the spatial splitting logic requires an axis-flip before running.