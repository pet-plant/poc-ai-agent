"""Native Ollama adapter client implementing the LLMClient protocol."""

import json
from typing import Optional, Any
import httpx
from plant_poc.config import OLLAMA_HOST, OLLAMA_MODEL
from plant_poc.llm.base import LLMClient, LLMResponse, ToolCall


class OllamaClient:
    """Client for Ollama's native chat and tool-calling API."""

    def __init__(
        self,
        host: str = OLLAMA_HOST,
        model: str = OLLAMA_MODEL,
        timeout: float = 60.0,
    ):
        self.host = host.rstrip("/")
        self.model = model
        self.timeout = timeout

    def chat(
        self,
        messages: list[dict[str, Any]],
        tools: Optional[list[dict[str, Any]]] = None,
        temperature: float = 0.2,
    ) -> LLMResponse:
        """Call Ollama /api/chat with messages and optional tool definitions."""
        payload: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "stream": False,
            "options": {
                "temperature": temperature,
            },
        }
        if tools:
            payload["tools"] = tools

        url = f"{self.host}/api/chat"
        with httpx.Client(timeout=self.timeout) as client:
            res = client.post(url, json=payload)
            res.raise_for_status()
            data = res.json()

        message = data.get("message", {})
        content = message.get("content") or ""

        tool_calls: list[ToolCall] = []
        raw_tool_calls = message.get("tool_calls", [])
        for i, tc in enumerate(raw_tool_calls):
            func = tc.get("function", {})
            name = func.get("name", "")
            raw_args = func.get("arguments", {})
            if isinstance(raw_args, str):
                try:
                    args = json.loads(raw_args)
                except Exception:
                    args = {}
            elif isinstance(raw_args, dict):
                args = raw_args
            else:
                args = {}

            tool_calls.append(
                ToolCall(
                    id=tc.get("id", f"call_{i}"),
                    name=name,
                    arguments=args,
                )
            )

        return LLMResponse(content=content, tool_calls=tool_calls)
