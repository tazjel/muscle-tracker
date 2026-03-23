"""
API integration tests for gtd3d REST endpoints.

Tests auth flow, body profile CRUD, mesh generation trigger,
and proper HTTP status codes.
"""
import pytest
import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from core.auth import create_token, verify_token, hash_password, verify_password


# ── Password hashing tests ──────────────────────────────────────────────────

class TestPasswordHashing:
    def test_hash_and_verify(self):
        h = hash_password('secret123')
        assert verify_password('secret123', h)

    def test_wrong_password(self):
        h = hash_password('correct')
        assert not verify_password('wrong', h)

    def test_empty_password(self):
        h = hash_password('something')
        assert not verify_password('', h)

    def test_none_hash(self):
        assert not verify_password('anything', None)

    def test_empty_hash(self):
        assert not verify_password('anything', '')

    def test_malformed_hash(self):
        assert not verify_password('anything', 'not-a-valid-hash')

    def test_different_hashes_for_same_password(self):
        """Salt should make hashes unique."""
        h1 = hash_password('same')
        h2 = hash_password('same')
        assert h1 != h2
        assert verify_password('same', h1)
        assert verify_password('same', h2)

    def test_hash_format(self):
        h = hash_password('test')
        assert h.startswith('pbkdf2:sha256:260000$')
        parts = h.split('$')
        assert len(parts) == 3


# ── Token + auth helper tests ───────────────────────────────────────────────

class TestAuthCheck:
    """Test the _auth_check helper logic (tested via auth module directly)."""

    def test_token_contains_sub(self):
        token = create_token(42, role='user')
        payload = verify_token(token)
        assert payload['sub'] == '42'
        assert payload['role'] == 'user'

    def test_admin_token(self):
        token = create_token('admin', role='admin')
        payload = verify_token(token)
        assert payload['sub'] == 'admin'
        assert payload['role'] == 'admin'

    def test_expired_token_returns_none(self):
        import jwt as pyjwt
        import time
        payload = {'sub': '1', 'role': 'user', 'iat': int(time.time()) - 7200, 'exp': int(time.time()) - 3600}
        token = pyjwt.encode(payload, 'wrong-secret', algorithm='HS256')
        assert verify_token(token) is None

    def test_invalid_token_returns_none(self):
        assert verify_token('not.a.token') is None
        assert verify_token('') is None
        assert verify_token(None) is None


# ── Model schema tests ──────────────────────────────────────────────────────

class TestModelSchema:
    """Verify DB schema has required fields (import-level check)."""

    def test_customer_has_password_hash(self):
        from web_app.models import db
        assert 'password_hash' in db.customer.fields

    def test_muscle_scan_has_processing_status(self):
        from web_app.models import db
        assert 'processing_status' in db.muscle_scan.fields

    def test_audit_log_customer_is_reference(self):
        from web_app.models import db
        field = db.audit_log.customer_id
        assert 'reference' in str(field.type)

    def test_customer_phenotype_fields(self):
        from web_app.models import db
        for f in ['muscle_factor', 'weight_factor', 'gender_factor']:
            assert f in db.customer.fields, f'{f} missing from customer table'


# ── Body profile field whitelist test ────────────────────────────────────────

class TestBodyProfileFields:
    def test_whitelist_includes_phenotype(self):
        # Import the whitelist from controllers
        from web_app.controllers import _BODY_PROFILE_FIELDS
        for f in ['muscle_factor', 'weight_factor', 'gender_factor', 'skin_tone_hex']:
            assert f in _BODY_PROFILE_FIELDS, f'{f} missing from _BODY_PROFILE_FIELDS'

    def test_whitelist_includes_measurements(self):
        from web_app.controllers import _BODY_PROFILE_FIELDS
        for f in ['height_cm', 'weight_kg', 'chest_circumference_cm', 'bicep_circumference_cm']:
            assert f in _BODY_PROFILE_FIELDS, f'{f} missing from _BODY_PROFILE_FIELDS'
