"""
Smart Detection Service

Analyzes Street View and satellite imagery to flag properties that are
likely vacant, demolished, or in poor condition. This is a triage tool,
not a definitive assessment. It sorts the worst-looking properties to
the top of the review queue so a human can confirm.

Approach:
- Color variance analysis (boarded-up buildings have uniform colors)
- Green coverage estimation (overgrown lots suggest vacancy)
- Edge density (demolished/empty lots have fewer structural edges)
- Brightness and contrast (abandoned properties tend to be darker/dingier)
- Overall "condition score" combining these signals

This is heuristic-based. For higher accuracy, swap in a trained model
(e.g., fine-tuned ResNet on blight detection datasets).
"""

import json
import os
import asyncio
import numpy as np
from pathlib import Path
from PIL import Image
from typing import Optional
from concurrent.futures import ProcessPoolExecutor

from app.config import VACANCY_THRESHOLD, DEMOLITION_THRESHOLD, DETECTION_WORKERS


class DetectionResult:
    def __init__(
        self,
        score: float,
        label: str,
        details: dict,
    ):
        self.score = score          # 0.0 (likely fine) to 1.0 (likely problem)
        self.label = label          # likely_occupied, likely_vacant, likely_demolished
        self.details = details      # breakdown of individual signals


def analyze_color_variance(img_array: np.ndarray) -> float:
    """
    Low color variance can indicate boarded-up windows, uniform siding,
    or a blank/demolished lot. Returns 0.0 (high variance = normal)
    to 1.0 (low variance = suspicious).
    """
    # Calculate std dev across all channels
    std_per_channel = np.std(img_array, axis=(0, 1))
    avg_std = np.mean(std_per_channel)

    # Normal houses have std of 40-70+. Boarded/uniform surfaces drop below 30.
    if avg_std > 55:
        return 0.0
    elif avg_std < 20:
        return 1.0
    else:
        return max(0.0, 1.0 - (avg_std - 20) / 35)


