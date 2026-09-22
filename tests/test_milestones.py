"""Unit tests for deterministic milestone detection engine."""

from datetime import datetime, timedelta
import pytest

from plant_poc.schemas import (
    VLMObservation,
    HealthStatus,
    Observation,
    MilestoneType,
    PlantMilestone,
)
from plant_poc.event_engine.milestones import detect_milestones


def make_obs(
    day: int,
    health: HealthStatus,
    symptoms: list[str] = None,
    plant_id: str = "plant-1",
) -> VLMObservation:
    ts = datetime(2026, 9, 1) + timedelta(days=day)
    obs_list = [Observation(type=s, severity="moderate", confidence=0.9) for s in (symptoms or [])]
    return VLMObservation(
        plant_id=plant_id,
        timestamp=ts,
        health_status=health,
        confidence=0.95,
        observations=obs_list,
    )


def test_first_symptom_detection():
    obs1 = make_obs(1, HealthStatus.HEALTHY)
    m1 = detect_milestones(obs1, history=[], existing_milestones=[])
    assert len(m1) == 0

    obs2 = make_obs(2, HealthStatus.POSSIBLY_UNHEALTHY, symptoms=["leaf_yellowing"])
    m2 = detect_milestones(obs2, history=[obs1], existing_milestones=[])
    assert len(m2) == 1
    assert m2[0].event_type == MilestoneType.FIRST_SYMPTOM

    # Second day with symptoms should NOT trigger first_symptom again
    m3 = detect_milestones(obs2, history=[obs1, obs2], existing_milestones=m2)
    assert len(m3) == 0


def test_health_crisis_detection():
    obs1 = make_obs(1, HealthStatus.HEALTHY)
    obs2 = make_obs(2, HealthStatus.UNHEALTHY, symptoms=["root_rot"])

    m = detect_milestones(obs2, history=[obs1], existing_milestones=[])
    types = {x.event_type for x in m}
    assert MilestoneType.HEALTH_CRISIS in types
    assert MilestoneType.FIRST_SYMPTOM in types


def test_severe_episode_at_3_consecutive_days():
    obs1 = make_obs(1, HealthStatus.UNHEALTHY)
    m1 = detect_milestones(obs1, history=[], existing_milestones=[])

    obs2 = make_obs(2, HealthStatus.UNHEALTHY)
    m2 = detect_milestones(obs2, history=[obs1], existing_milestones=m1)
    assert not any(x.event_type == MilestoneType.SEVERE_EPISODE for x in m2)

    obs3 = make_obs(3, HealthStatus.UNHEALTHY)
    m3 = detect_milestones(obs3, history=[obs1, obs2], existing_milestones=m1 + m2)
    assert any(x.event_type == MilestoneType.SEVERE_EPISODE for x in m3)

    # Day 4: still unhealthy, but severe_episode should NOT duplicate
    obs4 = make_obs(4, HealthStatus.UNHEALTHY)
    m4 = detect_milestones(obs4, history=[obs1, obs2, obs3], existing_milestones=m1 + m2 + m3)
    assert not any(x.event_type == MilestoneType.SEVERE_EPISODE for x in m4)


def test_near_death_at_7_consecutive_days():
    history = [make_obs(i, HealthStatus.UNHEALTHY) for i in range(1, 7)]
    milestones = [
        PlantMilestone(
            plant_id="plant-1",
            timestamp=datetime(2026, 9, 1),
            event_type=MilestoneType.HEALTH_CRISIS,
            description="Crisis",
        ),
        PlantMilestone(
            plant_id="plant-1",
            timestamp=datetime(2026, 9, 3),
            event_type=MilestoneType.SEVERE_EPISODE,
            description="Severe episode",
        ),
    ]

    obs7 = make_obs(7, HealthStatus.UNHEALTHY)
    m7 = detect_milestones(obs7, history=history, existing_milestones=milestones)
    assert any(x.event_type == MilestoneType.NEAR_DEATH for x in m7)


def test_full_recovery_after_crisis():
    obs1 = make_obs(1, HealthStatus.HEALTHY)
    obs2 = make_obs(2, HealthStatus.UNHEALTHY, symptoms=["root_rot"])
    crisis_milestones = [
        PlantMilestone(
            plant_id="plant-1",
            timestamp=datetime(2026, 9, 2),
            event_type=MilestoneType.HEALTH_CRISIS,
            description="Crisis",
        )
    ]

    obs3 = make_obs(3, HealthStatus.HEALTHY)
    m3 = detect_milestones(obs3, history=[obs1, obs2], existing_milestones=crisis_milestones)
    assert any(x.event_type == MilestoneType.FULL_RECOVERY for x in m3)
    recovery_milestone = next(x for x in m3 if x.event_type == MilestoneType.FULL_RECOVERY)
    assert recovery_milestone.resolved_at is not None
