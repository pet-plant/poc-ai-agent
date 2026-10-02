"""Mock Chat Model for offline testing and CLI mock runs."""

from __future__ import annotations

import json
from typing import Any, Optional

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage
from langchain_core.outputs import ChatGeneration, ChatResult

DEFAULT_MOCK_CARE_PLAN = json.dumps(
    {
        "plant_id": "plant-mock",
        "assessment": "Offline mock assessment: Observations noted and care schedule adjusted.",
        "confidence": 0.9,
        "actions": [
            {"priority": 1, "action": "Check soil moisture 2 inches down."},
            {"priority": 2, "action": "Adjust watering schedule based on moisture level."},
        ],
    }
)


class MockChatModel(BaseChatModel):
    """LangChain mock chat model supporting canned string responses, tool calls, and invocation history."""

    responses: list[Any] = []
    call_history: list[Any] = []

    class Config:
        underscore_attrs_are_private = True

    def __init__(self, responses: Optional[list[Any]] = None, **kwargs: Any):
        super().__init__(**kwargs)
        object.__setattr__(self, "responses", list(responses or [DEFAULT_MOCK_CARE_PLAN]))
        object.__setattr__(self, "call_history", [])
        object.__setattr__(self, "_idx", 0)

    def _generate(
        self,
        messages: list[BaseMessage],
        stop: Optional[list[str]] = None,
        run_manager: Any = None,
        **kwargs: Any,
    ) -> ChatResult:
        self.call_history.append(messages)

        if not self.responses:
            return ChatResult(generations=[ChatGeneration(message=AIMessage(content=""))])

        if self._idx < len(self.responses):
            resp = self.responses[self._idx]
            object.__setattr__(self, "_idx", self._idx + 1)
        else:
            resp = self.responses[-1]

        if isinstance(resp, AIMessage):
            ai_msg = resp
        elif isinstance(resp, dict):
            ai_msg = AIMessage(
                content=resp.get("content", ""),
                tool_calls=resp.get("tool_calls", []),
            )
        else:
            ai_msg = AIMessage(content=str(resp))

        return ChatResult(generations=[ChatGeneration(message=ai_msg)])

    def bind_tools(self, tools: Any, **kwargs: Any) -> Any:
        return self

    @property
    def _llm_type(self) -> str:
        return "mock_chat_model"
