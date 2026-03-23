"""
API endpoint logic tests.

Tests controller helper functions, validation, and auth flow
without requiring a running server.
"""
import pytest
import sys
import os
import json

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from core.auth import create_token, verify_token, hash_password, verify_password


class TestAuthFlow:
    """Test auth token creation and verification round-trip."""

    def test_user_token_roundtrip(self):
        token = create_token(1, role='user')
        payload = verify_token(token)
        assert payload is not None
        assert payload['sub'] == '1'
        assert payload['role'] == 'user'

    def test_admin_token_roundtrip(self):
        token = create_token('admin', role='admin')
        payload = verify_token(token)
        assert payload['sub'] == 'admin'
        assert payload['role'] == 'admin'

    def test_invalid_token_rejected(self):
        assert verify_token('garbage.token.here') is None

    def test_empty_token_rejected(self):
        assert verify_token('') is None

    def test_none_token_rejected(self):
        assert verify_token(None) is None


class TestPasswordFlow:
    """Test password hashing for the login upgrade."""

    def test_hash_creates_unique_salts(self):
        h1 = hash_password('test')
        h2 = hash_password('test')
        assert h1 != h2  # different salts

    def test_verify_correct(self):
        h = hash_password('mypassword')
        assert verify_password('mypassword', h)

    def test_verify_wrong(self):
        h = hash_password('mypassword')
        assert not verify_password('wrongpassword', h)

    def test_verify_empty_password(self):
        assert not verify_password('', hash_password('something'))

    def test_verify_none_hash(self):
        assert not verify_password('anything', None)

    def test_verify_empty_hash(self):
        assert not verify_password('anything', '')


class TestBodyProfileFields:
    """Verify the body profile field whitelist is complete."""

    def test_all_measurement_fields_present(self):
        from web_app.controllers import _BODY_PROFILE_FIELDS
        required = [
            'height_cm', 'weight_kg',
            'shoulder_width_cm', 'chest_circumference_cm',
            'bicep_circumference_cm', 'waist_circumference_cm',
            'hip_circumference_cm', 'thigh_circumference_cm',
            'calf_circumference_cm',
        ]
        for f in required:
            assert f in _BODY_PROFILE_FIELDS, f'{f} missing'

    def test_phenotype_fields_present(self):
        from web_app.controllers import _BODY_PROFILE_FIELDS
        for f in ['muscle_factor', 'weight_factor', 'gender_factor']:
            assert f in _BODY_PROFILE_FIELDS, f'{f} missing'

    def test_skin_tone_present(self):
        from web_app.controllers import _BODY_PROFILE_FIELDS
        assert 'skin_tone_hex' in _BODY_PROFILE_FIELDS


class TestDatabaseSchema:
    """Verify schema has required fields after migration."""

    def test_customer_has_password_hash(self):
        from web_app.models import db
        assert 'password_hash' in db.customer.fields

    def test_customer_has_phenotype_fields(self):
        from web_app.models import db
        for f in ['muscle_factor', 'weight_factor', 'gender_factor']:
            assert f in db.customer.fields

    def test_muscle_scan_has_processing_status(self):
        from web_app.models import db
        assert 'processing_status' in db.muscle_scan.fields

    def test_audit_log_customer_is_reference(self):
        from web_app.models import db
        assert 'reference' in str(db.audit_log.customer_id.type)

    def test_mesh_model_has_required_fields(self):
        from web_app.models import db
        for f in ['glb_path', 'obj_path', 'volume_cm3', 'num_vertices', 'num_faces']:
            assert f in db.mesh_model.fields, f'{f} missing from mesh_model'


class TestAuthCheckHelper:
    """Test the _auth_check helper logic via controllers import."""

    def test_auth_check_exists(self):
        from web_app.controllers import _auth_check
        assert callable(_auth_check)

    def test_auth_check_signature(self):
        """_auth_check should accept an optional customer_id parameter."""
        import inspect
        from web_app.controllers import _auth_check
        sig = inspect.signature(_auth_check)
        params = list(sig.parameters.keys())
        assert 'customer_id' in params


class TestMuscleGroups:
    """Test reference data."""

    def test_muscle_groups_list(self):
        from web_app.models import MUSCLE_GROUPS
        assert len(MUSCLE_GROUPS) >= 10
        assert 'bicep' in MUSCLE_GROUPS
        assert 'quadricep' in MUSCLE_GROUPS

    def test_volume_models(self):
        from web_app.models import VOLUME_MODELS
        assert 'elliptical_cylinder' in VOLUME_MODELS
        assert 'prismatoid' in VOLUME_MODELS


class TestShapeDeltas:
    """Verify shape delta files for phenotype deformation."""

    def test_shape_delta_index_exists(self):
        index_path = os.path.join(os.path.dirname(__file__), '..', 'meshes', 'shape_deltas', 'index.json')
        assert os.path.exists(index_path)

    def test_shape_delta_index_valid(self):
        index_path = os.path.join(os.path.dirname(__file__), '..', 'meshes', 'shape_deltas', 'index.json')
        with open(index_path) as f:
            index = json.load(f)
        assert len(index) >= 10, f'Expected >=10 deltas, got {len(index)}'
        for name, entry in index.items():
            assert 'file' in entry, f'{name} missing "file" key'
            assert 'baked_value' in entry, f'{name} missing "baked_value" key'

    def test_muscle_weight_deltas_exist(self):
        deltas_dir = os.path.join(os.path.dirname(__file__), '..', 'meshes', 'shape_deltas')
        import numpy as np
        for name in ['macro_muscle.npy', 'macro_weight.npy']:
            path = os.path.join(deltas_dir, name)
            assert os.path.exists(path), f'{name} not found'
            arr = np.load(path)
            assert arr.shape == (13380, 3), f'{name} shape is {arr.shape}, expected (13380, 3)'
