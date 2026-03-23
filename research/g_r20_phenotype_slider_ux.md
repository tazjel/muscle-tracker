# G-R20: Phenotype Slider UX Patterns

### 1. Labels & Ranges
Based on fitness app standards, use these ranges for the 0-1 macro values:

| Macro | Label | Range Display | Visual Feedback |
|----------|------------------|---------------|------------------|
| muscle | Muscle Definition | Hidden → Ripped | Pore/vascularity |
| weight | Body Fat | Athletic ↓ Obese | Body width/softness |
| gender | Body Type | Female → Male | Hip/shoulder ratio |

### 2. Layout Strategy
1. **Placement:** In the `Adjust` tab, above the `#adjust-panel`. These are "Global" modifiers compared to the region-specific width/depth sliders.
2. **Grouping:** Create a new div `#phenotype-controls` with a separate header "Body Composition".

### 3. Real-Time Feedback
1. **Debounce:** 500ms is mandatory. Show a spinner on the 3D canvas during the `GLBLoader` phase.
2. **Progressive:** Do not block the UI. Allow the user to adjust multiple sliders before the first update fires.
3. **Min/Max:** Set slider steps to 0.01 for smooth morphing.

### 4. Verdict
Phenotype sliders should be the first thing a user sees in the Adjust tab. Use descriptive labels (Ripped, Athletic) rather than raw 0.0-1.0 numbers.