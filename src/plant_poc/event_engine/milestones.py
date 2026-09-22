"""Deterministic milestone detection engine for major plant life events."""

from typing import Optional
from plant_poc.schemas import (
    VLMObservation,
    HealthStatus,
    PlantMilestone,
    MilestoneType,
)


def detect_milestones(
    new_obs: VLMObservation,
    history: list[VLMObservation],
    existing_milestones: list[PlantMilestone],
) -> list[PlantMilestone]:
    """Evaluate observation trajectory to detect new episodic milestones.

    Args:
        new_obs: The incoming observation for today.
        history: Chronological list of past observations for this plant (oldest to newest).
        existing_milestones: All historical milestones recorded for this plant.

    Returns:
        List of newly detected PlantMilestone objects to be recorded.
    """
    newly_detected: list[PlantMilestone] = []
    recorded_types = {m.event_type for m in existing_milestones}

    # 1. FIRST_SYMPTOM: First time symptoms appear on this plant
    has_symptoms = len(new_obs.observations) > 0 or new_obs.health_status != HealthStatus.HEALTHY
    if has_symptoms and MilestoneType.FIRST_SYMPTOM not in recorded_types:
        symptom_names = ", ".join(o.type for o in new_obs.observations) if new_obs.observations else "declining health"
        newly_detected.append(
            PlantMilestone(
                plant_id=new_obs.plant_id,
                timestamp=new_obs.timestamp,
                event_type=MilestoneType.FIRST_SYMPTOM,
                description=f"First health symptoms detected: {symptom_names}.",
            )
        )

    # 2. HEALTH_CRISIS: Drops into UNHEALTHY status
    prev_obs = history[-1] if history else None
    prev_was_unhealthy = prev_obs is not None and prev_obs.health_status == HealthStatus.UNHEALTHY
    is_now_unhealthy = new_obs.health_status == HealthStatus.UNHEALTHY

    if is_now_unhealthy and not prev_was_unhealthy:
        newly_detected.append(
            PlantMilestone(
                plant_id=new_obs.plant_id,
                timestamp=new_obs.timestamp,
                event_type=MilestoneType.HEALTH_CRISIS,
                description=f"Entered critical unhealthy state at {new_obs.timestamp.date()}.",
            )
        )

    # Calculate consecutive unhealthy streak ending with new_obs
    streak = 0
    if is_now_unhealthy:
        streak = 1
        for past_obs in reversed(history):
            if past_obs.health_status == HealthStatus.UNHEALTHY:
                streak += 1
            else:
                break

    # 3. SEVERE_EPISODE: 3 consecutive days UNHEALTHY
    if streak >= 3:
        # Check if severe_episode was already recorded for this continuous streak
        # (Look for any severe_episode recorded on or after the most recent health_crisis)
        latest_crisis_ts = max(
            (m.timestamp for m in existing_milestones if m.event_type == MilestoneType.HEALTH_CRISIS),
            default=None,
        )
        already_recorded_this_streak = any(
            m.event_type == MilestoneType.SEVERE_EPISODE
            and (latest_crisis_ts is None or m.timestamp >= latest_crisis_ts)
            for m in existing_milestones + newly_detected
        )
        if not already_recorded_this_streak:
            newly_detected.append(
                PlantMilestone(
                    plant_id=new_obs.plant_id,
                    timestamp=new_obs.timestamp,
                    event_type=MilestoneType.SEVERE_EPISODE,
                    description=f"Persistent severe health crisis for {streak} consecutive days.",
                )
            )

    # 4. NEAR_DEATH: 7 consecutive days UNHEALTHY
    if streak >= 7:
        already_recorded_near_death = any(
            m.event_type == MilestoneType.NEAR_DEATH
            and (latest_crisis_ts is None or m.timestamp >= latest_crisis_ts)
            for m in existing_milestones + newly_detected
        )
        if not already_recorded_near_death:
            newly_detected.append(
                PlantMilestone(
                    plant_id=new_obs.plant_id,
                    timestamp=new_obs.timestamp,
                    event_type=MilestoneType.NEAR_DEATH,
                    description=f"Critical near-death condition: unresolved unhealthy state for {streak} days.",
                )
            )

    # 5. FULL_RECOVERY: Transitions back to HEALTHY after a crisis
    is_now_healthy = new_obs.health_status == HealthStatus.HEALTHY
    was_sick = prev_obs is not None and prev_obs.health_status in (
        HealthStatus.UNHEALTHY,
        HealthStatus.POSSIBLY_UNHEALTHY,
    )
    had_crisis = any(
        m.event_type in (MilestoneType.HEALTH_CRISIS, MilestoneType.SEVERE_EPISODE)
        for m in existing_milestones
    )
    # Check if a recovery hasn't already been recorded since the last crisis
    if is_now_healthy and was_sick and had_crisis:
        last_crisis_ts = max(
            (m.timestamp for m in existing_milestones if m.event_type in (MilestoneType.HEALTH_CRISIS, MilestoneType.SEVERE_EPISODE)),
            default=None,
        )
        last_recovery_ts = max(
            (m.timestamp for m in existing_milestones if m.event_type == MilestoneType.FULL_RECOVERY),
            default=None,
        )
        if last_crisis_ts and (last_recovery_ts is None or last_crisis_ts > last_recovery_ts):
            newly_detected.append(
                PlantMilestone(
                    plant_id=new_obs.plant_id,
                    timestamp=new_obs.timestamp,
                    event_type=MilestoneType.FULL_RECOVERY,
                    description=f"Full recovery back to healthy status on {new_obs.timestamp.date()}.",
                    resolved_at=new_obs.timestamp,
                )
            )

    return newly_detected
