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

    # Mock chat model returning CarePlan JSON directly (single-turn invoke via _SimpleAgentWrapper)
    mock_model = MockChatModel(
        responses=[
            """{
                "plant_id": "plant-monstera-1",
                "status_label": "Overwatering stress",
                "assessment": "The mild leaf yellowing strongly suggests early overwatering.",
                "confidence": 0.88,
                "actions": [
                    {"action": "Check soil moisture 2 inches down before watering.", "label": "Check soil", "type": "inspect", "priority": 1},
                    {"action": "Allow topsoil to dry out completely.", "label": "Pause water", "type": "water", "priority": 2}
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


def test_care_advisor_throws_error_when_llm_unavailable():
    from langchain_core.language_models import BaseChatModel
    from plant_poc.exceptions import LLMUnavailableError

    reg = PlantRegistry(init_db(":memory:"))
    k_store = KnowledgeStore()
    retriever = KnowledgeRetriever(k_store)

    class FailingChatModel(BaseChatModel):
        def _generate(self, *args, **kwargs):
            raise ConnectionError("Connection refused at http://localhost:11434")

        def bind_tools(self, tools, **kwargs):
            return self

        @property
        def _llm_type(self) -> str:
            return "failing_model"

    failing_model = FailingChatModel()

    advisor = CareAdvisorAgent(
        llm=failing_model,
        registry=reg,
        retriever=retriever,
    )

    obs = VLMObservation(
        plant_id="plant-monstera-1",
        timestamp=datetime.now(timezone.utc),
        health_status=HealthStatus.UNHEALTHY,
        confidence=0.90,
        observations=[
            Observation(type="leaf_yellowing", severity="severe", confidence=0.95)
        ],
    )
    trigger_res = TriggerResult(
        decision=TriggerDecision.CARE_ADVICE_REQUIRED,
        reason="Severe symptoms detected.",
    )

    with pytest.raises(LLMUnavailableError) as exc_info:
        advisor.advise(obs, trigger_res)

    err = exc_info.value
    assert "LLM reasoning service is unavailable" in str(err)

    # Check to_error_dict envelope format (expose_details=True for test assertions)
    error_dict = err.to_error_dict(expose_details=True)
    assert error_dict["success"] is False
    assert error_dict["data"] is None
    assert error_dict["error"]["code"] == "LLM_UNAVAILABLE"
    assert "Connection refused" in error_dict["error"]["details"]["reason"]

    # Verify production mode (default) does NOT leak raw exception reason
    safe_dict = err.to_error_dict()
    safe_details = safe_dict["error"]["details"]
    assert safe_details is None or "reason" not in safe_details


def test_internal_server_error_and_make_error_response():
    from plant_poc.exceptions import InternalServerError, make_error_response

    ise = InternalServerError(
        message="An unexpected internal server error occurred while processing the plant companion state.",
        request_id="req_8f1b2c3d4e5f",
        original_error=RuntimeError("Database connection timeout"),
    )
    d = ise.to_error_dict(expose_details=True)
    assert d["success"] is False
    assert d["data"] is None
    assert d["error"]["code"] == "INTERNAL_SERVER_ERROR"
    assert d["error"]["details"]["request_id"] == "req_8f1b2c3d4e5f"
    assert "Database connection timeout" in d["error"]["details"]["reason"]

    # Verify production mode (default) does NOT leak raw exception reason
    safe_d = ise.to_error_dict()
    assert safe_d["error"]["details"]["request_id"] == "req_8f1b2c3d4e5f"
    assert "reason" not in safe_d["error"]["details"]

    custom = make_error_response(
        code="INTERNAL_SERVER_ERROR",
        message="Generic failure",
        details={"hint": "check logs"},
    )
    assert custom["success"] is False
    assert custom["error"]["code"] == "INTERNAL_SERVER_ERROR"


