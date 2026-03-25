# G-R20: Phenotype Slider UX Patterns

### 1. Slider Labels and Ranges
- **Muscle**: Instead of "0-100", use "Muscle Definition" (Smooth ↔ Shredded) or "Lean Mass Index" (Low ↔ High) for broader user comprehension.
- **Weight/Fat**: "Body Fat %" (5% - 50%) is the industry standard in fitness apps, rather than abstract "Weight" variables. It correlates better with user goals.
- **Gender**: A continuous slider (0.0 to 1.0) labeled "Masculine ↔ Feminine" allows for inclusive phenotype blending and handles varied baseline morphologies better than a binary toggle.

### 2. Contextual vs. Global Controls
- **Global**: Phenotype controls (Gender, Muscle, Weight) dictate the base mesh generation. These must be **Global** (always visible in a sticky sidebar or top panel).
- **Contextual**: Per-region adjustments (e.g., Left Bicep Width) should remain contextual, appearing only when the user selects a specific muscle group.

### 3. Server Round-Trip UX (500ms Debounce)
- **Debounce**: A 500ms debounce on slider `onChange` is mandatory to prevent server flooding.
- **Progressive Preview**:
  - *Instant Feedback*: Update UI numbers and overlay a lightweight wireframe or a loading spinner on the 3D canvas immediately upon drag.
  - *Resolution*: Once the new GLB arrives (~1s), cross-fade or pop it in. Do not freeze the main thread while parsing the new mesh.

### 4. Layout Placement in Viewer
- Inside the `#adjust-panel` (Adjust Tab), the layout should be vertically stacked:
  1. **Global Phenotype Panel**: Contains Gender, Muscle, and Body Fat sliders.
  2. **Divider/Header**: "Region Adjustments"
  3. **Contextual Panel**: The existing Width/Depth/Length sliders, active only when a region is clicked.