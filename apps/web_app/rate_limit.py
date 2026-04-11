"""Simple in-memory rate limiter for GTD3D API endpoints.

Usage in controllers:
    from .rate_limit import rate_limit

    @action('api/login', method=['POST'])
    def login():
        limited = rate_limit('auth', max_requests=10, window_seconds=60)
        if limited:
            return limited
        ...
"""
import time
import threading
from py4web import request, response

_lock = threading.Lock()
_buckets = {}  # key -> { ip -> [timestamps] }


def rate_limit(bucket='default', max_requests=30, window_seconds=60):
    """Check rate limit for current request IP.

    Returns None if allowed, or a dict with error response if limited.
    Sets response.status = 429 when rate limited.
    """
    ip = request.environ.get('REMOTE_ADDR', 'unknown')
    key = f"{bucket}:{ip}"
    now = time.time()
    cutoff = now - window_seconds

    with _lock:
        if key not in _buckets:
            _buckets[key] = []

        # Prune old entries
        _buckets[key] = [t for t in _buckets[key] if t > cutoff]

        if len(_buckets[key]) >= max_requests:
            response.status = 429
            retry_after = int(_buckets[key][0] + window_seconds - now) + 1
            response.headers['Retry-After'] = str(retry_after)
            return dict(
                status='error',
                message=f'Rate limit exceeded. Try again in {retry_after}s.',
                retry_after=retry_after,
            )

        _buckets[key].append(now)

    return None


def cleanup_buckets(max_age=300):
    """Remove stale entries older than max_age seconds. Call periodically."""
    cutoff = time.time() - max_age
    with _lock:
        stale = [k for k, v in _buckets.items() if not v or v[-1] < cutoff]
        for k in stale:
            del _buckets[k]
