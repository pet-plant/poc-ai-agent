"""Companion Layer — plant personality projector (speaks AS the plant in first-person)."""

from typing import Optional
from plant_poc.agents.companion.prompts import (
    get_companion_system_prompt,
    format_companion_user_prompt,
)
from plant_poc.agents.companion.validator import validate_fact_preservation
from plant_poc.llm import LLMClient
from plant_poc.schemas import CarePlan, PlantProfile, HealthStatus


class CompanionAgent:
    """Generates plant-voice messages from structured CarePlans — the plant speaks as itself."""

    def __init__(
        self,
        llm_client: Optional[LLMClient] = None,
        use_llm: bool = True,
    ):
        self.llm_client = llm_client
        self.use_llm = use_llm

    def generate_message(
        self,
        care_plan: CarePlan,
        plant_profile: Optional[PlantProfile] = None,
        health_status: Optional[HealthStatus] = None,
    ) -> str:
        """Generate a first-person plant-voice message, falling back to 3rd-person template if LLM unavailable."""
        nickname = plant_profile.nickname if plant_profile else "your plant"
        status_str = health_status.value if health_status else "healthy"

        # Primary: LLM speaks AS the plant in first-person
        if self.use_llm and self.llm_client:
            action_texts = [a.action for a in care_plan.actions]
            system_prompt = get_companion_system_prompt(status_str)
            user_prompt = format_companion_user_prompt(
                plant_nickname=nickname,
                assessment=care_plan.assessment,
                actions=action_texts,
                health_status=status_str,
            )
            try:
                res = self.llm_client.chat(
                    [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt},
                    ],
                    temperature=0.7,
                )
                llm_text = (res.content or "").strip()
                is_valid, missing = validate_fact_preservation(care_plan, llm_text)
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