def analyze_green_coverage(img_array: np.ndarray) -> float:
    """
    High green coverage in the main frame (not just lawn) can indicate
    overgrown vegetation on a vacant property. Returns 0.0 (normal)
    to 1.0 (heavily overgrown).
    """
    r, g, b = img_array[:, :, 0], img_array[:, :, 1], img_array[:, :, 2]

    # Detect green-dominant pixels (vegetation)
    green_mask = (g > r + 15) & (g > b + 15) & (g > 60)
    green_ratio = np.sum(green_mask) / green_mask.size

    # Focus on upper portion of image (where structure should be)
    h = img_array.shape[0]
    upper_half = img_array[:h // 2, :, :]
    r_u, g_u, b_u = upper_half[:, :, 0], upper_half[:, :, 1], upper_half[:, :, 2]
    upper_green = (g_u > r_u + 15) & (g_u > b_u + 15) & (g_u > 60)
    upper_green_ratio = np.sum(upper_green) / upper_green.size

    # Lots of green in the upper frame suggests overgrowth/no structure
    if upper_green_ratio > 0.5:
        return min(1.0, upper_green_ratio)
    elif green_ratio > 0.6:
        return 0.6
    else:
        return max(0.0, green_ratio - 0.1)


def analyze_edge_density(img_array: np.ndarray) -> float:
    """
    Structures have lots of edges (windows, doors, rooflines, siding).
    Demolished lots or overgrown areas have fewer regular edges.
    Returns 0.0 (many edges = structure present) to 1.0 (few edges = likely empty).
    """
    # Convert to grayscale
    gray = np.mean(img_array, axis=2).astype(np.uint8)

    # Simple Sobel-like edge detection
    # Horizontal edges
    h_kernel = gray[1:, :].astype(float) - gray[:-1, :].astype(float)
    # Vertical edges
    v_kernel = gray[:, 1:].astype(float) - gray[:, :-1].astype(float)

    h_edges = np.abs(h_kernel)
    v_edges = np.abs(v_kernel)

    # Count strong edges (threshold at 30)
    strong_h = np.sum(h_edges > 30)
    strong_v = np.sum(v_edges > 30)
    total_pixels = gray.size

    edge_ratio = (strong_h + strong_v) / (2 * total_pixels)

    # Normal buildings: edge_ratio > 0.08
    # Empty lots: edge_ratio < 0.03
    if edge_ratio > 0.08:
        return 0.0
    elif edge_ratio < 0.02:
        return 1.0
    else:
        return max(0.0, 1.0 - (edge_ratio - 0.02) / 0.06)


def analyze_brightness(img_array: np.ndarray) -> float:
    """
    Very dark or very washed out images can indicate poor property condition
    or boarded-up structures. Returns a mild signal.
    """
    brightness = np.mean(img_array)
    # Normal range: 80-180
    if 80 <= brightness <= 180:
        return 0.0
    elif brightness < 50 or brightness > 220:
        return 0.5
    else:
        return 0.2


def analyze_satellite_coverage(sat_array: np.ndarray) -> float:
    """
    Analyze satellite imagery for signs of vacancy:
    - Lots with no visible roof structure
    - Heavy tree canopy over property (potential overgrowth)
    - Visible dirt/bare ground (potential demolition)
    """
    r, g, b = sat_array[:, :, 0], sat_array[:, :, 1], sat_array[:, :, 2]

    # Detect brown/bare ground
    brown_mask = (r > g) & (r > b) & (r > 100) & (g > 60) & (g < r - 20)
    brown_ratio = np.sum(brown_mask) / brown_mask.size

    # Detect dense canopy (very green)
    canopy_mask = (g > r + 20) & (g > b + 20) & (g > 80)
    canopy_ratio = np.sum(canopy_mask) / canopy_mask.size

    # Detect roof-like surfaces (gray, consistent color)
    gray_mask = (np.abs(r.astype(float) - g.astype(float)) < 20) & \
                (np.abs(g.astype(float) - b.astype(float)) < 20) & \
                (r > 60) & (r < 200)
    gray_ratio = np.sum(gray_mask) / gray_mask.size

    # High brown + low gray suggests demolished lot
    if brown_ratio > 0.3 and gray_ratio < 0.15:
        return 0.8
    # Very high canopy suggests overgrown/abandoned
    elif canopy_ratio > 0.6:
        return 0.6
    else:
        return max(0.0, brown_ratio * 0.5 + max(0, canopy_ratio - 0.3) * 0.5)


def detect_property_condition(
    streetview_path: Optional[str] = None,
    satellite_path: Optional[str] = None,
) -> DetectionResult:
    """
    Run all analysis on available imagery and produce a composite score.
    """
    signals = {}
    weights = {}

    # Analyze Street View if available
    if streetview_path and Path(streetview_path).exists():
        try:
            with Image.open(streetview_path) as img:
                sv_array = np.array(img.convert("RGB"))

            signals["color_variance"] = analyze_color_variance(sv_array)
            signals["green_coverage"] = analyze_green_coverage(sv_array)
            signals["edge_density"] = analyze_edge_density(sv_array)
            signals["brightness"] = analyze_brightness(sv_array)

            # Street View signals are weighted more heavily
            weights["color_variance"] = 0.2
            weights["green_coverage"] = 0.25
            weights["edge_density"] = 0.3
            weights["brightness"] = 0.05
        except Exception as e:
            signals["streetview_error"] = str(e)

    # Analyze satellite if available
    if satellite_path and Path(satellite_path).exists():
        try:
            with Image.open(satellite_path) as img:
                sat_array = np.array(img.convert("RGB"))

            signals["satellite_coverage"] = analyze_satellite_coverage(sat_array)
            weights["satellite_coverage"] = 0.2
        except Exception as e:
            signals["satellite_error"] = str(e)

    # Calculate composite score
    if not weights:
        return DetectionResult(
            score=0.0,
            label="unprocessed",
            details={"reason": "No imagery available for analysis"},
        )

    # Normalize weights
    total_weight = sum(weights.values())
    composite = sum(
        signals.get(k, 0) * (w / total_weight)
        for k, w in weights.items()
    )

    # Determine label
    if composite >= DEMOLITION_THRESHOLD:
        label = "likely_demolished"
    elif composite >= VACANCY_THRESHOLD:
        label = "likely_vacant"
    else:
        label = "likely_occupied"

    # Build details for transparency
    details = {
        "composite_score": round(composite, 3),
        "signals": {k: round(v, 3) for k, v in signals.items() if isinstance(v, (int, float))},
        "weights": {k: round(v, 3) for k, v in weights.items()},
        "thresholds": {
            "vacancy": VACANCY_THRESHOLD,
            "demolition": DEMOLITION_THRESHOLD,
        },
    }

    return DetectionResult(
        score=round(composite, 3),
        label=label,
        details=details,
    )


async def batch_detect(
    properties: list[dict],
    workers: int = DETECTION_WORKERS,
    on_result=None,
) -> dict[int, DetectionResult]:
    """
    Run detection on multiple properties.
    Each dict should have: id, streetview_path, satellite_path.
    Uses process-based parallelism for CPU-bound analysis.
    """
    if not properties:
        return {}

    worker_count = max(1, min(workers, len(properties), os.cpu_count() or 1))
    loop = asyncio.get_running_loop()
    results = {}
    with ProcessPoolExecutor(max_workers=worker_count) as pool:
        tasks = [
            loop.run_in_executor(pool, detect_property_condition_worker, prop)
            for prop in properties
        ]
        total = len(tasks)
        for current, task in enumerate(asyncio.as_completed(tasks), start=1):
            prop_id, score, label, details = await task
            result = DetectionResult(score=score, label=label, details=details)
            results[prop_id] = result
            if on_result:
                maybe_coro = on_result(prop_id, result, current, total)
                if asyncio.iscoroutine(maybe_coro):
                    await maybe_coro

    return results


def detect_property_condition_worker(prop: dict) -> tuple[int, float, str, dict]:
    """
    Process-safe worker wrapper (top-level for macOS spawn compatibility).
    """
    result = detect_property_condition(
        streetview_path=prop.get("streetview_path"),
        satellite_path=prop.get("satellite_path"),
    )
    return prop["id"], result.score, result.label, result.details
