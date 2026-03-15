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

db.commit()
