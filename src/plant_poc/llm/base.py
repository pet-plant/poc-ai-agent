"""LLM client interface protocol, response models, and mock implementation."""

from typing import Protocol, Optional, Any, Callable, runtime_checkable
from pydantic import BaseModel, Field


class ToolCall(BaseModel):
    id: str = ""
    name: str
    arguments: dict[str, Any] = Field(default_factory=dict)


class LLMResponse(BaseModel):
    content: Optional[str] = None
    tool_calls: list[ToolCall] = Field(default_factory=list)


@runtime_checkable
class LLMClient(Protocol):
    """Protocol for LLM communication (Ollama, Mock, etc.)."""

    def chat(
        self,
        messages: list[dict[str, Any]],
        tools: Optional[list[dict[str, Any]]] = None,
        temperature: float = 0.2,
    ) -> LLMResponse:
        """Send chat messages and optional tool definitions to the model."""
        ...


class MockLLMClient:
    """Mock LLM client returning scripted or computed responses for offline testing."""

    def __init__(
        self,
        canned_responses: Optional[list[LLMResponse]] = None,
        handler: Optional[Callable[[list[dict[str, Any]], Optional[list[dict[str, Any]]]], LLMResponse]] = None,
    ):
        self.canned_responses = list(canned_responses or [])
        self.handler = handler
        self.call_history: list[dict[str, Any]] = []

    def chat(
        self,
        messages: list[dict[str, Any]],
        tools: Optional[list[dict[str, Any]]] = None,
        temperature: float = 0.2,
    ) -> LLMResponse:
        self.call_history.append({"messages": messages, "tools": tools})

        if self.handler:
            return self.handler(messages, tools)

        if self.canned_responses:
            return self.canned_responses.pop(0)

        # Default fallback: return a default valid JSON care plan
        return LLMResponse(
            content='{"plant_id": "mock-plant", "assessment": "Symptoms indicate moisture imbalance.", "confidence": 0.85, "actions": [{"action": "Check soil moisture.", "priority": 1}]}',
            tool_calls=[],
        )
