import json
import pytest
from plant_poc.orchestration import PlantPipeline
from plant_poc.llm import MockLLMClient, LLMResponse
from plant_poc.schemas import TriggerDecision, VLMObservation
from plant_poc.config import SCENARIOS_DIR


def test_pipeline_runs_no_change_scenario_without_calling_llm():
    # In no_change, LLM should never be called
    mock_client = MockLLMClient(canned_responses=[])
    pipeline = PlantPipeline.create_default(llm_client=mock_client)

    with open(SCENARIOS_DIR / "no_change.json") as f:
        data = json.load(f)
    observations = [VLMObservation.model_validate(o) for o in data["observations"]]

    results = pipeline.run_scenario(observations)
    assert len(results) == 2
    assert results[0].trigger_result.decision == TriggerDecision.NO_ACTION
    assert results[0].care_plan is None

    assert results[1].trigger_result.decision == TriggerDecision.NO_ACTION
    assert results[1].care_plan is None

    # Verify zero LLM calls
    assert len(mock_client.call_history) == 0


def test_pipeline_runs_new_symptom_scenario():
    # Day 1: NO_ACTION (healthy baseline)
    # Day 2: CARE_ADVICE_REQUIRED -> triggers Care Advisor & Companion
    mock_client = MockLLMClient(
        canned_responses=[
            LLMResponse(
                content="""{
                    "plant_id": "plant-monstera-1",
                    "assessment": "Early leaf yellowing due to overwatering.",
                    "confidence": 0.90,
                    "actions": [
                        {"action": "Check soil moisture before watering.", "priority": 1}
                    ]
                }"""
            )
        ]
    )
    pipeline = PlantPipeline.create_default(llm_client=mock_client)

    with open(SCENARIOS_DIR / "new_symptom.json") as f:
        data = json.load(f)
    observations = [VLMObservation.model_validate(o) for o in data["observations"]]

    results = pipeline.run_scenario(observations)
    assert len(results) == 2

    # Day 1
    assert results[0].trigger_result.decision == TriggerDecision.NO_ACTION
    assert results[0].care_plan is None

    # Day 2
    assert results[1].trigger_result.decision == TriggerDecision.CARE_ADVICE_REQUIRED
    assert results[1].care_plan is not None
    assert results[1].care_plan.assessment == "Early leaf yellowing due to overwatering."
    assert results[1].companion_message is not None
    assert "Check soil moisture before watering." in results[1].companion_message
    assert len(mock_client.call_history) == 1
