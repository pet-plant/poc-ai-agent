"""Deterministic Event Engine rules for triggering Care Advice (Zero LLM)."""

from typing import Optional
from plant_poc.config import CONFIDENCE_THRESHOLD
from plant_poc.schemas import (
    VLMObservation,
    TriggerDecision,
    TriggerResult,
    HealthStatus,
)

SEVERITY_RANKS = {
    "mild": 1,
    "moderate": 2,
    "severe": 3,
}

HEALTH_STATUS_RANKS = {
    HealthStatus.HEALTHY: 1,
    HealthStatus.POSSIBLY_UNHEALTHY: 2,
    HealthStatus.UNHEALTHY: 3,
}


def evaluate(
    new: VLMObservation,
    previous: Optional[VLMObservation] = None,
    confidence_threshold: float = CONFIDENCE_THRESHOLD,
) -> TriggerResult:
    """Evaluate whether an observation requires care advice, more info, or no action.

    Deterministic logic per PRD §4.2:
    1. Overall observation confidence < threshold -> REQUEST_MORE_INFORMATION
    2. If first observation (no previous):
       - If healthy with no symptoms -> NO_ACTION
       - Else -> CARE_ADVICE_REQUIRED
    3. If any symptom observation has confidence < threshold -> REQUEST_MORE_INFORMATION
    4. If health_status changed to worse rank -> CARE_ADVICE_REQUIRED
    5. If a new observation symptom type appeared -> CARE_ADVICE_REQUIRED
    6. If severity of a matching symptom type increased -> CARE_ADVICE_REQUIRED
    7. Otherwise (improvement, steady state, or minor variations) -> NO_ACTION
    """
    # 1. Low confidence check on overall observation
    if new.confidence < confidence_threshold:
        return TriggerResult(
            decision=TriggerDecision.REQUEST_MORE_INFORMATION,
            reason=f"Overall confidence {new.confidence:.2f} is below threshold {confidence_threshold:.2f}.",
        )

    # 2. Low confidence on any individual symptom
    for obs in new.observations:
        if obs.confidence < confidence_threshold:
            return TriggerResult(
                decision=TriggerDecision.REQUEST_MORE_INFORMATION,
                reason=f"Symptom '{obs.type}' confidence {obs.confidence:.2f} is below threshold {confidence_threshold:.2f}.",
            )

    # 3. First observation check
    if previous is None:
        if new.health_status == HealthStatus.HEALTHY and len(new.observations) == 0:
            return TriggerResult(
                decision=TriggerDecision.NO_ACTION,
                reason="Baseline observation recorded as healthy with no symptoms.",
            )
        return TriggerResult(
            decision=TriggerDecision.CARE_ADVICE_REQUIRED,
            reason="Initial observation detected symptoms or non-healthy status.",
        )

    # 4. Check for health status degradation (worsening)
    new_health_rank = HEALTH_STATUS_RANKS[new.health_status]
    prev_health_rank = HEALTH_STATUS_RANKS[previous.health_status]
    if new_health_rank > prev_health_rank:
        return TriggerResult(
            decision=TriggerDecision.CARE_ADVICE_REQUIRED,
            reason=f"Health status worsened from {previous.health_status.value} to {new.health_status.value}.",
        )

    # 5. Check for new symptom type that was not present previously
    prev_symptoms_by_type = {obs.type: obs for obs in previous.observations}
    for new_obs in new.observations:
        if new_obs.type not in prev_symptoms_by_type:
            return TriggerResult(
                decision=TriggerDecision.CARE_ADVICE_REQUIRED,
                reason=f"New symptom '{new_obs.type}' appeared (severity: {new_obs.severity}).",
            )

    # 6. Check for severity escalation of existing symptoms
    for new_obs in new.observations:
        prev_obs = prev_symptoms_by_type[new_obs.type]
        new_rank = SEVERITY_RANKS.get(new_obs.severity, 0)
        prev_rank = SEVERITY_RANKS.get(prev_obs.severity, 0)
        if new_rank > prev_rank:
            return TriggerResult(
                decision=TriggerDecision.CARE_ADVICE_REQUIRED,
                reason=f"Severity of symptom '{new_obs.type}' increased from {prev_obs.severity} to {new_obs.severity}.",
            )

    # 7. Check if health_status changed to better, or symptoms improved / remained steady
    if new_health_rank < prev_health_rank:
        return TriggerResult(
            decision=TriggerDecision.NO_ACTION,
            reason=f"Health status improved from {previous.health_status.value} to {new.health_status.value}.",
        )

    # 8. Otherwise: steady state / no change
    return TriggerResult(
        decision=TriggerDecision.NO_ACTION,
        reason="No new symptoms, no severity increase, and health status is stable.",
    )
