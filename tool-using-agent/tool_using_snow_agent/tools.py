"""LangChain tools for the Snow Cover Analysis Agent."""

import json
import re
from datetime import datetime

from langchain_core.tools import tool

from .responses import get_response, build_tool_response, ResponseStatus
from .state import get_state
from .services import geocode_location, fetch_snow_data


@tool
def get_location(query: str) -> str:
    """Resolve a place name to a geographic location.
    
    Args:
        query: Place name like 'Grand Mesa, CO', 'Yellowstone', or 'Sierra Nevada'
    
    Returns:
        JSON with status and minimal location info.
        Full geometry is stored in state for downstream tools.
    """
    result = geocode_location(query)
    
    if result is None:
        msg = get_response("location_not_found", query=query)
        return json.dumps(build_tool_response(ResponseStatus.ERROR, msg))
    
    # Store FULL result in state (includes large geometry)
    get_state()["location_name"] = result["name"]
    get_state()["location_bbox"] = result["bbox"]
    get_state()["location_geometry"] = result["geometry"]
    get_state()["pending_confirmation"].append("location")
    
    # Return MINIMAL info to LLM
    msg = get_response("location_resolved", place=result["name"])
    return json.dumps(build_tool_response(
        ResponseStatus.PENDING_CONFIRMATION,
        msg,
        place=result["name"],
        bbox=result["bbox"],
    ))


@tool
def set_date_range(start: str, end: str) -> str:
    """Set the date range for snow cover analysis.
    
    Date range must be in ISO-8601 format with "/" separator: YYYY-MM-DD/YYYY-MM-DD
    The LLM converts natural language dates to this format before calling.
    
    Args:
        start: ISO-8601 start date (e.g., '2023-02-01')
        end: ISO-8601 end date (e.g., '2023-02-28')
    
    Returns:
        JSON with status and confirmation message.
    """
    import re
    
    def validate_and_normalize(start_str, end_str):
        """Validate ISO-8601 format and return (normalized, error)."""
        # Check for "/" separator
        combined = f"{start_str}/{end_str}"
        if combined.count('/') != 1:
            return None, "Date range must use exactly one '/' separator: YYYY-MM-DD/YYYY-MM-DD"
        
        # Split and validate each part
        parts = combined.split('/')
        if len(parts) != 2:
            return None, "Invalid format: expected YYYY-MM-DD/YYYY-MM-DD"
        
        start_part, end_part = parts
        
        # Validate ISO-8601 pattern (YYYY-MM-DD)
        iso_pattern = r'^\d{4}-\d{2}-\d{2}$'
        if not re.match(iso_pattern, start_part):
            return None, f"Invalid start date format: '{start_part}'. Expected YYYY-MM-DD"
        if not re.match(iso_pattern, end_part):
            return None, f"Invalid end date format: '{end_part}'. Expected YYYY-MM-DD"
        
        # Validate date values
        from datetime import datetime
        try:
            start_dt = datetime.strptime(start_part, "%Y-%m-%d")
        except ValueError:
            return None, f"Invalid start date: '{start_part}'"
        
        try:
            end_dt = datetime.strptime(end_part, "%Y-%m-%d")
        except ValueError:
            return None, f"Invalid end date: '{end_part}'"
        
        # Validate range
        if start_dt > end_dt:
            return None, f"Start date {start_part} must be before end date {end_part}"
        
        return (start_part, end_part), None
    
    # Normalize and validate
    normalized, error = validate_and_normalize(start, end)
    
    if error:
        return json.dumps(build_tool_response(ResponseStatus.ERROR, error))
    
    start_parsed, end_parsed = normalized
    
    # Store in state
    get_state()["date_start"] = start_parsed
    get_state()["date_end"] = end_parsed
    
    msg = get_response("date_set", start=start_parsed, end=end_parsed)
    return json.dumps(build_tool_response(ResponseStatus.COMPLETE, msg))
    
