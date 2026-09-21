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


def test_pipeline_process_vlm_probe_result():
    mock_client = MockLLMClient(
        canned_responses=[
            LLMResponse(
                content="""{
                    "plant_id": "plant-monstera-probe",
                    "assessment": "Underwatering causing leaf drooping and brown tips.",
                    "confidence": 0.95,
                    "actions": [
                        {"action": "Deep soak watering immediately.", "priority": 1}
                    ]
                }"""
            )
        ]
    )
    pipeline = PlantPipeline.create_default(llm_client=mock_client)

    probe_payload = {
        "timestamp": "2026-09-21T14:00:00",
        "confidence": {
            "agreement": 1.0,
            "runs": 5,
            "model_stated_average": 0.95,
        },
        "severity": 2,
        "verdict": "worse",
        "observation": {
            "leaf_posture": "drooping downwards",
            "leaf_color": "dark green with crisp margins",
            "visible_damage": "dry tips and brown edges on foliage",
            "visible_stress_level": "moderate",
        },
    }

    result = pipeline.process_vlm_probe_result(
        probe_data=probe_payload,
        plant_id="plant-monstera-probe",
        species="Monstera deliciosa",
    )

    assert result.trigger_result.decision == TriggerDecision.CARE_ADVICE_REQUIRED
    assert result.care_plan is not None
    assert result.care_plan.assessment == "Underwatering causing leaf drooping and brown tips."
    assert result.companion_message is not None

    # Verify saved to database and retrieved
    prev_obs = pipeline.registry.get_previous_observation("plant-monstera-probe")
    assert prev_obs is not None
    assert prev_obs.consensus is not None
    assert prev_obs.consensus.agreement == 1.0
    assert prev_obs.leaf_posture == "drooping downwards"
