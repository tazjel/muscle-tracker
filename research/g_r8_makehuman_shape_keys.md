# G-R8: MakeHuman Shape Keys for Athletic Male Body

### 1. Encoded Names in Blender
TMPFB2 shortens target filenames using prefixes to fit Blender limits:
- **Male:** Prefixed with `$ma`.
- **Muscular:** Prefixed with `$mu`.
- **Macrodetails:** Prefixed with `$md`.

### 2. Exact Shape Keys (Patterns)
The script's pattern matching is the safest approach as final names vary based on import settings:
- `$ma`: Male proportions
- `$mu` or `muscle`: Muscle definition
- `weight`: Overall body fat (low value = athletic)

### 3. Application Method
Shape keys are set via `body.data.shape_keys.key_blocks[name].value`. 
**Note:** Literal "male" and "muscular" do not exist as direct names unless prefixed.

### 4. Recommended Values for "Athletic"
- `'$ma'`: 1.0 + `'$md-male'`: 1.0
- `'$mu'`: 0.7 - 1.0
- `'weight'a: 0.3 - 0.4 (lean)