# G-R18: MPFB2 Muscle/Weight Macro System

### 1. Mechanism of Action
MPFB2 does NOT use standard Blender shape keys for muscle and weight. It uses an internal **Target Service** that interpolates between sparse vertex delta files (.target). 
Shape keys appear only after calling the MPFB2 API.

### 2. Target File Paths
Located in `selected_addon_dir/data/targets/macrodetails/`:
- **Muscle:** `minmuscle.target`, `averagemuscle.target`, `maxmuscle.target`
- **Weight:** `minweight.target`, `averageweight.target`, `maxweight.target`

### 3. Extraction Sequence (for Sonnet)
To get numpy deltas without manual target parsing:
```python
from mpfb.services.humanservice import HumanService
from mpfb.services.targetservice import TargetService

# 1, Get baseline (muscle=0.5)
human = HumanService.get_active_human()
TargetService.set_macro_value(human, 'muscle', 0.5)
V_base = get_vertices(human)

# 2, Get extreme (muscle=1.0)
TargetService.set_macro_value(human, 'muscle', 1.0)
V_max = get_vertices(human)

# 3, Compute delta
delta_muscle = V_max - V_base
````

### 4. Verdict
Muscle/Weight are independent macros. They do not appear in the basic `sshape_keys` filter unless explicitly set through MPFB2 services. Sonnet must use the HumanService approach to export these.