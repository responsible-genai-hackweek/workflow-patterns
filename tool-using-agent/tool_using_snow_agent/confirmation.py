"""Deterministic confirmation handling for the Snow Cover Analysis Agent."""

from enum import Enum

from .responses import get_response
from .state import get_state


class ConfirmationType(str, Enum):
    """Classification of user response to a pending confirmation."""
    AFFIRM = "affirm"    # User said yes - handle without LLM
    REJECT = "reject"    # User said no - handle without LLM
    COMPLEX = "complex"  # Needs LLM interpretation (e.g., "no, I meant San Francisco")


# Near-exhaustive lists of simple affirmative/negative responses
AFFIRMATIVE_RESPONSES = frozenset({
    "yes", "y", "yeah", "yep", "yup",
    "correct", "right", "ok", "okay",
    "confirm", "confirmed", "sure",
    "looks good", "that's right", "thats right",
    "good", "perfect", "great",
    "proceed", "continue", "go ahead",
})

NEGATIVE_RESPONSES = frozenset({
    "no", "n", "nope", "nah",
    "wrong", "incorrect", "not right",
    "cancel", "stop", "nevermind", "never mind",
})


def classify_response(user_input: str) -> ConfirmationType:
    """Classify user response as affirm, reject, or complex.
    
    This is DETERMINISTIC - no LLM involved, no tokens spent.
    """
    normalized = user_input.strip().lower().rstrip("!.,?")
    
    if normalized in AFFIRMATIVE_RESPONSES:
        return ConfirmationType.AFFIRM
    if normalized in NEGATIVE_RESPONSES:
        return ConfirmationType.REJECT
    return ConfirmationType.COMPLEX  # Route to LLM


def handle_confirmation(user_message: str, state: dict | None = None) -> tuple[str | None, dict | None]:
    """Handle a confirmation response deterministically if possible.
    
    Returns:
        (response_message, info) if handled without LLM
        (None, None) if should route to LLM
    """
    if state is None:
        state = get_state()
    
    pending = state.get("pending_confirmation", [])
    if not pending:
        return None, None  # No pending confirmation, route to LLM
    
    classification = classify_response(user_message)
    
    if classification == ConfirmationType.COMPLEX:
        # Complex response (e.g., "no, I meant X") supersedes the pending
        # confirmation - remove it so the LLM can re-run the relevant tool.
        state["pending_confirmation"] = pending[1:]
        return None, None

    # Get the first item from the pending list
    current_type = pending[0]
    
    if classification == ConfirmationType.REJECT:
        # Clear the rejected value
        if current_type == "location":
            state["location_name"] = None
            state["location_bbox"] = None
            state["location_geometry"] = None
        # Remove the rejected item from the pending list
        state["pending_confirmation"] = pending[1:]
        return get_response("rejected", field=current_type), {"action": "reject"}
    
    # AFFIRM - confirm and proceed
    # Remove the confirmed item from the pending list
    state["pending_confirmation"] = pending[1:]
    return get_response("confirmed"), {"action": "affirm"}
