"""API integration tests for GTD3D backend.

Run: python -m pytest tests/test_api_integration.py -v
Requires: py4web running on localhost:8000
"""
import unittest
import json
import os
import sys

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    import urllib.request
    import urllib.error
    BASE_URL = os.environ.get('GTD3D_TEST_URL', 'http://localhost:8000/web_app')
    HAS_SERVER = False
    try:
        resp = urllib.request.urlopen(f'{BASE_URL}/api/health', timeout=2)
        HAS_SERVER = resp.status == 200
    except Exception:
        pass
except ImportError:
    HAS_SERVER = False


def api_get(path, token=None):
    headers = {}
    if token:
        headers['Authorization'] = f'Bearer {token}'
    req = urllib.request.Request(f'{BASE_URL}{path}', headers=headers)
    try:
        resp = urllib.request.urlopen(req, timeout=10)
        return resp.status, json.loads(resp.read())
    except urllib.error.HTTPError as e:
        body = e.read()
        return e.code, json.loads(body) if body else {}


def api_post(path, body=None, token=None):
    headers = {'Content-Type': 'application/json'}
    if token:
        headers['Authorization'] = f'Bearer {token}'
    data = json.dumps(body or {}).encode()
    req = urllib.request.Request(f'{BASE_URL}{path}', data=data, headers=headers, method='POST')
    try:
        resp = urllib.request.urlopen(req, timeout=10)
        return resp.status, json.loads(resp.read())
    except urllib.error.HTTPError as e:
        body = e.read()
        return e.code, json.loads(body) if body else {}


# ── Auth unit tests (no server required) ──────────────────────────────────────

from core.auth import create_token, verify_token, hash_password, verify_password


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


class TestBodyProfileFields:
    def test_whitelist_includes_phenotype(self):
        from web_app.controllers import _BODY_PROFILE_FIELDS
        for f in ['muscle_factor', 'weight_factor', 'gender_factor', 'skin_tone_hex']:
            assert f in _BODY_PROFILE_FIELDS, f'{f} missing from _BODY_PROFILE_FIELDS'

    def test_whitelist_includes_measurements(self):
        from web_app.controllers import _BODY_PROFILE_FIELDS
        for f in ['height_cm', 'weight_kg', 'chest_circumference_cm', 'bicep_circumference_cm']:
            assert f in _BODY_PROFILE_FIELDS, f'{f} missing from _BODY_PROFILE_FIELDS'


# ── Rate limiter unit tests (no server required) ───────────────────────────────

class TestRateLimiterUnit(unittest.TestCase):
    """Test rate_limit() logic directly without a running server."""

    def setUp(self):
        # Clear bucket state between tests
        from apps.web_app.rate_limit import _buckets
        _buckets.clear()

    def test_cleanup_removes_stale(self):
        import time
        from apps.web_app import rate_limit as rl_module
        # Manually insert stale entry
        with rl_module._lock:
            rl_module._buckets['stale:1.2.3.4'] = [time.time() - 400]
        rl_module.cleanup_buckets(max_age=300)
        with rl_module._lock:
            self.assertNotIn('stale:1.2.3.4', rl_module._buckets)

    def test_cleanup_keeps_fresh(self):
        import time
        from apps.web_app import rate_limit as rl_module
        with rl_module._lock:
            rl_module._buckets['fresh:1.2.3.4'] = [time.time() - 10]
        rl_module.cleanup_buckets(max_age=300)
        with rl_module._lock:
            self.assertIn('fresh:1.2.3.4', rl_module._buckets)


# ── Live server integration tests ─────────────────────────────────────────────

@unittest.skipUnless(HAS_SERVER, 'py4web not running on localhost:8000')
class TestHealthEndpoint(unittest.TestCase):
    def test_health_returns_ok(self):
        status, data = api_get('/api/health')
        self.assertEqual(status, 200)
        self.assertEqual(data['status'], 'ok')
        self.assertIn('version', data)
        self.assertIn('timestamp', data)


@unittest.skipUnless(HAS_SERVER, 'py4web not running on localhost:8000')
class TestAuthFlow(unittest.TestCase):
    def test_admin_token_success(self):
        status, data = api_post('/api/auth/admin_token', {'admin_secret': 'dev-admin-secret'})
        self.assertEqual(status, 200)
        self.assertEqual(data['status'], 'success')
        self.assertIn('token', data)

    def test_admin_token_wrong_secret(self):
        status, data = api_post('/api/auth/admin_token', {'admin_secret': 'wrong'})
        self.assertEqual(status, 401)

    def test_login_nonexistent_email(self):
        status, data = api_post('/api/login', {'email': 'nonexistent@test.com'})
        self.assertEqual(status, 404)
        self.assertEqual(data['status'], 'error')


@unittest.skipUnless(HAS_SERVER, 'py4web not running on localhost:8000')
class TestCustomerAPI(unittest.TestCase):
    def _get_admin_token(self):
        _, data = api_post('/api/auth/admin_token', {'admin_secret': 'dev-admin-secret'})
        return data.get('token')

    def test_customers_requires_auth(self):
        status, data = api_get('/api/customers')
        self.assertEqual(status, 401)

    def test_customers_with_token(self):
        token = self._get_admin_token()
        self.assertIsNotNone(token)
        status, data = api_get('/api/customers', token=token)
        self.assertEqual(status, 200)
        self.assertEqual(data['status'], 'success')
        self.assertIn('customers', data)


@unittest.skipUnless(HAS_SERVER, 'py4web not running on localhost:8000')
class TestRateLimit(unittest.TestCase):
    def test_rate_limit_enforced(self):
        """Hit auth endpoint rapidly to trigger rate limit."""
        hit_429 = False
        for i in range(15):
            try:
                status, data = api_post('/api/auth/admin_token', {'admin_secret': 'wrong'})
                if status == 429:
                    hit_429 = True
                    self.assertIn('retry_after', data)
                    break
            except Exception:
                pass
        # Rate limit should kick in within 15 requests (limit is 10/min)
        self.assertTrue(hit_429, 'Rate limit was not triggered after 15 requests')


if __name__ == '__main__':
    unittest.main()
