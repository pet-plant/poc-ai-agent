"""Tests for LLM factory and LangChain chat model integration."""

import pytest
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage

try:
    from langchain_ollama import ChatOllama
except ImportError:
    ChatOllama = None

try:
    from langchain_openai import ChatOpenAI
except ImportError:
    ChatOpenAI = None

from plant_poc.llm import get_llm
from tests.conftest import MockChatModel


@pytest.mark.skipif(ChatOllama is None or ChatOpenAI is None, reason="langchain_ollama/langchain_openai not installed")
def test_get_llm_factory_providers(monkeypatch):
    ollama_model = get_llm(provider="ollama")
    assert isinstance(ollama_model, BaseChatModel)
    assert isinstance(ollama_model, ChatOllama)

    monkeypatch.setenv("OPENAI_API_KEY", "sk-fake-test-key-for-factory-test")
    openai_model = get_llm(provider="openai")
    assert isinstance(openai_model, BaseChatModel)
    assert isinstance(openai_model, ChatOpenAI)

    with pytest.raises(ValueError, match="Unknown LLM provider"):
        get_llm(provider="unsupported_provider_xyz")


def test_mock_chat_model_tool_calling():
    tool_call = {
        "name": "search_plant_knowledge",
        "args": {"species": "Monstera deliciosa"},
        "id": "call_1",
    }
    model = MockChatModel(
        responses=[
            {"content": "", "tool_calls": [tool_call]},
            '{"plant_id": "p1", "assessment": "healthy", "confidence": 0.9, "actions": []}',
        ]
    )

    # First turn: tool call
    res1 = model.invoke("hello")
    assert len(res1.tool_calls) == 1
    assert res1.tool_calls[0]["name"] == "search_plant_knowledge"

    # Second turn: final answer
    res2 = model.invoke("search results returned")
    assert "assessment" in res2.content
    assert len(res2.tool_calls) == 0
