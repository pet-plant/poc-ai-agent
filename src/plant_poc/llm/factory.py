"""LLM factory for multi-provider support via LangChain."""

from __future__ import annotations

from typing import Optional
from langchain_core.language_models import BaseChatModel

from plant_poc.config import LLM_MODEL, LLM_PROVIDER, OLLAMA_HOST, OLLAMA_MODEL


def get_llm(
    provider: Optional[str] = None,
    model: Optional[str] = None,
    temperature: float = 0.2,
) -> BaseChatModel:
    """Return a configured BaseChatModel instance based on provider and model.

    Supported providers: 'ollama', 'openai', 'anthropic', 'gemini'
    """
    resolved_provider = (provider or LLM_PROVIDER or "ollama").lower()
    resolved_model = model or LLM_MODEL or None

    if resolved_provider == "ollama":
        from langchain_ollama import ChatOllama

        return ChatOllama(
            base_url=OLLAMA_HOST,
            model=resolved_model or OLLAMA_MODEL,
            temperature=temperature,
        )
    elif resolved_provider == "openai":
        from langchain_openai import ChatOpenAI

        return ChatOpenAI(
            model=resolved_model or "gpt-4o-mini",
            temperature=temperature,
        )
    elif resolved_provider == "anthropic":
        try:
            from langchain_anthropic import ChatAnthropic
        except ImportError:
            raise ImportError(
                "langchain-anthropic is required for Anthropic provider. Install with `uv add langchain-anthropic`"
            )
        return ChatAnthropic(
            model=resolved_model or "claude-3-5-sonnet-20241022",
            temperature=temperature,
        )
    elif resolved_provider in ("gemini", "google"):
        try:
            from langchain_google_genai import ChatGoogleGenerativeAI
        except ImportError:
            raise ImportError(
                "langchain-google-genai is required for Gemini provider. Install with `uv add langchain-google-genai`"
            )
        return ChatGoogleGenerativeAI(
            model=resolved_model or "gemini-2.0-flash",
            temperature=temperature,
        )
    elif resolved_provider == "mock":
        from plant_poc.llm.mock import MockChatModel

        return MockChatModel()
    else:
        raise ValueError(f"Unknown LLM provider: {resolved_provider}")
