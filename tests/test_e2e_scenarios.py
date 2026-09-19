"""End-to-end scenario verification against PRD §3 acceptance criteria."""

import json
import pytest
from plant_poc.config import SCENARIOS_DIR
from plant_poc.llm import MockLLMClient, LLMResponse
from plant_poc.orchestration import PlantPipeline
from plant_poc.schemas import TriggerDecision, VLMObservation

EXPECTED_TRIGGERS_MAP = {
    "no_change.json": [TriggerDecision.NO_ACTION, TriggerDecision.NO_ACTION],
    "new_symptom.json": [TriggerDecision.NO_ACTION, TriggerDecision.CARE_ADVICE_REQUIRED],
    "health_status_change.json": [TriggerDecision.NO_ACTION, TriggerDecision.CARE_ADVICE_REQUIRED],
    "severity_increase.json": [TriggerDecision.CARE_ADVICE_REQUIRED, TriggerDecision.CARE_ADVICE_REQUIRED],
    "low_confidence.json": [TriggerDecision.NO_ACTION, TriggerDecision.REQUEST_MORE_INFORMATION],
    "improvement.json": [TriggerDecision.CARE_ADVICE_REQUIRED, TriggerDecision.NO_ACTION],
    "mixed_multiday.json": [
        TriggerDecision.NO_ACTION,
        TriggerDecision.CARE_ADVICE_REQUIRED,
        TriggerDecision.CARE_ADVICE_REQUIRED,
        TriggerDecision.NO_ACTION,
        TriggerDecision.REQUEST_MORE_INFORMATION,
    ],
}


@pytest.mark.parametrize("scenario_file,expected_decisions", EXPECTED_TRIGGERS_MAP.items())
def test_e2e_scenario_triggers_match_prd_spec(scenario_file, expected_decisions):
    # Setup offline mock client to verify pipeline logic quickly and deterministically
    mock_client = MockLLMClient(
        canned_responses=[
            LLMResponse(
                content="""{
                    "plant_id": "plant-monstera-1",
                    "assessment": "Overwatering stress detected.",
                    "confidence": 0.88,
                    "actions": [{"action": "Check soil moisture.", "priority": 1}]
                }"""
            )
            for _ in range(10)
        ]
    )
    pipeline = PlantPipeline.create_default(llm_client=mock_client)

    path = SCENARIOS_DIR / scenario_file
    with open(path) as f:
        data = json.load(f)
    observations = [VLMObservation.model_validate(o) for o in data["observations"]]

    results = pipeline.run_scenario(observations)
    assert len(results) == len(expected_decisions)

    for day_idx, (res, expected) in enumerate(zip(results, expected_decisions), start=1):
        actual = res.trigger_result.decision
        assert actual == expected, (
            f"Scenario '{scenario_file}' Day {day_idx} expected {expected.value}, but got {actual.value}. "
            f"Reason: {res.trigger_result.reason}"
        )
        if expected == TriggerDecision.CARE_ADVICE_REQUIRED:
            assert res.care_plan is not None
            assert res.companion_message is not None
        else:
            assert res.care_plan is None
