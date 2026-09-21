"""Care Advisor Agent implementation."""

from plant_poc.agents.base import run_tool_agent
from plant_poc.agents.care_advisor.prompts import (
    CARE_ADVISOR_SYSTEM_PROMPT,
    format_advisor_user_prompt,
)
from plant_poc.agents.care_advisor.tools import build_care_advisor_tools
from plant_poc.knowledge import KnowledgeRetriever
from plant_poc.llm import LLMClient
from plant_poc.registry import PlantRegistry
from plant_poc.schemas import CarePlan, TriggerResult, VLMObservation


class CareAdvisorAgent:
    """Agent that reasons over plant history & knowledge to output a structured CarePlan."""

    def __init__(
        self,
        llm_client: LLMClient,
        registry: PlantRegistry,
        retriever: KnowledgeRetriever,
    ):
        self.llm_client = llm_client
        self.registry = registry
        self.retriever = retriever
        self.tools = build_care_advisor_tools(registry, retriever)

    def advise(
        self,
        observation: VLMObservation,
        trigger_result: TriggerResult,
    ) -> CarePlan:
        """Run the Care Advisor reasoning loop to produce a CarePlan."""
        # Summarize observations for user prompt
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
            consensus_agreement=observation.consensus.agreement if observation.consensus else None,
        )

        plan = run_tool_agent(
            client=self.llm_client,
            system_prompt=CARE_ADVISOR_SYSTEM_PROMPT,
            user_prompt=user_prompt,
            tools=self.tools,
            response_model=CarePlan,
            max_turns=5,
            max_retries=1,
        )

        # Persist plan in registry
        self.registry.save_care_plan(observation.plant_id, plan)
        return plan
