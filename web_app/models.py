from py4web import DAL, Field
from pydal.validators import IS_NOT_EMPTY, IS_EMAIL, IS_IN_SET, IS_NOT_IN_DB
import os
from datetime import datetime

# Database setup — SQLite for dev, swappable to Cloud SQL for production
db_path = os.path.join(os.path.dirname(__file__), '..', 'database.db')
db = DAL('sqlite://' + os.path.abspath(db_path), folder=os.path.dirname(__file__))

MUSCLE_GROUPS = [
    "bicep", "tricep", "quadricep", "hamstring", "calf",
    "deltoid", "chest", "lat", "forearm", "glute",
]

VOLUME_MODELS = ["elliptical_cylinder", "prismatoid"]

# 1. CUSTOMERS
db.define_table('customer',
    Field('name', 'string', length=128, requires=IS_NOT_EMPTY()),
    Field('email', 'string', length=256, unique=True, requires=IS_EMAIL()),
    Field('date_of_birth', 'date'),
    Field('gender', 'string', length=16),
    Field('height_cm', 'double'),
    Field('weight_kg', 'double'),
    # Segment lengths
    Field('shoulder_width_cm', 'double'),
    Field('neck_to_shoulder_cm', 'double'),
    Field('shoulder_to_head_cm', 'double'),
    Field('arm_length_cm', 'double'),
    Field('upper_arm_length_cm', 'double'),
    Field('forearm_length_cm', 'double'),
    Field('torso_length_cm', 'double'),
    Field('inseam_cm', 'double'),
    Field('floor_to_knee_cm', 'double'),
    Field('knee_to_belly_cm', 'double'),
    Field('back_buttock_to_knee_cm', 'double'),
    # Circumferences
    Field('head_circumference_cm', 'double'),
    Field('neck_circumference_cm', 'double'),
    Field('chest_circumference_cm', 'double'),
    Field('bicep_circumference_cm', 'double'),
    Field('forearm_circumference_cm', 'double'),
    Field('hand_circumference_cm', 'double'),
    Field('waist_circumference_cm', 'double'),
    Field('hip_circumference_cm', 'double'),
    Field('thigh_circumference_cm', 'double'),
    Field('quadricep_circumference_cm', 'double'),
    Field('calf_circumference_cm', 'double'),
    # Appearance
    Field('skin_tone_hex', 'string', length=8),
    Field('profile_completed', 'boolean', default=False),
    Field('notes', 'text'),
    Field('created_on', 'datetime', default=lambda: datetime.now()),
    Field('is_active', 'boolean', default=True),
)

# 2. MUSCLE SCANS
db.define_table('muscle_scan',
    Field('customer_id', 'reference customer', requires=IS_NOT_EMPTY()),
    Field('scan_date', 'datetime', default=lambda: datetime.now()),
    Field('muscle_group', 'string', length=32,
          requires=IS_IN_SET(MUSCLE_GROUPS, zero=None)),
    Field('side', 'string', length=8,
          requires=IS_IN_SET(['left', 'right', 'front', 'back', 'both'])),
    # Images
    Field('img_front', 'upload', uploadfolder='uploads/'),
    Field('img_side', 'upload', uploadfolder='uploads/'),
    # Calibration
    Field('marker_size_mm', 'double', default=20.0),
    Field('calibrated', 'boolean', default=False),
    # Computed metrics
    Field('area_mm2', 'double'),
    Field('width_mm', 'double'),
    Field('height_mm', 'double'),
    Field('volume_cm3', 'double'),
    Field('volume_model', 'string', length=32, default='elliptical_cylinder'),
    Field('shape_score', 'double'),
    Field('shape_grade', 'string', length=2),
    # Comparison to previous
    Field('growth_pct', 'double'),
    Field('volume_delta_cm3', 'double'),
    # Quality
    Field('detection_confidence', 'double'),
    Field('alignment_confidence', 'double'),
    # v5 metrics
    Field('circumference_cm', 'double'),
    Field('definition_score', 'double'),
    Field('definition_grade', 'string', length=16),
    Field('annotated_img', 'string', length=256),
    # Metadata
    Field('notes', 'text'),
    Field('device_info', 'string', length=256),
)

# 3. SYMMETRY ASSESSMENTS
db.define_table('symmetry_assessment',
    Field('customer_id', 'reference customer'),
    Field('assessment_date', 'datetime', default=lambda: datetime.now()),
    Field('muscle_group', 'string', length=32),
    Field('scan_left_id', 'reference muscle_scan'),
    Field('scan_right_id', 'reference muscle_scan'),
    Field('composite_imbalance_pct', 'double'),
    Field('dominant_side', 'string', length=8),
    Field('risk_level', 'string', length=16),
    Field('verdict', 'text'),
)

