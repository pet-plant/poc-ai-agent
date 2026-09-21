import json
from pathlib import Path
import pytest
from plant_poc.config import SCENARIOS_DIR
from plant_poc.event_engine import evaluate
from plant_poc.schemas import VLMObservation, TriggerDecision


def load_scenario(filename: str) -> list[VLMObservation]:
    with open(SCENARIOS_DIR / filename) as f:
        data = json.load(f)
    return [VLMObservation.model_validate(o) for o in data["observations"]]


def test_scenario_no_change():
    obs_list = load_scenario("no_change.json")
    assert len(obs_list) == 2
    # Day 1: baseline healthy
    result_day1 = evaluate(obs_list[0], previous=None)
    assert result_day1.decision == TriggerDecision.NO_ACTION

    # Day 2: same healthy, same symptoms
    result_day2 = evaluate(obs_list[1], previous=obs_list[0])
    assert result_day2.decision == TriggerDecision.NO_ACTION


def test_scenario_new_symptom():
    obs_list = load_scenario("new_symptom.json")
    result = evaluate(obs_list[1], previous=obs_list[0])
    assert result.decision == TriggerDecision.CARE_ADVICE_REQUIRED
    assert "New symptom" in result.reason or "worsened" in result.reason


def test_scenario_health_status_change():
    obs_list = load_scenario("health_status_change.json")
    result = evaluate(obs_list[1], previous=obs_list[0])
    assert result.decision == TriggerDecision.CARE_ADVICE_REQUIRED
    assert "Health status worsened" in result.reason


def test_scenario_severity_increase():
    obs_list = load_scenario("severity_increase.json")
    result = evaluate(obs_list[1], previous=obs_list[0])
    assert result.decision == TriggerDecision.CARE_ADVICE_REQUIRED
    assert "Severity of symptom" in result.reason or "worsened" in result.reason


def test_scenario_low_confidence():
    obs_list = load_scenario("low_confidence.json")
    result = evaluate(obs_list[1], previous=obs_list[0])
    assert result.decision == TriggerDecision.REQUEST_MORE_INFORMATION


def test_scenario_improvement():
    obs_list = load_scenario("improvement.json")
    result = evaluate(obs_list[1], previous=obs_list[0])
    assert result.decision == TriggerDecision.NO_ACTION
    assert "improved" in result.reason.lower() or "stable" in result.reason.lower()


def test_scenario_mixed_multiday():
    obs_list = load_scenario("mixed_multiday.json")
    assert len(obs_list) == 5

    # Day 1: baseline healthy
    res1 = evaluate(obs_list[0], None)
    assert res1.decision == TriggerDecision.NO_ACTION

    # Day 2: new mild yellowing symptom
    res2 = evaluate(obs_list[1], obs_list[0])
    assert res2.decision == TriggerDecision.CARE_ADVICE_REQUIRED

    # Day 3: severity increase to severe
    res3 = evaluate(obs_list[2], obs_list[1])
    assert res3.decision == TriggerDecision.CARE_ADVICE_REQUIRED

    # Day 4: improvement back to mild
    res4 = evaluate(obs_list[3], obs_list[2])
    assert res4.decision == TriggerDecision.NO_ACTION

    # Day 5: low confidence
    res5 = evaluate(obs_list[4], obs_list[3])
    assert res5.decision == TriggerDecision.REQUEST_MORE_INFORMATION


def test_consensus_agreement_below_threshold():
    from datetime import datetime
    from plant_poc.schemas import HealthStatus, VLMObservation, VLMConsensus

    obs = VLMObservation(
        plant_id="plant-1",
        timestamp=datetime.now(),
        health_status=HealthStatus.HEALTHY,
        confidence=0.95,
        consensus=VLMConsensus(agreement=0.6, runs=5, model_stated_average=0.95),
    )

    result = evaluate(obs, None, confidence_threshold=0.7)
    assert result.decision == TriggerDecision.REQUEST_MORE_INFORMATION
    assert "VLM agreement 0.60 is below threshold 0.70" in result.reason


def test_consensus_agreement_above_threshold_healthy():
    from datetime import datetime
    from plant_poc.schemas import HealthStatus, VLMObservation, VLMConsensus

    obs = VLMObservation(
        plant_id="plant-1",
        timestamp=datetime.now(),
        health_status=HealthStatus.HEALTHY,
        confidence=0.95,
        consensus=VLMConsensus(agreement=1.0, runs=5, model_stated_average=0.95),
    )

    result = evaluate(obs, None, confidence_threshold=0.7)
    assert result.decision == TriggerDecision.NO_ACTION


def test_missing_consensus_with_require_consensus():
    from datetime import datetime
    from plant_poc.schemas import HealthStatus, VLMObservation

    obs = VLMObservation(
        plant_id="plant-1",
        timestamp=datetime.now(),
        health_status=HealthStatus.HEALTHY,
        confidence=0.95,
        consensus=None,
    )

    result = evaluate(obs, None, require_consensus=True)
    assert result.decision == TriggerDecision.REQUEST_MORE_INFORMATION
    assert "VLM is not available for the moment." in result.reason
