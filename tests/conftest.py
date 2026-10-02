"""Pytest configuration and shared mocks for LangChain migration."""

from __future__ import annotations

import json
from typing import Any, Optional

import pytest
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage
from langchain_core.outputs import ChatGeneration, ChatResult


from plant_poc.llm.mock import MockChatModel


@pytest.fixture
def mock_chat_model_factory():
    """Factory fixture returning a configured MockChatModel."""

    def _factory(responses: list[Any]) -> MockChatModel:
        return MockChatModel(responses=responses)

    return _factory
