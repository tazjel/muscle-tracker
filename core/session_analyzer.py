import logging
import copy

logger = logging.getLogger(__name__)

class SessionDeltaReporter:
    """
    G15: Delta-Only State Reporting.
    Tracks session state and returns only changed values to minimize bandwidth.
    """
    def __init__(self):
        self.last_state = {}

    def update(self, new_state):
        """
        Update the current session state and return a delta from the previous state.
        
        Args:
            new_state: dict containing current session metrics, pose status, etc.
            
        Returns:
            dict containing only keys that changed or are new.
        """
        delta = {}
        for key, value in new_state.items():
            # If key is new or value is different
            if key not in self.last_state or self.last_state[key] != value:
                # For dictionaries, we can do a shallow check or recurse
                if isinstance(value, dict) and isinstance(self.last_state.get(key), dict):
                    inner_delta = self._get_dict_delta(self.last_state[key], value)
                    if inner_delta:
                        delta[key] = inner_delta
                else:
                    delta[key] = value
        
        # Update internal state with a deep copy to prevent mutation issues
        self.last_state = copy.deepcopy(new_state)
        return delta

    def _get_dict_delta(self, old_dict, new_dict):
        """Internal helper for nested dictionary deltas."""
        delta = {}
        for k, v in new_dict.items():
            if k not in old_dict or old_dict[k] != v:
                delta[k] = v
        return delta

    def reset(self):
        """Clear the reported state."""
        self.last_state = {}
        logger.info("SessionDeltaReporter reset.")

def get_session_summary(full_state):
    """
    High-level utility to filter a full session state into a UI-friendly summary.
    """
    summary = {
        "timestamp": full_state.get("timestamp"),
        "active_task": full_state.get("current_action"),
        "progress_pct": full_state.get("progress_pct", 0),
        "status": full_state.get("status", "idle")
    }
    
    # Include pose info if available
    if "pose" in full_state:
        summary["pose_status"] = full_state["pose"].get("status")
        summary["pose_score"] = full_state["pose"].get("pose_score")
        
    return summary
