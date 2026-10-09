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
        observations=[
            Observation(
                type="leaf_yellowing",
                severity="mild",
                description="slight yellowing on tip",
            )
        ],
    )
    assert obs.plant_id == "plant-1"
    assert obs.health_status == HealthStatus.HEALTHY
    assert len(obs.observations) == 1
    assert obs.observations[0].severity == "mild"
    assert obs.observations[0].description == "slight yellowing on tip"
    assert obs.effective_confidence == 0.9


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
