import pytest
from plant_poc.llm import LLMClient, MockLLMClient, LLMResponse, ToolCall


def test_mock_llm_client_protocol():
    mock = MockLLMClient(
        canned_responses=[
            LLMResponse(
                content="",
                tool_calls=[
                    ToolCall(name="search_plant_knowledge", arguments={"species": "Monstera deliciosa"})
                ],
            ),
            LLMResponse(
                content='{"plant_id": "p1", "assessment": "healthy", "confidence": 0.9, "actions": []}',
                tool_calls=[],
            ),
        ]
    )

    # Verify protocol compliance
    assert isinstance(mock, LLMClient)

    # First call: tool call
    res1 = mock.chat([{"role": "user", "content": "hello"}])
    assert len(res1.tool_calls) == 1
    assert res1.tool_calls[0].name == "search_plant_knowledge"

    # Second call: final answer
    res2 = mock.chat([{"role": "tool", "content": "found 1 doc"}])
    assert "assessment" in res2.content
    assert len(res2.tool_calls) == 0
