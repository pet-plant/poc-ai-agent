"""Companion Layer turning structured CarePlans into friendly conversational messages."""

from typing import Optional
from plant_poc.agents.companion.prompts import (
    COMPANION_SYSTEM_PROMPT,
    format_companion_user_prompt,
)
from plant_poc.agents.companion.validator import validate_fact_preservation
from plant_poc.llm import LLMClient
from plant_poc.schemas import CarePlan, PlantProfile


class CompanionAgent:
    """Generates friendly companion messages from structured CarePlans with fact-preservation."""

    def __init__(
        self,
        llm_client: Optional[LLMClient] = None,
        use_llm: bool = False,
    ):
        self.llm_client = llm_client
        self.use_llm = use_llm

    def generate_message(
        self,
        care_plan: CarePlan,
        plant_profile: Optional[PlantProfile] = None,
    ) -> str:
        """Generate friendly message ensuring all actions are accurately reflected."""
        nickname = plant_profile.nickname if plant_profile else "your plant"

        # If LLM mode is enabled and client available, try LLM first
        if self.use_llm and self.llm_client:
            action_texts = [a.action for a in care_plan.actions]
            prompt = format_companion_user_prompt(nickname, care_plan.assessment, action_texts)
            res = self.llm_client.chat(
                [
                    {"role": "system", "content": COMPANION_SYSTEM_PROMPT},
                    {"role": "user", "content": prompt},
                ],
                temperature=0.3,
            )
            llm_text = (res.content or "").strip()
            is_valid, missing = validate_fact_preservation(care_plan, llm_text)
            if is_valid:
                return llm_text

        # Default / Fallback: Deterministic friendly template
        return self._format_template(care_plan, nickname)

    def _format_template(self, care_plan: CarePlan, nickname: str) -> str:
        """Deterministic friendly template formatter."""
        if not care_plan.actions:
            return f"Good news! {nickname} is doing well. {care_plan.assessment}"

        action_lines = "\n".join(
            f"  • {item.action}"
            for item in sorted(care_plan.actions, key=lambda x: x.priority)
        )
        return (
            f"Hey there! Here's an update on {nickname}:\n"
            f"{care_plan.assessment}\n\n"
            f"Here is what we should do next to help {nickname} thrive:\n"
            f"{action_lines}\n\n"
            f"You've got this! Let's keep a close eye on the progress."
        )
