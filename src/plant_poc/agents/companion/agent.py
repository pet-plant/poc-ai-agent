"""Companion Layer — plant personality projector using LangChain LCEL chain."""

from __future__ import annotations

from typing import Any, Optional, Union

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage
from langchain_core.output_parsers import StrOutputParser
from langchain_core.outputs import ChatGeneration, ChatResult
from langchain_core.prompts import ChatPromptTemplate

from plant_poc.agents.companion.prompts import (
    format_companion_user_prompt,
    get_companion_system_prompt,
)
from plant_poc.agents.companion.validator import validate_fact_preservation
from plant_poc.schemas import (
    CarePlan,
    HealthStatus,
    PlantMilestone,
    PlantProfile,
    VLMObservation,
)


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

        resp = self.client.chat(msg_dicts, temperature=kwargs.get("temperature", 0.7))
        ai_msg = AIMessage(content=getattr(resp, "content", "") or "")
        return ChatResult(generations=[ChatGeneration(message=ai_msg)])

    def bind_tools(self, tools: Any, **kwargs: Any) -> Any:
        return self

    @property
    def _llm_type(self) -> str:
        return "legacy_client_adapter"


class CompanionAgent:
    """Generates plant-voice messages from structured CarePlans — the plant speaks as itself."""

    def __init__(
        self,
        llm: Optional[Union[BaseChatModel, Any]] = None,
        use_llm: bool = True,
        llm_client: Optional[Any] = None,  # Backward compatibility
    ):
        model = llm if llm is not None else llm_client
        if model is not None and not isinstance(model, BaseChatModel):
            self.llm: Optional[BaseChatModel] = _LegacyLLMAdapter(client=model)
        else:
            self.llm = model

        self.use_llm = use_llm

        if self.llm:
            prompt = ChatPromptTemplate.from_messages(
                [
                    ("system", "{system_prompt}"),
                    ("human", "{user_prompt}"),
                ]
            )
            self.chain = prompt | self.llm | StrOutputParser()
        else:
            self.chain = None

    def generate_message(
        self,
        care_plan: CarePlan,
        plant_profile: Optional[PlantProfile] = None,
        health_status: Optional[HealthStatus] = None,
        recent_observations: Optional[list[VLMObservation]] = None,
        milestones: Optional[list[PlantMilestone]] = None,
    ) -> str:
        """Generate a first-person plant-voice message with two-tier memory context."""
        nickname = plant_profile.nickname if plant_profile else "your plant"
        status_str = health_status.value if health_status else "healthy"

        # Primary: LCEL chain speaks AS the plant in first-person
        if self.use_llm and self.chain:
            action_texts = [a.action for a in care_plan.actions]
            system_prompt = get_companion_system_prompt(status_str)
            user_prompt = format_companion_user_prompt(
                plant_nickname=nickname,
                assessment=care_plan.assessment,
                actions=action_texts,
                health_status=status_str,
                recent_observations=recent_observations,
                milestones=milestones,
            )
            try:
                llm_text = self.chain.invoke(
                    {"system_prompt": system_prompt, "user_prompt": user_prompt}
                ).strip()

                is_valid, _ = validate_fact_preservation(care_plan, llm_text)
                if is_valid:
                    return llm_text
                # Fallback if LLM output dropped required care actions
                return self._format_template(
                    care_plan,
                    nickname,
                    notice="[Companion: Output dropped actions — showing structured summary]\n",
                )
            except Exception:
                return self._format_template(
                    care_plan,
                    nickname,
                    notice="[LLM unavailable — showing care summary]\n",
                )

        # Fallback: deterministic template when LLM mode is disabled
        return self._format_template(
            care_plan,
            nickname,
            notice="[Template mode — showing care summary]\n",
        )

    def _format_template(
        self,
        care_plan: CarePlan,
        nickname: str,
        notice: str = "[Template mode — showing care summary]\n",
    ) -> str:
        """3rd-person fallback template used when LLM is unavailable or disabled."""
        if not care_plan.actions:
            return f"{notice}{nickname} is doing well. {care_plan.assessment}"

        action_lines = "\n".join(
            f"  • {item.action}"
            for item in sorted(care_plan.actions, key=lambda x: x.priority)
        )
        return (
            f"{notice}Update on {nickname}:\n"
            f"{care_plan.assessment}\n\n"
            f"Recommended actions:\n"
            f"{action_lines}"
        )

    def generate_steady_message(
        self,
        obs: VLMObservation,
        previous_obs: Optional[VLMObservation] = None,
        plant_profile: Optional[PlantProfile] = None,
    ) -> str:
        """Generate a plant-voice message when plant is healthy or steady/improving (NO_ACTION).

        Per production architecture Step 8b: Always uses fast static templates (0 tokens, < 1ms)
        to eliminate LLM latency and cost on healthy/steady checks.
        """
        is_improving = (
            previous_obs is not None
            and previous_obs.health_status in (HealthStatus.UNHEALTHY, HealthStatus.POSSIBLY_UNHEALTHY)
            and (
                obs.health_status == HealthStatus.HEALTHY
                or (previous_obs.health_status == HealthStatus.UNHEALTHY and obs.health_status == HealthStatus.POSSIBLY_UNHEALTHY)
            )
        )

        if is_improving:
            return "I'm feeling much better today and bouncing back! Thanks for taking good care of me."
        return "I'm feeling great and thriving today! Leaves are happy and soaking up the room. Thanks for checking in on me!"

    def generate_info_request_message(
        self,
        reason: str,
        plant_profile: Optional[PlantProfile] = None,
    ) -> str:
        """Generate a plant-voice message when image quality/consensus is too low (REQUEST_MORE_INFORMATION).

        Per production architecture Step 8a: Uses fast static templates (0 tokens, < 1ms)
        prompting the user to retake the photo without incurring LLM charges.
        """
        return "Hmm, I couldn't get a clear look at my leaves in that photo — it might be a bit too blurry or dark. Could you snap another clear photo for me?"
