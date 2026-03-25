# Task G-R18: MPFB2 Muscle/Weight Macro System

1. **Mechanism**: MPFB2 does **not** use standard Blender shape keys (like `$ma` or `$fe`) for muscle and weight. Instead, it uses a proprietary macro system backed by `.target.gz` files containing sparse vertex deltas.
2. **Storage**: These files are located in `data/targets/macrodetails/` inside the add-on directory. They are combined phenotypic targets (e.g., `universal-male-young-maxmuscle-averageweight.target.gz`).
3. **API**: The Python API handles this via `HumanObjectProperties.set_value("muscle", value, entity_reference=basemesh)`. The system blends between `minmuscle` (0.0), `averagemuscle` (0.5), and `maxmuscle` (1.0) states.
4. **Independence**: They are technically separate macros but are resolved into combined targets based on age, gender, muscle, and weight to ensure accurate anatomical combinations.
5. **Extraction Strategy for Sonnet**: Since standard shape keys are not populated for muscle/weight, Sonnet must extract these deltas procedurally:
   - Create the MPFB2 human.
   - Store the baseline vertex positions (`muscle=0.5`, `weight=0.5`).
   - Call the MPFB2 API to set `muscle=1.0` (or weight).
   - Force a scene update (`bpy.context.view_layer.update()`).
   - Read the new vertex positions and compute the delta (`new_verts - baseline_verts`).
   - Export these calculated deltas.