@tool
def run_analysis() -> str:
    """Run snow cover analysis using MODIS data from Planetary Computer.
    
    Reads location and dates from internal state.
    No parameters needed - all data comes from state, not the LLM.
    
    Returns actual snow cover statistics:
    - Mean, min, max, std dev of snow cover percentage
    - Daily variation (dates with lowest/highest snow cover)
    - Number of days and pixels analyzed
    """
    # Read from state - NOT from LLM parameters
    bbox = get_state().get("location_bbox")
    location_name = get_state().get("location_name")
    start = get_state().get("date_start")
    end = get_state().get("date_end")
    
    if not bbox:
        return json.dumps(build_tool_response(ResponseStatus.ERROR, get_response("need_location")))
    if not start or not end:
        return json.dumps(build_tool_response(ResponseStatus.ERROR, get_response("need_date")))
    
    # Fetch snow data using bbox from state
    result = fetch_snow_data(bbox, start, end)
    get_state()["analysis_result"] = result
    
    # Handle no data
    if result["count"] == 0:
        msg = get_response("analysis_no_data")
        return json.dumps(build_tool_response(ResponseStatus.COMPLETE, msg, count=0))
    
    # Get snow statistics
    stats = result.get("statistics", {})
    snow = stats.get("snow_cover")
    
    if not snow:
        msg = get_response("analysis_no_snow_stats", count=result["count"])
        return json.dumps(build_tool_response(ResponseStatus.COMPLETE, msg, count=result["count"]))
    
    # Format the response with actual snow statistics
    snow_pct = snow.get("snow_cover_percent", {})
    daily = snow.get("daily_mean", {})
    
    msg = get_response(
        "analysis_complete",
        count=result["count"],
        scenes_analyzed=stats.get("scenes_analyzed", 0),
        location=location_name,
        mean_snow=snow_pct.get("mean", "N/A"),
        min_snow=snow_pct.get("min", "N/A"),
        max_snow=snow_pct.get("max", "N/A"),
        std_snow=snow_pct.get("std", "N/A"),
        min_daily_mean=daily.get("min", "N/A"),
        max_daily_mean=daily.get("max", "N/A"),
        min_daily_date=daily.get("min_date", "N/A"),
        max_daily_date=daily.get("max_date", "N/A"),
        days_analyzed=snow.get("days_analyzed", 0),
        pixels_analyzed=snow.get("total_pixels_analyzed", 0),
    )
    
    # Build templated summary
    mean_val = snow_pct.get("mean", 0)
    if mean_val >= 70:
        coverage_level = "high"
        interpretation = " This indicates substantial snowpack typical of mid-winter conditions."
    elif mean_val >= 40:
        coverage_level = "moderate"
        interpretation = " This suggests variable conditions with periods of melt and accumulation."
    else:
        coverage_level = "low"
        interpretation = " This may indicate early/late season conditions or significant melt events."
    
    variation_range = daily.get("max", 0) - daily.get("min", 0)
    if variation_range > 30:
        variation_description = "significant variation throughout the period"
    elif variation_range > 15:
        variation_description = "moderate variation throughout the period"
    else:
        variation_description = "relatively stable conditions"
    
    # Extract date range for display
    date_range = result.get("date_range", {})
    start_date = date_range.get("start", "2023-02-01")
    end_date = date_range.get("end", "2023-02-28")
    # Format as "February 1-28, 2023" or "December 2022 - February 2023"
    start_dt = datetime.strptime(start_date, "%Y-%m-%d")
    end_dt = datetime.strptime(end_date, "%Y-%m-%d")
    if start_dt.year == end_dt.year and start_dt.month == end_dt.month:
        date_range_str = f"{start_dt.strftime('%B')} {start_dt.day}-{end_dt.day}, {start_dt.year}"
    elif start_dt.year == end_dt.year:
        date_range_str = f"{start_dt.strftime('%B')} {start_dt.day} - {end_dt.strftime('%B')} {end_dt.day}, {start_dt.year}"
    else:
        date_range_str = f"{start_dt.strftime('%B')} {start_dt.day}, {start_dt.year} - {end_dt.strftime('%B')} {end_dt.day}, {end_dt.year}"
    
    summary = get_response(
        "analysis_summary",
        location=location_name.split(",")[0],
        coverage_level=coverage_level,
        date_range=date_range_str,
        mean_snow=mean_val,
        variation_description=variation_description,
        min_daily_mean=daily.get("min", "N/A"),
        max_daily_mean=daily.get("max", "N/A"),
        min_daily_date=daily.get("min_date", "N/A"),
        max_daily_date=daily.get("max_date", "N/A"),
        interpretation=interpretation,
    )
    
    msg = msg + "\n\n" + summary
    
    return json.dumps(build_tool_response(
        ResponseStatus.COMPLETE,
        msg,
        count=result["count"],
        statistics=stats,
    ))


tools = [get_location, set_date_range, run_analysis]