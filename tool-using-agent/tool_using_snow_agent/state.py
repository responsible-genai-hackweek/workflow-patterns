"""Shared state management for the Snow Cover Analysis Agent."""

from typing import Any


# Shared state that tools read from and write to
# The LLM never sees or handles large data directly
_state: dict[str, Any] = {}


def init_state():
    """Initialize fresh state."""
    global _state
    _state = {
        "location_name": None,
        "location_bbox": None,
        "location_geometry": None,  # LARGE - never sent to LLM
        "date_start": None,
        "date_end": None,
        "analysis_result": None,    # LARGE - never sent to LLM
        "pending_confirmation": [],
    }


def get_state() -> dict[str, Any]:
    """Get a reference to the shared state."""
    return _state


# Initialize state on import
init_state()
