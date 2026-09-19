from datetime import datetime, timezone
import pytest
from plant_poc.schemas import (
    VLMObservation,
    Observation,
    HealthStatus,
    CarePlan,
    CareAction,
    TriggerDecision,
    TriggerResult,
    KnowledgeChunk,
)


def test_vlm_observation_validation():
    obs = VLMObservation(
        plant_id="plant-1",
        timestamp=datetime.now(timezone.utc),
        health_status=HealthStatus.HEALTHY,
        confidence=0.95,
        observations=[
            Observation(type="leaf_yellowing", severity="mild", confidence=0.88)
        ],
    )
    assert obs.plant_id == "plant-1"
    assert obs.health_status == HealthStatus.HEALTHY
    assert len(obs.observations) == 1
    assert obs.observations[0].severity == "mild"


def test_care_plan_validation():
    plan = CarePlan(
        plant_id="plant-1",
        assessment="Possible early overwatering.",
        confidence=0.85,
        actions=[
            CareAction(action="Check soil moisture 2 inches down.", priority=1),
            CareAction(action="Allow soil to dry out before watering again.", priority=2),
        ],
    )
    assert len(plan.actions) == 2
    assert plan.actions[0].priority == 1
