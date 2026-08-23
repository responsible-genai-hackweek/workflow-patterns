"""Data services for the Snow Cover Analysis Agent."""

import json
import re
from datetime import datetime

import numpy as np
import requests
import rioxarray
import planetary_computer as pc

from .responses import get_response, build_tool_response, ResponseStatus


STAC_API_URL = "https://planetarycomputer.microsoft.com/api/stac/v1"

# Minimum bbox size in degrees (~5km) to ensure adequate MODIS coverage
MIN_BBOX_SIZE = 0.5


def skip_scene(errors, item, reason):
    """Log and record a skipped scene."""
    item_id = item.get("id", "unknown")
    errors.append(f"{item_id}: {reason}")
    print(f"  [SKIP] {item_id}: {reason}")


def _ensure_min_bbox(bbox):
    """Expand bbox if smaller than MIN_BBOX_SIZE in either dimension."""
    min_lon, min_lat, max_lon, max_lat = bbox
    lon_size = max_lon - min_lon
    lat_size = max_lat - min_lat
    
    if lon_size < MIN_BBOX_SIZE:
        center_lon = (min_lon + max_lon) / 2
        min_lon = center_lon - MIN_BBOX_SIZE / 2
        max_lon = center_lon + MIN_BBOX_SIZE / 2
    
    if lat_size < MIN_BBOX_SIZE:
        center_lat = (min_lat + max_lat) / 2
        min_lat = center_lat - MIN_BBOX_SIZE / 2
        max_lat = center_lat + MIN_BBOX_SIZE / 2
    
    return [min_lon, min_lat, max_lon, max_lat]


def geocode_location(query: str) -> dict | None:
    """Geocode a location using Nominatim (OpenStreetMap).
    
    Uses polygon_geojson=1 to get the actual polygon when available.
    Falls back to expanding bbox if only a point is returned.
    """
    try:
        url = "https://nominatim.openstreetmap.org/search"
        params = {
            "q": query,
            "format": "json",
            "limit": 1,
            "polygon_geojson": 1,
        }
        headers = {"User-Agent": "SnowCover-Analysis-Tutorial/1.0"}
        
        resp = requests.get(url, params=params, headers=headers, timeout=10)
        resp.raise_for_status()
        results = resp.json()
        
        if not results:
            return None
        
        result = results[0]
        
        # bbox from Nominatim: [min_lat, max_lat, min_lon, max_lon]
        bbox = [
            float(result["boundingbox"][2]),  # min_lon
            float(result["boundingbox"][0]),  # min_lat
            float(result["boundingbox"][3]),  # max_lon
            float(result["boundingbox"][1]),  # max_lat
        ]
        
        # Ensure minimum bbox size for MODIS coverage
        bbox = _ensure_min_bbox(bbox)
        
        # Use GeoJSON polygon if available, otherwise center point
        geojson = result.get("geojson")
        if geojson and geojson.get("type") == "Polygon":
            geometry = geojson
        else:
            center_lon = (bbox[0] + bbox[2]) / 2
            center_lat = (bbox[1] + bbox[3]) / 2
            geometry = {
                "type": "Point",
                "coordinates": [center_lon, center_lat]
            }
        
        return {
            "name": result["display_name"],
            "bbox": bbox,
            "geometry": geometry,
        }
    except Exception as e:
        print(f"Geocoding error: {e}")
        return None