# 4. HEALTH LOGS (Diet & Activity)
db.define_table('health_log',
    Field('customer_id', 'reference customer'),
    Field('log_date', 'date', default=lambda: datetime.now().date()),
    Field('calories_in', 'integer', comment='Total daily food intake'),
    Field('protein_g', 'integer', comment='Grams of protein'),
    Field('carbs_g', 'integer'),
    Field('fat_g', 'integer'),
    Field('water_ml', 'integer'),
    Field('activity_type', 'string', length=64, comment='e.g., Heavy Squats'),
    Field('activity_duration_min', 'integer'),
    Field('sleep_hours', 'double'),
    Field('body_weight_kg', 'double'),
    Field('notes', 'text'),
)

# 5. AUDIT LOGS
db.define_table('audit_log',
    Field('customer_id', 'integer'),
    Field('action', 'string', length=64),   # e.g. 'upload_scan', 'view_report'
    Field('resource_id', 'string', length=64),  # scan_id or other resource
    Field('ip_address', 'string', length=45),
    Field('created_at', 'datetime', default=datetime.utcnow),
)

# 6. BODY COMPOSITION ASSESSMENTS
db.define_table('body_composition_log',
    Field('customer_id', 'reference customer'),
    Field('assessed_on', 'datetime', default=lambda: datetime.now()),
    Field('bmi', 'double'),
    Field('body_fat_pct', 'double'),
    Field('lean_mass_kg', 'double'),
    Field('waist_hip_ratio', 'double'),
    Field('classification', 'string', length=32),
    Field('confidence', 'string', length=16),
    Field('visual_img', 'string', length=256),
    Field('notes', 'text'),
)

# 7. 3D MESH MODELS
db.define_table('mesh_model',
    Field('customer_id', 'reference customer'),
    Field('created_on', 'datetime', default=lambda: datetime.now()),
    Field('muscle_group', 'string', length=32),
    Field('model_type', 'string', length=16, default='tube'),  # tube | body
    Field('obj_path', 'string', length=512),
    Field('glb_path', 'string', length=512),
    Field('preview_path', 'string', length=512),
    Field('volume_cm3', 'double'),
    Field('num_vertices', 'integer'),
    Field('num_faces', 'integer'),
    Field('scan_before_id', 'reference mesh_model'),
    Field('notes', 'text'),
    Field('screenshot_path', 'string', length=512),
)

# 8. DEVICE PROFILES
db.define_table('device_profile',
    Field('customer_id', 'reference customer'),
    Field('device_name', 'string', length=128),
    Field('device_serial', 'string', length=64),
    Field('role', 'string', length=16,
          requires=IS_IN_SET(['front', 'back', 'left', 'right'], zero=None)),
    Field('orientation', 'string', length=16, default='portrait'),  # portrait | landscape
    Field('camera_height_from_ground_cm', 'double'),
    Field('distance_to_subject_cm', 'double'),
    Field('sensor_width_mm', 'double'),
    Field('focal_length_mm', 'double'),
    Field('screen_width_px', 'integer'),
    Field('screen_height_px', 'integer'),
    Field('tap_x', 'integer'),
    Field('tap_y', 'integer'),
    Field('is_active', 'boolean', default=True),
    Field('created_on', 'datetime', default=lambda: datetime.now()),
    Field('notes', 'text'),
)

# 9. SCAN SETUP (per-session environment snapshot)
db.define_table('scan_setup',
    Field('customer_id', 'reference customer'),
    Field('session_date', 'datetime', default=lambda: datetime.now()),
    Field('distance_to_subject_cm', 'double'),
    Field('lighting', 'string', length=32),   # overhead_lamp | natural | fluorescent | ring_light
    Field('clothing', 'string', length=64),   # shirtless | tight_shirt | shorts
    Field('notes', 'text'),
)

# 10. VIDEO SCAN SESSIONS
db.define_table('video_scan_session',
    Field('customer_id', 'reference customer'),
    Field('session_id', 'string', length=64),   # UUID
    Field('video_path', 'string', length=512),
    Field('tracking_json_path', 'string', length=512),
    Field('status', 'string', length=32, default='UPLOADED'),  # UPLOADED | FRAMES_EXTRACTED | RECONSTRUCTED
    Field('num_frames', 'integer'),
    Field('duration_ms', 'double'),
    Field('quality_score', 'double'),
    Field('quality_report', 'text'),            # JSON from quality_gate
    Field('created_on', 'datetime', default=lambda: datetime.now()),
)

# 11. ROOM TEXTURES (photo surfaces for 3D viewer room)
db.define_table('room_texture',
    Field('customer_id', 'reference customer'),
    Field('surface', 'string', length=16,
          requires=IS_IN_SET(['floor', 'ceiling', 'wall_front', 'wall_back', 'wall_left', 'wall_right'])),
    Field('image_path', 'string', length=512),
    Field('created_on', 'datetime', default=lambda: datetime.now()),
)

db.commit()
