import pytest
from plant_poc.agents.base import AgentTool, run_tool_agent
from plant_poc.llm.base import MockLLMClient, LLMResponse, ToolCall
from plant_poc.schemas import CarePlan, CareAction


def test_agent_tool_loop_with_tool_call():
    # 1. First turn: Model requests tool call
    # 2. Second turn: Model returns structured CarePlan
    mock_client = MockLLMClient(
        canned_responses=[
            LLMResponse(
                content="",
                tool_calls=[
                    ToolCall(
                        name="get_plant_profile",
                        arguments={"plant_id": "plant-monstera-1"},
                    )
                ],
            ),
            LLMResponse(
                content="""```json
                {
                    "plant_id": "plant-monstera-1",
                    "assessment": "Overwatering detected.",
                    "confidence": 0.95,
                    "actions": [
                        {"action": "Check soil moisture.", "priority": 1}
                    ]
                }
                ```""",
                tool_calls=[],
            ),
        ]
    )

    tool_called = []

    def mock_get_profile(plant_id: str):
        tool_called.append(plant_id)
        return {"plant_id": plant_id, "species": "Monstera deliciosa"}

    tool = AgentTool(
        name="get_plant_profile",
        description="Fetch profile",
        parameters={
            "type": "object",
            "properties": {"plant_id": {"type": "string"}},
            "required": ["plant_id"],
        },
        func=mock_get_profile,
    )

    plan = run_tool_agent(
        client=mock_client,
        system_prompt="You are a plant care advisor.",
        user_prompt="Assess plant-monstera-1",
        tools=[tool],
        response_model=CarePlan,
    )

    assert tool_called == ["plant-monstera-1"]
    assert plan.plant_id == "plant-monstera-1"
    assert plan.assessment == "Overwatering detected."
    assert len(plan.actions) == 1
    assert plan.actions[0].action == "Check soil moisture."


def test_agent_retry_on_invalid_schema():
    # 1. First turn: Model returns invalid JSON/schema (missing required plant_id)
    # 2. Second turn: Model corrects and returns valid CarePlan
    mock_client = MockLLMClient(
        canned_responses=[
            LLMResponse(
                content='{"assessment": "Missing plant_id and confidence"}',
                tool_calls=[],
            ),
            LLMResponse(
                content='{"plant_id": "p1", "assessment": "Corrected plan", "confidence": 0.9, "actions": []}',
                tool_calls=[],
            ),
        ]
    )

    plan = run_tool_agent(
        client=mock_client,
        system_prompt="System",
        user_prompt="User",
        tools=[],
        response_model=CarePlan,
        max_retries=1,
    )

    assert plan.plant_id == "p1"
    assert plan.assessment == "Corrected plan"
    assert len(mock_client.call_history) == 2
