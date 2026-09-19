import pytest
from plant_poc.agents.companion import CompanionAgent, validate_fact_preservation
from plant_poc.llm import MockLLMClient, LLMResponse
from plant_poc.schemas import CarePlan, CareAction, PlantProfile


def test_companion_template_preserves_all_actions():
    plan = CarePlan(
        plant_id="plant-1",
        assessment="Yellowing leaves suggest soil is staying wet too long.",
        confidence=0.9,
        actions=[
            CareAction(action="Check soil moisture 2 inches down.", priority=1),
            CareAction(action="Ensure pot drainage holes are clear.", priority=2),
        ],
    )
    profile = PlantProfile(
        plant_id="plant-1",
        species="Monstera deliciosa",
        nickname="Monty",
        location="Living Room",
    )

    companion = CompanionAgent(use_llm=False)
    text = companion.generate_message(plan, profile)

    # Acceptance test per PRD §4.5: produces text that mentions every action.action
    for item in plan.actions:
        assert item.action in text

    is_valid, missing = validate_fact_preservation(plan, text)
    assert is_valid
    assert len(missing) == 0


def test_validator_detects_dropped_action():
    plan = CarePlan(
        plant_id="plant-1",
        assessment="Overwatered.",
        confidence=0.9,
        actions=[
            CareAction(action="Stop watering for seven days.", priority=1),
            CareAction(action="Repot into chunky aerated bark mix.", priority=2),
        ],
    )

    # Text that dropped the repotting action
    bad_text = "Hey! Monty is overwatered. Please stop watering for seven days."
    is_valid, missing = validate_fact_preservation(plan, bad_text)

    assert not is_valid
    assert len(missing) == 1
    assert "Repot" in missing[0]


def test_companion_llm_mode_with_validation_fallback():
    plan = CarePlan(
        plant_id="plant-1",
        assessment="Mild yellowing.",
        confidence=0.85,
        actions=[
            CareAction(action="Check moisture 2 inches down.", priority=1),
        ],
    )

    # Mock client returns text that omits the action -> should fall back to template
    mock_client = MockLLMClient(
        canned_responses=[
            LLMResponse(content="Hello! Your plant looks okay, don't worry about anything!"),
        ]
    )

    companion = CompanionAgent(llm_client=mock_client, use_llm=True)
    text = companion.generate_message(plan)

    # Fallback template must contain the action
    assert "Check moisture 2 inches down." in text
