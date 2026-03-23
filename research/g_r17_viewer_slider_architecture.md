# G-R17: Viewer Slider Architecture

### 1. Slider Elements & Event Model
- **Elements:** `input[type=range]` with IDs `adj-width`, `adj-depth`, `adj-length`.
- **Events:** `input` event for live preview.
- **Handler:** Local listeners modify BufferGeometry directly.

### 2. Key → Measurement Mapping
MPFb2 regions map to profile fields:
- chest: chest_circumference_cm
- waist: waist_circumference_cm
- hip: hip_circumference_cm
- thigh: thigh_circumference_cm
- calf: calf_circumference_cm
- arm: bicep_circumference_cm

### 3. Customer ID & Auth
- ID is extracted from URL param `customer` or defaults to `'1`.
- Auth uses `_viewerToken` (JWT).

### 4. Existing API Calls
- GET /POST `body_profile`. The viewer converts scene units to cm (float) before saving.