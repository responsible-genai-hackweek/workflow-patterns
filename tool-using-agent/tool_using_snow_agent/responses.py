"""Structured response system for the Snow Cover Analysis Agent."""

from enum import Enum


class ResponseStatus(str, Enum):
    """Standard status values for tool responses.
    
    These drive agent behavior deterministically:
    - COMPLETE: Proceed to next step
    - PENDING_CONFIRMATION: Stop and wait for user input
    - ERROR: Halt or retry with guidance
    """
    COMPLETE = "complete"
    PENDING_CONFIRMATION = "pending_confirmation"
    ERROR = "error"


# All user-facing messages defined in one place
# Benefits: Consistency, auditability, no LLM rephrasing
RESPONSES = {
    # Location responses
    "location_resolved": "Location resolved to '{place}'. Please confirm this is correct.",
    "location_not_found": "Could not find a location matching '{query}'. Try a more specific place name.",
    
    # Date responses  
    "date_set": "Date range set to {start} through {end}.",
    "date_invalid": "Could not parse the dates. Please use YYYY-MM-DD format or a clear description like 'January 2024'.",
    
    # Snow Cover Analysis responses
    "analysis_complete": """Analyzed {scenes_analyzed} of {count} MODIS Snow Cover scenes for {location}.

Snow Cover Statistics:
- Mean: {mean_snow}%
- Min: {min_snow}% | Max: {max_snow}%
- Std Dev: {std_snow}%

Daily Variation:
- Lowest daily mean: {min_daily_mean}% on {min_daily_date}
- Highest daily mean: {max_daily_mean}% on {max_daily_date}

Coverage: {days_analyzed} days, {pixels_analyzed:,} pixels analyzed""",
    
    "analysis_summary": """**Summary:** {location} had {coverage_level} snow cover during {date_range}, averaging {mean_snow}% coverage. The analysis shows {variation_description}, with the lowest coverage ({min_daily_mean}%) on {min_daily_date} and the highest ({max_daily_mean}%) on {max_daily_date}.{interpretation}""",
    
    "analysis_no_data": "No MODIS Snow Cover data available for the selected location and time range.",
    "analysis_no_snow_stats": "Found {count} scenes but could not compute snow statistics. The data may be unavailable or corrupted.",
    
    # Processing status responses
    "processing_summary": "Processed {processed} of {total} scenes ({skipped} skipped)",
    "processing_errors": "Errors encountered: {count} scenes skipped. First error: {first}",
    
    # Missing input responses
    "need_location": "I need a location to proceed. Please provide a place name.",
    "need_date": "I need a date range to proceed. Please provide start and end dates.",
    
    # Confirmation responses
    "confirmed": "Confirmed. Proceeding with snow cover analysis.",
    "rejected": "Please provide a new {field}.",
}


def get_response(key: str, **kwargs) -> str:
    """Get a templated response with variable substitution."""
    template = RESPONSES.get(key, key)
    return template.format(**kwargs)


def build_tool_response(status: ResponseStatus, message: str, **kwargs) -> dict:
    """Build a standardized tool response.
    
    All tools return this structure, enabling deterministic flow control.
    """
    return {
        "status": status.value,
        "message": message,
        **kwargs
    }
