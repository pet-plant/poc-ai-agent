"""VLM Adapter — transforms VLM PROBE RESULT output into VLMObservation."""

from datetime import datetime, timezone
from typing import Optional

from plant_poc.schemas import (
    HealthStatus,
    Observation,
    VLMConsensus,
    VLMObservation,
)


class VLMAdapterError(Exception):
    """Raised when VLM probe result payload is invalid or missing required fields."""


# Maps VLM health_status string to HealthStatus enum
_HEALTH_STATUS_MAP: dict[str, HealthStatus] = {
    "healthy": HealthStatus.HEALTHY,
    "possibly_unhealthy": HealthStatus.POSSIBLY_UNHEALTHY,
    "unhealthy": HealthStatus.UNHEALTHY,
}


def _parse_timestamp(ts_val: Optional[str]) -> datetime:
    """Parse ISO-8601 string or return current timestamp if missing."""
    if not ts_val:
        return datetime.now(timezone.utc)
    try:
        return datetime.fromisoformat(ts_val)
    except (ValueError, TypeError) as e:
        raise VLMAdapterError(f"Invalid timestamp format '{ts_val}': {e}") from e


def _build_consensus(consensus_data: Optional[dict]) -> Optional[VLMConsensus]:
    """Build VLMConsensus from consensus block."""
    if not consensus_data or not isinstance(consensus_data, dict):
        return None

    agreement = consensus_data.get("agreement")
    runs = consensus_data.get("runs")
    if agreement is None or runs is None:
        return None

    model_stated_avg = consensus_data.get("model_stated_average", 0.95)

    return VLMConsensus(
        agreement=float(agreement),
        runs=int(runs),
        model_stated_average=float(model_stated_avg),
    )


def _parse_observations(raw_observations: list) -> list[Observation]:
    """Parse pre-structured observation dicts from VLM into Observation models."""
    observations: list[Observation] = []
    for obs_dict in raw_observations:
        if not isinstance(obs_dict, dict):
            continue
        obs_type = obs_dict.get("type")
        severity = obs_dict.get("severity")
        description = obs_dict.get("description", "")
        if obs_type and severity:
            observations.append(
                Observation(type=obs_type, severity=severity, description=description)
            )
    return observations


def parse_vlm_probe_result(
    data: dict,
    plant_id: str,
    species: Optional[str] = None,
    timestamp: Optional[datetime] = None,
) -> VLMObservation:
    """Transform a VLM PROBE RESULT dictionary into a VLMObservation.

    Args:
        data: The PROBE RESULT dict provided by the VLM pipeline.
        plant_id: Target plant identifier.
        species: Optional plant species.
        timestamp: Optional timestamp override. If None, parsed from `data['timestamp']`.

    Returns:
        VLMObservation with consensus metadata and structured observations.

    Raises:
        VLMAdapterError: If data is not a dict or missing critical structure.
    """
    if not isinstance(data, dict):
        raise VLMAdapterError(f"Expected dict for VLM probe result, got {type(data).__name__}")

    # 1. Resolve timestamp
    if timestamp is None:
        raw_ts = data.get("timestamp")
        timestamp = _parse_timestamp(raw_ts)

    # 2. Extract health status
    health_str = data.get("health_status", "healthy").lower()
    health_status = _HEALTH_STATUS_MAP.get(health_str, HealthStatus.HEALTHY)

    # 3. Extract consensus metadata
    consensus = _build_consensus(data.get("consensus"))

    # 4. Extract structured observations (pre-structured from VLM)
    raw_observations = data.get("observations", [])
    if not isinstance(raw_observations, list):
        raw_observations = []
    observations = _parse_observations(raw_observations)

    # 5. Extract image references
    image_refs = data.get("image_refs", [])
    if not isinstance(image_refs, list):
        image_refs = []

    # 6. Extract or derive overall description
    description = data.get("description")
    if not description and observations:
        description = " | ".join(
            f"{o.type}: {o.description}" if o.description else o.type
            for o in observations
        )

    return VLMObservation(
        plant_id=plant_id,
        species=species,
        timestamp=timestamp,
        health_status=health_status,
        observations=observations,
        consensus=consensus,
        image_refs=image_refs,
        description=description,
    )
