"""Tests for LangChain @tool decorator, tool calling loop, and Pydantic output parsing."""

import json
import pytest
from plant_poc.agents.care_advisor.agent import _build_agent
from langchain_core.output_parsers import PydanticOutputParser
from langchain_core.tools import tool

from plant_poc.schemas import CareAction, CarePlan
from tests.conftest import MockChatModel


def test_agent_tool_loop_with_tool_call():
    """Test that _build_agent produces an agent wrapper that can invoke the LLM and return parseable output."""

    @tool
    def get_plant_profile(plant_id: str) -> dict:
        """Fetch profile for a plant."""
        return {"plant_id": plant_id, "species": "Monstera deliciosa"}

    final_output = json.dumps({
        "plant_id": "plant-monstera-1",
        "assessment": "Overwatering detected.",
        "confidence": 0.95,
        "actions": [
            {"action": "Check soil moisture.", "priority": 1}
        ],
    })

    mock_model = MockChatModel(responses=[final_output])

    agent = _build_agent(
        llm=mock_model,
        tools=[get_plant_profile],
        system_prompt="You are a plant care advisor.",
    )

    result = agent.invoke({"messages": [{"role": "user", "content": "Assess plant-monstera-1"}]})
    final_text = result["messages"][-1].content

    parser = PydanticOutputParser(pydantic_object=CarePlan)
    plan = parser.parse(final_text)

    assert plan.plant_id == "plant-monstera-1"
    assert plan.assessment == "Overwatering detected."
    assert len(plan.actions) == 1
    assert plan.actions[0].action == "Check soil moisture."


def test_pydantic_output_parser_validation():
    parser = PydanticOutputParser(pydantic_object=CarePlan)

    valid_json = """{
        "plant_id": "p1",
        "assessment": "Healthy plant.",
        "confidence": 0.9,
        "actions": []
    }"""
    plan = parser.parse(valid_json)
    assert plan.plant_id == "p1"
    assert plan.assessment == "Healthy plant."
