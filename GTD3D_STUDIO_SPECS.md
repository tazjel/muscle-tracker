# GTD3D Studio - Functional Requirements

## Mobile Application (gtd3d apk)

### Core Features
- **Auto-Start Camera:** On application launch, the front camera should automatically start streaming.
- **Server Mode:** Host a local MJPEG or H.264 stream for the desktop studio to consume.
- **Remote Control API:** Respond to incoming commands from the desktop studio.
- **Camera Flash:** Support for toggling the device's flashlight (where available).
- **Zoom Control:** Support for digital zoom adjustments.
- **Two-Way Audio:** Stream audio from the phone to the desktop and vice versa.
- **High Resolution Capture:** Trigger high-quality photo capture for 3D reconstruction.

## Desktop Studio (py4web app)

### Camera Viewer
- **Live Feed:** Low-latency display of the mobile app's camera stream.
- **View Controls:** Flip or rotate the view as needed for better visibility.
- **Volume Indicators:** Visual feedback for incoming audio levels.

### Remote Controls
- **Camera Toggle:** Switch between front and back cameras.
- **Flash Toggle:** Remote switch for the phone's flashlight.
- **Zoom Controls:** Slider or buttons to zoom in and out.
- **Audio Controls:**
  - **Mute/Unmute:** Control incoming audio stream.
  - **Talkback:** Stream audio from desktop to the mobile app's speakers.

### Data Capture (Phase 2) - [IN PROGRESS / IMPLEMENTED]
- **Snapshot Capture:** [DONE] Trigger a full-resolution image capture on the mobile device and save it directly to the desktop workspace.
- **Metadata Logging:** [DONE] Capture orientation, focal length, and lighting conditions (via sensors) alongside images.
- **Sequence Capture:** [DONE] Automated multi-angle capture (Front, Side, Back) for mesh generation.
