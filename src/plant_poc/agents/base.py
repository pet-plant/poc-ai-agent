"""Shared tool-calling agent loop with Pydantic schema validation and retry."""

import json
import re
from typing import Callable, Any, TypeVar, Type, Optional
from pydantic import BaseModel, ValidationError
from plant_poc.llm import LLMClient, LLMResponse, ToolCall

T = TypeVar("T", bound=BaseModel)


class AgentTool:
    """Encapsulates a callable tool with JSON schema metadata for Ollama/OpenAI."""

    def __init__(
        self,
        name: str,
        description: str,
        parameters: dict[str, Any],
        func: Callable[..., Any],
    ):
        self.name = name
        self.description = description
        self.parameters = parameters
        self.func = func

    def to_ollama_tool(self) -> dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters,
            },
        }

    def execute(self, **kwargs) -> Any:
        return self.func(**kwargs)


def extract_json_from_text(text: str) -> Optional[dict[str, Any]]:
    """Extract JSON object from markdown code block or raw text."""
    # Check for markdown code fence
    fence_match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    if fence_match:
        try:
            return json.loads(fence_match.group(1))
        except Exception:
            pass

    # Check for first { to last }
    brace_match = re.search(r"(\{.*\})", text, re.DOTALL)
    if brace_match:
        try:
            return json.loads(brace_match.group(1))
        except Exception:
            pass

    try:
        return json.loads(text.strip())
    except Exception:
        return None


def run_tool_agent(
    client: LLMClient,
    system_prompt: str,
    user_prompt: str,
    tools: list[AgentTool],
    response_model: Type[T],
    max_turns: int = 5,
    max_retries: int = 1,
) -> T:
    """Execute autonomous tool-calling loop and validate output against response_model.

    Handles tool calls up to max_turns, then validates output JSON against response_model.
    On validation failure, sends validation errors back to the model for up to max_retries.
    """
    tool_map = {t.name: t for t in tools}
    tool_defs = [t.to_ollama_tool() for t in tools] if tools else None

    messages: list[dict[str, Any]] = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]

    retries_left = max_retries
    for turn in range(max_turns):
        res: LLMResponse = client.chat(messages, tools=tool_defs)

        # If model requested tool calls
        if res.tool_calls:
            # Append assistant message with tool calls
            assistant_msg: dict[str, Any] = {
                "role": "assistant",
                "content": res.content or "",
                "tool_calls": [
                    {
                        "id": tc.id,
                        "type": "function",
                        "function": {"name": tc.name, "arguments": tc.arguments},
                    }
                    for tc in res.tool_calls
                ],
            }
            messages.append(assistant_msg)

            # Execute tools and append results
            for tc in res.tool_calls:
                tool = tool_map.get(tc.name)
                if tool:
                    try:
                        tool_result = tool.execute(**tc.arguments)
                    except Exception as e:
                        tool_result = {"error": f"Tool execution failed: {str(e)}"}
                else:
                    tool_result = {"error": f"Unknown tool '{tc.name}'"}

                messages.append(
                    {
                        "role": "tool",
                        "name": tc.name,
                        "content": json.dumps(tool_result, default=str),
                    }
                )
            continue

        # If model returned final content
        content = res.content or ""
        parsed_dict = extract_json_from_text(content)

        if parsed_dict is not None:
            try:
                validated_obj = response_model.model_validate(parsed_dict)
                return validated_obj
            except ValidationError as e:
                if retries_left > 0:
                    retries_left -= 1
                    messages.append({"role": "assistant", "content": content})
                    messages.append(
                        {
                            "role": "user",
                            "content": (
                                f"Your response failed schema validation:\n{str(e)}\n"
                                f"Please correct the JSON output and respond with valid JSON matching the schema."
                            ),
                        }
                    )
                    continue
                raise ValueError(f"Failed schema validation after retry: {e}")
        else:
            if retries_left > 0:
                retries_left -= 1
                messages.append({"role": "assistant", "content": content})
                messages.append(
                    {
                        "role": "user",
                        "content": "Your response was not valid JSON. Please return ONLY a valid JSON object matching the requested schema.",
                    }
                )
                continue
            raise ValueError(f"Model response could not be parsed as JSON: {content}")

    raise RuntimeError(f"Agent exceeded maximum turns ({max_turns}) without producing a valid response.")
