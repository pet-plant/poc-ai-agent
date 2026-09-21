"""VLM Adapter — transforms aggregated VLM PROBE RESULT output into enriched VLMObservation."""

import re
from datetime import datetime
from typing import Optional

from plant_poc.schemas import (
    HealthStatus,
    Observation,
    VLMConsensus,
    VLMObservation,
)


class VLMAdapterError(Exception):
    """Raised when VLM probe result payload is invalid or missing required fields."""


# Maps VLM visible_stress_level string to HealthStatus
_STRESS_TO_HEALTH: dict[str, HealthStatus] = {
    "none": HealthStatus.HEALTHY,
    "mild": HealthStatus.POSSIBLY_UNHEALTHY,
    "moderate": HealthStatus.POSSIBLY_UNHEALTHY,
    "severe": HealthStatus.UNHEALTHY,
}

_STRESS_TO_SEVERITY: dict[str, str] = {
    "mild": "mild",
    "moderate": "moderate",
    "severe": "severe",
}

# Keyword patterns for extracting typed observations from visible_damage text
_DAMAGE_PATTERNS: list[tuple[str, str]] = [
    (r"brown\s*(?:edge|margin)", "brown_edges"),
    (r"dry\s*(?:tip|ness)|crisp", "dry_tips"),
    (r"yellow|chloros", "leaf_yellowing"),
    (r"wilt|limp", "wilting"),
    (r"spot|lesion|necro", "brown_spots"),
    (r"curl", "curling"),
]

# Posture keywords that generate structured observation entries
_POSTURE_PATTERNS: list[tuple[str, str]] = [
    (r"droop|bent|bend", "drooping"),
    (r"wilt|limp", "wilting"),
    (r"curl", "curling"),
]


def _extract_damage_observations(
    damage_text: str,
    stress_level: str,
) -> list[Observation]:
    """Extract typed Observation entries from visible_damage text."""
    if not damage_text or damage_text.lower().strip() in ("none", "no", "none visible", "none visible.", "no visible damage", "no visible damage."):
        return []

    severity = _STRESS_TO_SEVERITY.get(stress_level, "mild")
    seen_types: set[str] = set()
    observations: list[Observation] = []

    for pattern, obs_type in _DAMAGE_PATTERNS:
        if obs_type not in seen_types and re.search(pattern, damage_text, re.IGNORECASE):
            seen_types.add(obs_type)
            observations.append(
                Observation(type=obs_type, severity=severity, confidence=0.9)
            )

    return observations


def _extract_posture_observations(
    posture_text: str,
    stress_level: str,
) -> list[Observation]:
    """Extract typed Observation entries from leaf_posture text."""
    if not posture_text:
        return []

    severity = _STRESS_TO_SEVERITY.get(stress_level, "mild")
    seen_types: set[str] = set()
    observations: list[Observation] = []

    for pattern, obs_type in _POSTURE_PATTERNS:
        if obs_type not in seen_types and re.search(pattern, posture_text, re.IGNORECASE):
            seen_types.add(obs_type)
            observations.append(
                Observation(type=obs_type, severity=severity, confidence=0.9)
            )

    return observations


def _parse_timestamp(ts_val: Optional[str]) -> datetime:
    """Parse ISO-8601 string or return current timestamp if missing."""
    if not ts_val:
        return datetime.now()
    try:
        return datetime.fromisoformat(ts_val)
    except (ValueError, TypeError) as e:
        raise VLMAdapterError(f"Invalid timestamp format '{ts_val}': {e}") from e


def _build_consensus(confidence_data: Optional[dict]) -> Optional[VLMConsensus]:
    """Build VLMConsensus from confidence block."""
    if not confidence_data or not isinstance(confidence_data, dict):
        return None

    agreement = confidence_data.get("agreement")
    runs = confidence_data.get("runs")
    if agreement is None or runs is None:
        return None

    model_stated_avg = confidence_data.get(
        "model_stated_average",
        confidence_data.get("confidence", 0.95),
    )

    return VLMConsensus(
        agreement=float(agreement),
        runs=int(runs),
        model_stated_average=float(model_stated_avg),
    )


def parse_vlm_probe_result(
    data: dict,
    plant_id: str,
    species: Optional[str] = None,
    timestamp: Optional[datetime] = None,
) -> VLMObservation:
    """Transform an aggregated VLM PROBE RESULT dictionary into a VLMObservation.

    Args:
        data: The aggregated PROBE RESULT dict provided by the VLM pipeline.
        plant_id: Target plant identifier.
        species: Optional plant species.
        timestamp: Optional timestamp override. If None, parsed from `data['timestamp']`.

    Returns:
        VLMObservation enriched with consensus metadata, leaf posture, and color detail.

    Raises:
        VLMAdapterError: If data is not a dict or missing critical structure.
    """
    if not isinstance(data, dict):
        raise VLMAdapterError(f"Expected dict for VLM probe result, got {type(data).__name__}")

    # Extract observation block (either nested under "observation" or at root)
    obs_block = data.get("observation")
    if not isinstance(obs_block, dict):
        obs_block = data

    # 1. Resolve timestamp
    if timestamp is None:
        raw_ts = data.get("timestamp")
        timestamp = _parse_timestamp(raw_ts)

    # 2. Extract health status and stress level
    stress_level = obs_block.get("visible_stress_level", "none").lower()
    health_status = _STRESS_TO_HEALTH.get(stress_level, HealthStatus.HEALTHY)

    # 3. Extract posture and color detail
    leaf_posture = obs_block.get("leaf_posture")
    leaf_color_detail = obs_block.get("leaf_color")

    # 4. Extract structured observation entries
    damage_text = obs_block.get("visible_damage", "")
    damage_obs = _extract_damage_observations(damage_text, stress_level)
    posture_obs = _extract_posture_observations(leaf_posture or "", stress_level)

    # Merge observations (damage takes precedence if type overlaps)
    seen_types = {o.type for o in damage_obs}
    all_observations = damage_obs + [o for o in posture_obs if o.type not in seen_types]

    # 5. Extract consensus metadata
    conf_block = data.get("confidence")
    consensus = _build_consensus(conf_block)

    # Effective overall confidence (from consensus or model stated average)
    overall_conf = (
        consensus.model_stated_average
        if consensus is not None
        else float(data.get("confidence", 0.9) if isinstance(data.get("confidence"), (int, float)) else 0.9)
    )

    # 6. Extract image references
    image_refs = data.get("image_refs", [])
    if not isinstance(image_refs, list):
        image_refs = []

    return VLMObservation(
        plant_id=plant_id,
        species=species,
        timestamp=timestamp,
        health_status=health_status,
        confidence=overall_conf,
        observations=all_observations,
        consensus=consensus,
        leaf_posture=leaf_posture,
        leaf_color_detail=leaf_color_detail,
        image_refs=image_refs,
    )
