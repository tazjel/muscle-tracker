# G-R15: Shape Key Delta Export Order

### 1. Correct Order: (a) Remove Helpers → Extract Deltas
Blender's `bmesh.to_mesh(me)` automatically shrinks all shape key blocks to match the new vertex count. Extracting DELTA after removal ensures indices match the 13,380-body mesh perfectly.

### 2. Safe Extraction Snippet (Amended)
```python
import bpy, bmesh, numpy as np
bm = bmesh.from_edit_mesh(obj.data)
# Delete helpers here...
bm.to_mesh(obj.data)
bm.free()
kb = obj.data.shape_keys.key_blocks
deltas = np.zeros(13380 * 3, dtype=np.float32)
kb['$ma-$mu'].data.foreach_get('co', deltas)
```

### 3. Edge Cases & Verdict
- **Shape Key Removal:** Calling `bpy.ops.object.shape_key_remove(all=True, apply_mix=True)` *after* extraction is safe.
- **Verdict:** Delete first. Blender handles the re-indexing of key_blocks during the to_mesh commit.