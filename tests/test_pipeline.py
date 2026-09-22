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


def test_pipeline_low_confidence_does_not_pollute_registry_and_sets_retake():
    """Verify that low-confidence scans trigger retake, never pollute the DB, and use 0 LLM calls."""
    mock_client = MockLLMClient(canned_responses=[])
    pipeline = PlantPipeline.create_default(llm_client=mock_client)

    with open(SCENARIOS_DIR / "low_confidence.json") as f:
        data = json.load(f)
    observations = [VLMObservation.model_validate(o) for o in data["observations"]]

    results = pipeline.run_scenario(observations)
    assert len(results) == 2

    # Day 1: Healthy scan saved to registry
    assert results[0].trigger_result.decision == TriggerDecision.NO_ACTION
    obs_day1 = pipeline.registry.get_previous_observation("plant-monstera-1")
    assert obs_day1 is not None
    assert obs_day1.confidence == 0.90

    # Day 2: Low-confidence scan (< 0.5)
    assert results[1].trigger_result.decision == TriggerDecision.REQUEST_MORE_INFORMATION
    frontend_payload = results[1].to_frontend_dict()
    assert frontend_payload["decision"] == "REQUEST_MORE_INFORMATION"
    assert "blurry or dark" in frontend_payload["companion_message"]

    # CRITICAL: Verify DB still holds Day 1's clean observation, NOT Day 2's blurry scan!
    current_stored_obs = pipeline.registry.get_previous_observation("plant-monstera-1")
    assert current_stored_obs.confidence == 0.90  # Still Day 1 baseline
    assert current_stored_obs.health_status.value == "healthy"

    # Verify zero LLM calls were made
    assert len(mock_client.call_history) == 0


def test_pipeline_milestone_lifecycle_and_two_tier_memory():
    """Verify multi-day progression through first_symptom, health_crisis, severe_episode, and full_recovery."""
    canned_careplan = """{
        "plant_id": "plant-monstera-lifecycle",
        "assessment": "Severe brown spots caused by fungal rot.",
        "confidence": 0.92,
        "actions": [
            {"action": "Trim affected foliage and treat with bio-fungicide.", "priority": 1},
            {"action": "Isolate from nearby plants.", "priority": 2}
        ]
    }"""
    mock_client = MockLLMClient(
        canned_responses=[
            LLMResponse(content=canned_careplan),
            LLMResponse(content=canned_careplan),
            LLMResponse(content=canned_careplan),
            LLMResponse(content=canned_careplan),
        ]
    )
    pipeline = PlantPipeline.create_default(llm_client=mock_client)

    with open(SCENARIOS_DIR / "milestone_lifecycle.json") as f:
        data = json.load(f)
    observations = [VLMObservation.model_validate(o) for o in data["observations"]]

    results = pipeline.run_scenario(observations)
    assert len(results) == 6

    # Day 1: Healthy -> NO_ACTION, no milestone
    assert results[0].trigger_result.decision == TriggerDecision.NO_ACTION
    assert len(results[0].milestones_triggered) == 0

    # Day 2: First symptom appears -> CARE_ADVICE_REQUIRED, FIRST_SYMPTOM milestone
    assert results[1].trigger_result.decision == TriggerDecision.CARE_ADVICE_REQUIRED
    day2_milestone_types = [m.event_type.value for m in results[1].milestones_triggered]
    assert "first_symptom" in day2_milestone_types

    # Day 3: Unhealthy -> HEALTH_CRISIS milestone
    assert results[2].trigger_result.decision == TriggerDecision.CARE_ADVICE_REQUIRED
    day3_milestone_types = [m.event_type.value for m in results[2].milestones_triggered]
    assert "health_crisis" in day3_milestone_types

    # Day 4: Unhealthy day 2 (unchanged) -> NO_ACTION, no new milestone
    assert results[3].trigger_result.decision == TriggerDecision.NO_ACTION
    assert len(results[3].milestones_triggered) == 0

    # Day 5: Unhealthy day 3 (unchanged) -> NO_ACTION, but detects SEVERE_EPISODE milestone!
    assert results[4].trigger_result.decision == TriggerDecision.NO_ACTION
    day5_milestone_types = [m.event_type.value for m in results[4].milestones_triggered]
    assert "severe_episode" in day5_milestone_types

    # Day 6: Returns to healthy -> FULL_RECOVERY milestone & NO_ACTION
    assert results[5].trigger_result.decision == TriggerDecision.NO_ACTION
    day6_milestone_types = [m.event_type.value for m in results[5].milestones_triggered]
    assert "full_recovery" in day6_milestone_types

    # Verify all milestones stored in DB
    all_stored_milestones = pipeline.registry.get_milestones("plant-monstera-lifecycle")
    stored_types = [m.event_type.value for m in all_stored_milestones]
    assert "first_symptom" in stored_types
    assert "health_crisis" in stored_types
    assert "severe_episode" in stored_types
    assert "full_recovery" in stored_types

    # Verify frontend payload includes milestones_triggered
    payload_day5 = results[4].to_frontend_dict()
    assert len(payload_day5["milestones_triggered"]) > 0
    assert payload_day5["milestones_triggered"][0]["event_type"] == "severe_episode"

    # Verify companion_message was saved into observations table for each day
    recent_obs = pipeline.registry.get_recent_observations("plant-monstera-lifecycle", n=7)
    assert len(recent_obs) == 6
    for obs in recent_obs:
        assert obs.companion_message is not None
        assert len(obs.companion_message) > 0