def fetch_snow_data(bbox: list, start: str, end: str) -> dict:
    """Fetch MODIS Snow Cover data and compute snow statistics.
    
    Clips in native Sinusoidal projection (no per-scene reprojection).
    Uses np.concatenate instead of list append for efficiency.
    
    Args:
        bbox: [min_lon, min_lat, max_lon, max_lat]
        start: Start date YYYY-MM-DD
        end: End date YYYY-MM-DD
    
    Returns:
        Dict with STAC items found and snow cover statistics
    """
    try:
        search_url = f"{STAC_API_URL}/search"
        
        search_params = {
            "collections": ["modis-10A1-061"],
            "bbox": bbox,
            "datetime": f"{start}T00:00:00Z/{end}T23:59:59Z",
            "limit": 100,
        }
        
        resp = requests.post(search_url, json=search_params, timeout=30)
        resp.raise_for_status()
        results = resp.json()
        
        items = results.get("features", [])
        
        if not items:
            return {
                "count": 0,
                "statistics": None,
                "collection": "modis-10A1-061",
                "message": "No MODIS Snow Cover data found for this location/time range"
            }
        
        # Accumulate pixel arrays per date
        snow_arrays_by_date = {}
        scenes_processed = 0
        errors = []
        print(f"  Processing {len(items)} MODIS scenes...")
        
        for item in items:
            props = item.get("properties", {})
            dt_str = props.get("start_datetime") or props.get("datetime")
            
            if not dt_str:
                skip_scene(errors, item, "no datetime")
                continue
                
            date_key = dt_str[:10]
            
            assets = item.get("assets", {})
            ndsi_asset = assets.get("NDSI_Snow_Cover")
            
            if not ndsi_asset:
                skip_scene(errors, item, "no NDSI_Snow_Cover asset")
                continue
            
            try:
                signed_href = pc.sign(ndsi_asset.get("href"))
                
                with rioxarray.open_rasterio(signed_href) as da:
                    # Clip in native Sinusoidal projection (no reprojection)
                    da_clipped = da.rio.clip_box(*bbox, crs="EPSG:4326")
                    
                    # Extract valid snow cover values (0-100) chrome-extension://dbkidnlfklnjanneifjjojofckpcogcl/pdf-viewer.html?file=https%3A%2F%2Fmodis-snow-ice.gsfc.nasa.gov%2Fuploads%2Fsnow_user_guide_C6.1_final_revised_april.pdf
                    values = da_clipped.values.flatten()
                    valid_values = values[(values >= 0) & (values <= 100)]
                    
                    if len(valid_values) > 0:
                        if date_key not in snow_arrays_by_date:
                            snow_arrays_by_date[date_key] = []
                        snow_arrays_by_date[date_key].append(valid_values)
                        scenes_processed += 1
                    else:
                        skip_scene(errors, item, "no valid snow values (all cloud/water/missing)")
                
            except Exception as e:
                skip_scene(errors, item, str(e)[:100])
                continue
        
        # Print summary
        print(get_response("processing_summary", processed=scenes_processed, skipped=len(errors), total=len(items)))
        if errors:
            print(get_response("processing_errors", count=len(errors), first=errors[0]))
        
        # Compute snow cover statistics
        if snow_arrays_by_date:
            # Concatenate arrays per date
            daily_stats = {}
            for date, arrays in snow_arrays_by_date.items():
                arr = np.concatenate(arrays)
                daily_stats[date] = {
                    "mean": round(float(np.mean(arr)), 1),
                    "min": round(float(np.min(arr)), 1),
                    "max": round(float(np.max(arr)), 1),
                    "pixels": len(arr),
                }
            
            # Find dates with min/max mean snow cover
            sorted_dates = sorted(daily_stats.items(), key=lambda x: x[1]["mean"])
            min_snow_date = sorted_dates[0][0]
            max_snow_date = sorted_dates[-1][0]
            
            # Overall statistics
            all_arr = np.concatenate([np.concatenate(arrs) for arrs in snow_arrays_by_date.values()])
            
            snow_statistics = {
                "snow_cover_percent": {
                    "min": round(float(np.min(all_arr)), 1),
                    "max": round(float(np.max(all_arr)), 1),
                    "mean": round(float(np.mean(all_arr)), 1),
                    "std": round(float(np.std(all_arr)), 1),
                },
                "daily_mean": {
                    "min": daily_stats[min_snow_date]["mean"],
                    "max": daily_stats[max_snow_date]["mean"],
                    "min_date": min_snow_date,
                    "max_date": max_snow_date,
                },
                "days_analyzed": len(daily_stats),
                "total_pixels_analyzed": len(all_arr),
            }
        else:
            snow_statistics = None
        
        # Metadata
        platforms = {}
        tiles = set()
        for item in items:
            props = item.get("properties", {})
            p = props.get("platform", "unknown")
            platforms[p] = platforms.get(p, 0) + 1
            
            item_id = item.get("id", "")
            parts = item_id.split(".")
            if len(parts) > 2:
                tiles.add(parts[2])
        
        statistics = {
            "total_scenes": len(items),
            "scenes_analyzed": scenes_processed,
            "platforms": platforms,
            "tiles": list(tiles),
            "snow_cover": snow_statistics,
        }
        
        return {
            "count": len(items),
            "statistics": statistics,
            "collection": "modis-10A1-061",
            "collection_title": "MODIS Snow Cover Daily",
            "bbox": bbox,
            "date_range": {"start": start, "end": end},
        }
        
    except Exception as e:
        import traceback
        return {
            "count": 0,
            "statistics": None,
            "error": str(e),
            "traceback": traceback.format_exc(),
            "message": f"Error fetching MODIS data: {e}"
        }


