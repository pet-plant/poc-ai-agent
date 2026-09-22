"""In-process pipeline orchestrator connecting Event Engine, Care Advisor, and Companion."""

from dataclasses import dataclass, field
from typing import Optional
from plant_poc.event_engine import evaluate, detect_milestones
from plant_poc.registry import PlantRegistry, init_db
from plant_poc.knowledge import (
    KnowledgeRetriever,
    KnowledgeStore,
    init_knowledge_db,
    ingest_knowledge_directory,
)
from plant_poc.llm import LLMClient, OllamaClient
from plant_poc.agents.care_advisor import CareAdvisorAgent
from plant_poc.agents.companion import CompanionAgent
from plant_poc.schemas import (
    VLMObservation,
    TriggerResult,
    TriggerDecision,
    CarePlan,
    PlantProfile,
    PlantMilestone,
)
from plant_poc.config import KNOWLEDGE_DIR


@dataclass
class PipelineStepResult:
    """Output summary of processing a single day's observation."""
    day_index: int
    observation: VLMObservation
    trigger_result: TriggerResult
    care_plan: Optional[CarePlan] = None
    companion_message: Optional[str] = None
    milestones_triggered: list[PlantMilestone] = field(default_factory=list)

    def to_frontend_dict(self) -> dict:
        """Structured response payload ready to be sent directly to the frontend/client."""
        return {
            "day": self.day_index,
            "plant_id": self.observation.plant_id,
            "timestamp": self.observation.timestamp.isoformat(),
            "health_status": self.observation.health_status.value,
            "decision": self.trigger_result.decision.value,
            "companion_message": self.companion_message,
            "milestones_triggered": [
                {
                    "event_type": m.event_type.value,
                    "description": m.description,
                    "timestamp": m.timestamp.isoformat(),
                }
                for m in self.milestones_triggered
            ],
            "care_plan": (
                {
                    "assessment": self.care_plan.assessment,
                    "confidence": self.care_plan.confidence,
                    "actions": [
                        {"priority": a.priority, "action": a.action}
                        for a in sorted(self.care_plan.actions, key=lambda x: x.priority)
                    ],
                }
                if self.care_plan
                else None
            ),
        }


class PlantPipeline:
    """Orchestrates the post-VLM pipeline for plant observations."""

    def __init__(
        self,
        registry: PlantRegistry,
        care_advisor: CareAdvisorAgent,
        companion: CompanionAgent,
    ):
        self.registry = registry
        self.care_advisor = care_advisor
        self.companion = companion

    @classmethod
    def create_default(
        cls,
        llm_client: Optional[LLMClient] = None,
        use_companion_llm: bool = False,
    ) -> "PlantPipeline":
        """Factory creating an isolated pipeline instance with in-memory DBs."""
        client = llm_client or OllamaClient()

        # Isolated SQLite Plant Registry
        reg_conn = init_db(":memory:")
        registry = PlantRegistry(reg_conn)

        # Isolated Knowledge RAG
        k_conn = init_knowledge_db(":memory:")
        k_store = KnowledgeStore(k_conn)
        ingest_knowledge_directory(k_store, KNOWLEDGE_DIR)
        retriever = KnowledgeRetriever(k_store)

        advisor = CareAdvisorAgent(client, registry, retriever)
        companion = CompanionAgent(client, use_llm=use_companion_llm)

        return cls(registry=registry, care_advisor=advisor, companion=companion)

    def process_observation(
        self,
        obs: VLMObservation,
        day_index: int = 1,
        require_consensus: bool = False,
    ) -> PipelineStepResult:
        """Process a single day's observation through the pipeline with two-tier memory."""
        # 1. Fetch historical observation baseline and context
        previous_obs = self.registry.get_previous_observation(obs.plant_id)
        recent_history = self.registry.get_recent_observations(obs.plant_id, n=7)
        existing_milestones = self.registry.get_milestones(obs.plant_id)

        # 2. Evaluate deterministic Event Engine rules
        trigger_res = evaluate(
            new=obs,
            previous=previous_obs,
            require_consensus=require_consensus,
        )

        new_milestones: list[PlantMilestone] = []

        # 3. Save clean observation to registry for future days (do not pollute DB on low-confidence scans)
        if trigger_res.decision != TriggerDecision.REQUEST_MORE_INFORMATION:
            self.registry.save_observation(obs)

            # 4. Detect and record new milestones on clean observations
            new_milestones = detect_milestones(
                new_obs=obs,
                history=recent_history,
                existing_milestones=existing_milestones,
            )
            for m in new_milestones:
                self.registry.record_milestone(m)

        care_plan: Optional[CarePlan] = None
        companion_msg: Optional[str] = None
        profile = self.registry.get_plant_profile(obs.plant_id)

        # Combine all milestones for memory context
        all_milestones = existing_milestones + new_milestones

        # 5. Generate botanical CarePlan (if advice required) and Companion response for the owner
        if trigger_res.decision == TriggerDecision.CARE_ADVICE_REQUIRED:
            care_plan = self.care_advisor.advise(obs, trigger_res)
            companion_msg = self.companion.generate_message(
                care_plan=care_plan,
                plant_profile=profile,
                health_status=obs.health_status,
                recent_observations=recent_history,
                milestones=all_milestones,
            )
        elif trigger_res.decision == TriggerDecision.REQUEST_MORE_INFORMATION:
            companion_msg = self.companion.generate_info_request_message(
                reason=trigger_res.reason,
                plant_profile=profile,
            )
        else:  # NO_ACTION
            companion_msg = self.companion.generate_steady_message(
                obs=obs,
                previous_obs=previous_obs,
                plant_profile=profile,
            )

        # 6. Persist generated dialogue message to the observation record
        if trigger_res.decision != TriggerDecision.REQUEST_MORE_INFORMATION and companion_msg:
            obs.companion_message = companion_msg
            self.registry.update_observation_companion_message(
                plant_id=obs.plant_id,
                timestamp=obs.timestamp,
                companion_message=companion_msg,
            )

        return PipelineStepResult(
            day_index=day_index,
            observation=obs,
            trigger_result=trigger_res,
            care_plan=care_plan,
            companion_message=companion_msg,
            milestones_triggered=new_milestones,
        )

    def process_vlm_probe_result(
        self,
        probe_data: dict,
        plant_id: str,
        species: Optional[str] = None,
        day_index: int = 1,
        require_consensus: bool = True,
    ) -> PipelineStepResult:
        """Process an aggregated VLM PROBE RESULT dictionary through the pipeline."""
        from plant_poc.vlm_adapter import parse_vlm_probe_result

        obs = parse_vlm_probe_result(data=probe_data, plant_id=plant_id, species=species)
        return self.process_observation(obs, day_index=day_index, require_consensus=require_consensus)

    def run_scenario(self, observations: list[VLMObservation]) -> list[PipelineStepResult]:
        """Execute a sequence of multi-day observations in isolation."""
        results = []
        for idx, obs in enumerate(observations, start=1):
            res = self.process_observation(obs, day_index=idx)
            results.append(res)
        return results
