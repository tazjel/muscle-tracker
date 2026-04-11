"""GTD3D Event Hub — Server-Sent Events broadcaster.

Usage from any controller:
    from .event_hub import broadcast
    broadcast('scan_progress', {'customer_id': 1, 'coverage': 75})

Studio connects via GET /api/events (SSE stream).
"""
import json
import threading
import time
from collections import deque

_lock = threading.Lock()
_events = deque(maxlen=1000)  # Ring buffer of recent events
_event_id = 0
_subscribers = []  # list of {'queue': deque, 'last_id': int}


def broadcast(event_type, payload=None):
    """Push an event to all connected SSE clients."""
    global _event_id
    with _lock:
        _event_id += 1
        event = {
            'id': _event_id,
            'type': event_type,
            'data': payload or {},
            'timestamp': time.time(),
        }
        _events.append(event)
        for sub in _subscribers:
            sub['queue'].append(event)


def subscribe():
    """Register a new SSE subscriber. Returns a subscriber dict."""
    sub = {'queue': deque(), 'last_id': _event_id}
    with _lock:
        _subscribers.append(sub)
    return sub


def unsubscribe(sub):
    """Remove a subscriber."""
    with _lock:
        try:
            _subscribers.remove(sub)
        except ValueError:
            pass


def get_recent(since_id=0, limit=50):
    """Get recent events since a given ID (for reconnecting clients)."""
    with _lock:
        return [e for e in _events if e['id'] > since_id][-limit:]
