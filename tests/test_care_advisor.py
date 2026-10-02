from datetime import datetime, timezone
import pytest
from plant_poc.agents.care_advisor import CareAdvisorAgent
from plant_poc.knowledge import (
    KnowledgeStore,
    ingest_knowledge_directory,
    KnowledgeRetriever,
)
from plant_poc.registry import init_db, PlantRegistry
from plant_poc.schemas import (
    VLMObservation,
    Observation,
    HealthStatus,
    TriggerResult,
    TriggerDecision,
)
from plant_poc.config import KNOWLEDGE_DIR
from tests.conftest import MockChatModel


def test_care_advisor_generates_watering_action():
    # Setup test registry and seeded knowledge RAG
    reg = PlantRegistry(init_db(":memory:"))
    k_store = KnowledgeStore()
    ingest_knowledge_directory(k_store, KNOWLEDGE_DIR)
    retriever = KnowledgeRetriever(k_store)

    # Mock chat model simulating tool call to search knowledge, then returning CarePlan with watering action
    mock_model = MockChatModel(
        responses=[
            {
                "content": "",
                "tool_calls": [
                    {
                        "name": "search_plant_knowledge",
                        "args": {
                            "species": "Monstera deliciosa",
                            "symptoms": ["leaf_yellowing"],
                        },
                        "id": "call_search_1",
                    }
                ],
            },
            """{
                "plant_id": "plant-monstera-1",
                "assessment": "The mild leaf yellowing strongly suggests early overwatering.",
                "confidence": 0.88,
                "actions": [
                    {"action": "Check soil moisture 2 inches down before watering.", "priority": 1},
                    {"action": "Allow topsoil to dry out completely.", "priority": 2}
                ]
            }""",
        ]
    )

    advisor = CareAdvisorAgent(
        llm=mock_model,
        registry=reg,
        retriever=retriever,
    )

    obs = VLMObservation(
        plant_id="plant-monstera-1",
        timestamp=datetime.now(timezone.utc),
        health_status=HealthStatus.POSSIBLY_UNHEALTHY,
        confidence=0.90,
        observations=[
            Observation(type="leaf_yellowing", severity="mild", confidence=0.88)
        ],
    )

    trigger_res = TriggerResult(
        decision=TriggerDecision.CARE_ADVICE_REQUIRED,
        reason="New symptom 'leaf_yellowing' appeared.",
    )

    plan = advisor.advise(obs, trigger_res)

    assert plan.plant_id == "plant-monstera-1"
    assert "overwatering" in plan.assessment.lower()
    assert len(plan.actions) >= 1

    watering_actions = [
        a for a in plan.actions
        if any(term in a.action.lower() for term in ["water", "soil", "moisture", "dry"])
    ]
    assert len(watering_actions) > 0, "Expected at least one watering/soil-related action"

    saved_plans = reg.get_recent_care_plans("plant-monstera-1")
    assert len(saved_plans) == 1
    assert saved_plans[0].assessment == plan.assessment
