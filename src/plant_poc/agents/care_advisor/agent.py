"""Care Advisor Agent implementation using LangChain."""

from __future__ import annotations

import asyncio
import json
import re
from typing import Any, Optional, Union

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage
from langchain_core.output_parsers import PydanticOutputParser
from langchain_core.outputs import ChatGeneration, ChatResult

try:
    from langchain.agents import AgentExecutor, create_tool_calling_agent
    from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
    _HAS_AGENT_EXECUTOR = True
except ImportError:
    _HAS_AGENT_EXECUTOR = False

from plant_poc.exceptions import LLMUnavailableError
from plant_poc.agents.care_advisor.prompts import (
    CARE_ADVISOR_SYSTEM_PROMPT,
    format_advisor_user_prompt,
)
from plant_poc.agents.care_advisor.tools import build_care_advisor_tools
from plant_poc.knowledge import KnowledgeRetriever
from plant_poc.registry import PlantRegistry
from plant_poc.schemas import CarePlan, TriggerResult, VLMObservation


class _SimpleAgentWrapper:
    """Minimal agent wrapper for when AgentExecutor is unavailable or no tools are needed."""

    def __init__(self, llm: BaseChatModel, system_prompt: str):
        self.llm = llm
        self.system_prompt = system_prompt

    def invoke(self, input_dict: dict) -> dict:
        messages_raw = input_dict.get("messages", [])
        messages: list[BaseMessage] = [SystemMessage(content=self.system_prompt)]
        for m in messages_raw:
            if isinstance(m, BaseMessage):
                messages.append(m)
            elif isinstance(m, dict):
                messages.append(HumanMessage(content=m.get("content", "")))
        result = self.llm.invoke(messages)
        return {"messages": messages + [result]}


def _build_agent(llm: BaseChatModel, tools: list, system_prompt: str) -> Any:
    """Build an agent wrapper that passes the system prompt and user messages to the LLM.

    Uses _SimpleAgentWrapper for all cases because the system prompt contains
    raw JSON examples with braces that break ChatPromptTemplate variable parsing.
    The LLM is expected to have tools bound via bind_tools if needed.
    """
    if tools and hasattr(llm, "bind_tools"):
        try:
            llm = llm.bind_tools(tools)
        except (NotImplementedError, AttributeError):
            pass
    return _SimpleAgentWrapper(llm=llm, system_prompt=system_prompt)


class _LegacyLLMAdapter(BaseChatModel):
    """Adapter allowing legacy LLMClient implementations to be used as BaseChatModel."""

    client: Any

    def _generate(
        self,
        messages: list[BaseMessage],
        stop: Optional[list[str]] = None,
        run_manager: Any = None,
        **kwargs: Any,
    ) -> ChatResult:
        msg_dicts = []
        for m in messages:
            role = "user" if m.type == "human" else ("assistant" if m.type == "ai" else m.type)
            msg_dicts.append({"role": role, "content": m.content})

        resp = self.client.chat(msg_dicts)
        tool_calls = []
        if getattr(resp, "tool_calls", None):
            for tc in resp.tool_calls:
                tool_calls.append(
                    {
                        "name": tc.name,
                        "args": tc.arguments,
                        "id": getattr(tc, "id", f"call_{tc.name}"),
                    }
                )
        ai_msg = AIMessage(content=resp.content or "", tool_calls=tool_calls)
        return ChatResult(generations=[ChatGeneration(message=ai_msg)])

    def bind_tools(self, tools: Any, **kwargs: Any) -> Any:
        return self

    @property
    def _llm_type(self) -> str:
        return "legacy_client_adapter"


class CareAdvisorAgent:
    """Agent that reasons over plant history & knowledge to output a structured CarePlan."""

    def __init__(
        self,
        llm: Union[BaseChatModel, Any] = None,
        registry: Optional[PlantRegistry] = None,
        retriever: Optional[KnowledgeRetriever] = None,
        llm_client: Optional[Any] = None,  # Backward compatibility
    ):
        model = llm if llm is not None else llm_client
        if model is None:
            from plant_poc.llm import get_llm
            try:
                model = get_llm()
            except Exception as exc:
                raise LLMUnavailableError(
                    message="Failed to initialize default LLM provider.",
                    original_error=exc,
                ) from exc

        if model is None:
            raise LLMUnavailableError("No LLM client or model provided to CareAdvisorAgent.")

        if not isinstance(model, BaseChatModel):
            self.llm = _LegacyLLMAdapter(client=model)
        else:
            self.llm = model

        self.registry = registry
        self.retriever = retriever
        self.tools = (
            build_care_advisor_tools(registry, retriever)
            if (registry and retriever)
            else []
        )
        self.parser = PydanticOutputParser(pydantic_object=CarePlan)

        self.agent = _build_agent(
            llm=self.llm,
            tools=self.tools,
            system_prompt=CARE_ADVISOR_SYSTEM_PROMPT,
        )

    def advise(
        self,
        observation: VLMObservation,
        trigger_result: TriggerResult,
    ) -> CarePlan:
        """Run the Care Advisor reasoning loop to produce a CarePlan."""
        symptoms_str = (
            ", ".join(
                f"{obs.type} ({obs.severity}, conf={obs.confidence:.2f})"
                for obs in observation.observations
            )
            if observation.observations
            else "No specific symptoms reported."
        )

        user_prompt = format_advisor_user_prompt(
            plant_id=observation.plant_id,
            health_status=observation.health_status.value,
            confidence=observation.confidence,
            observations_summary=symptoms_str,
            trigger_reason=trigger_result.reason,
            leaf_posture=observation.leaf_posture,
            leaf_color_detail=observation.leaf_color_detail,
            consensus_agreement=observation.consensus.agreement
            if observation.consensus
            else None,
        )

        try:
            result = self.agent.invoke(
                {"messages": [{"role": "user", "content": user_prompt}]}
            )
        except Exception as exc:
            if isinstance(exc, LLMUnavailableError):
                raise
            raise LLMUnavailableError(
                message=f"Failed to generate care plan: LLM reasoning service is unavailable ({exc})",
                original_error=exc,
            ) from exc

        final_message = result["messages"][-1]
        raw_output = (
            final_message.content
            if hasattr(final_message, "content")
            else str(final_message)
        )

        plan = self._parse_care_plan(raw_output, observation.plant_id)

        if self.registry:
            self.registry.save_care_plan(observation.plant_id, plan)

        return plan

    async def advise_async(
        self,
        observation: VLMObservation,
        trigger_result: TriggerResult,
    ) -> CarePlan:
        """Async wrapper around :meth:`advise` that offloads the blocking LLM
        call to a thread so it does not stall an async event loop (e.g.
        FastAPI, Starlette).
        """
        return await asyncio.to_thread(self.advise, observation, trigger_result)

    def _parse_care_plan(self, text: str, plant_id: str) -> CarePlan:
        try:
            return self.parser.parse(text)
        except Exception:
            match = re.search(r"(\{.*\})", text, re.DOTALL)
            if match:
                try:
                    data = json.loads(match.group(1))
                    if "plant_id" not in data:
                        data["plant_id"] = plant_id
                    return CarePlan.model_validate(data)
                except Exception:
                    pass
            return CarePlan(
                plant_id=plant_id,
                status_label="Care advice required",
                assessment="Automated assessment: observation recorded.",
                confidence=0.5,
                actions=[],
            )
