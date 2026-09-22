"""Companion Layer — plant personality projector (speaks AS the plant in first-person)."""

from typing import Optional
from plant_poc.agents.companion.prompts import (
    get_companion_system_prompt,
    format_companion_user_prompt,
)
from plant_poc.agents.companion.validator import validate_fact_preservation
from plant_poc.llm import LLMClient
from plant_poc.schemas import (
    CarePlan,
    PlantProfile,
    HealthStatus,
    VLMObservation,
    PlantMilestone,
)


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
        recent_observations: Optional[list[VLMObservation]] = None,
        milestones: Optional[list[PlantMilestone]] = None,
    ) -> str:
        """Generate a first-person plant-voice message with two-tier memory context."""
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
                recent_observations=recent_observations,
                milestones=milestones,
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
        # Check if improving from a worse state
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
