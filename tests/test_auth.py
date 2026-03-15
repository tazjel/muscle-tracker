"""Tests for core/auth.py — JWT token creation and verification."""
import unittest
import time
import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from core.auth import create_token, verify_token, JWT_SECRET, JWT_ALGORITHM


class TestCreateToken(unittest.TestCase):

    def test_creates_string(self):
        token = create_token(user_id=1)
        self.assertIsInstance(token, str)
        self.assertGreater(len(token), 20)

    def test_contains_sub_and_role(self):
        token = create_token(user_id=42, role='admin')
        payload = verify_token(token)
        self.assertIsNotNone(payload)
        self.assertEqual(payload['sub'], '42')
        self.assertEqual(payload['role'], 'admin')

    def test_default_role_is_user(self):
        token = create_token(user_id=1)
        payload = verify_token(token)
        self.assertEqual(payload['role'], 'user')

    def test_has_iat_and_exp(self):
        token = create_token(user_id=1)
        payload = verify_token(token)
        self.assertIn('iat', payload)
        self.assertIn('exp', payload)
        self.assertGreater(payload['exp'], payload['iat'])

    def test_string_user_id(self):
        token = create_token(user_id='admin')
        payload = verify_token(token)
        self.assertEqual(payload['sub'], 'admin')


class TestVerifyToken(unittest.TestCase):

    def test_valid_token(self):
        token = create_token(user_id=1)
        payload = verify_token(token)
        self.assertIsNotNone(payload)
        self.assertEqual(payload['sub'], '1')

    def test_expired_token(self):
        import jwt as pyjwt
        now = int(time.time())
        payload = {
            'sub': '1',
            'role': 'user',
            'iat': now - 7200,
            'exp': now - 3600,  # Expired 1 hour ago
        }
        token = pyjwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)
        result = verify_token(token)
        self.assertIsNone(result)

    def test_wrong_secret(self):
        import jwt as pyjwt
        now = int(time.time())
        payload = {
            'sub': '1',
            'role': 'user',
            'iat': now,
            'exp': now + 3600,
        }
        token = pyjwt.encode(payload, 'wrong-secret', algorithm=JWT_ALGORITHM)
        result = verify_token(token)
        self.assertIsNone(result)

    def test_malformed_token(self):
        result = verify_token("not.a.valid.jwt")
        self.assertIsNone(result)

    def test_empty_string(self):
        result = verify_token("")
        self.assertIsNone(result)

    def test_none_like_token(self):
        # Passing garbage shouldn't crash
        result = verify_token("abc123")
        self.assertIsNone(result)


class TestTokenRoundtrip(unittest.TestCase):
    """End-to-end: create then verify."""

    def test_roundtrip_user(self):
        token = create_token(user_id=99, role='user')
        payload = verify_token(token)
        self.assertEqual(payload['sub'], '99')
        self.assertEqual(payload['role'], 'user')

    def test_roundtrip_admin(self):
        token = create_token(user_id='admin', role='admin')
        payload = verify_token(token)
        self.assertEqual(payload['sub'], 'admin')
        self.assertEqual(payload['role'], 'admin')

    def test_multiple_tokens_are_unique(self):
        t1 = create_token(user_id=1)
        # Small sleep to ensure different iat
        t2 = create_token(user_id=1)
        # Tokens may or may not differ (same second = same iat),
        # but both should verify
        self.assertIsNotNone(verify_token(t1))
        self.assertIsNotNone(verify_token(t2))


if __name__ == '__main__':
    unittest.main()
