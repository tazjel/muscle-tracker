"""JWT authentication module for the Muscle Tracker API."""
import os
import time
import logging
import secrets
import jwt

logger = logging.getLogger(__name__)

# Secret key for signing JWTs — MUST be set via environment variable in production.
# Generates a random key on startup if not set (dev mode only).
JWT_SECRET = os.environ.get('MUSCLE_TRACKER_JWT_SECRET', '')
if not JWT_SECRET:
    JWT_SECRET = secrets.token_hex(32)
    logger.warning("JWT_SECRET not set — using random key (tokens will not survive restart)")

JWT_ALGORITHM = 'HS256'
JWT_EXPIRY_SECONDS = int(os.environ.get('MUSCLE_TRACKER_JWT_EXPIRY', 3600))  # 1 hour default


def create_token(user_id, role='user'):
    """
    Create a signed JWT token.

    Args:
        user_id: Unique identifier for the user (customer_id or admin username)
        role: 'user' or 'admin'

    Returns:
        Encoded JWT string
    """
    now = int(time.time())
    payload = {
        'sub': str(user_id),
        'role': role,
        'iat': now,
        'exp': now + JWT_EXPIRY_SECONDS,
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


def verify_token(token):
    """
    Verify and decode a JWT token.

    Returns:
        dict with 'sub', 'role', 'iat', 'exp' on success
        None on failure (expired, invalid signature, malformed)
    """
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        return payload
    except jwt.ExpiredSignatureError:
        logger.warning("JWT expired")
        return None
    except jwt.InvalidTokenError as e:
        logger.warning("JWT invalid: %s", e)
        return None
