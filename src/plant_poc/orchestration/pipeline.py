"""In-process pipeline orchestrator connecting Event Engine, Care Advisor, and Companion."""

from dataclasses import dataclass
from typing import Optional
from plant_poc.event_engine import evaluate
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
    ) -> PipelineStepResult:
        """Process a single day's observation through the pipeline."""
        # 1. Fetch previous observation from registry
        previous_obs = self.registry.get_previous_observation(obs.plant_id)

        # 2. Evaluate deterministic Event Engine rules
        trigger_res = evaluate(new=obs, previous=previous_obs)

        # 3. Save new observation to registry for future days
        self.registry.save_observation(obs)

        care_plan: Optional[CarePlan] = None
        companion_msg: Optional[str] = None

        # 4. If care advice required, run Care Advisor and Companion
        if trigger_res.decision == TriggerDecision.CARE_ADVICE_REQUIRED:
            care_plan = self.care_advisor.advise(obs, trigger_res)
            profile = self.registry.get_plant_profile(obs.plant_id)
            companion_msg = self.companion.generate_message(care_plan, profile, health_status=obs.health_status)

        return PipelineStepResult(
            day_index=day_index,
            observation=obs,
            trigger_result=trigger_res,
            care_plan=care_plan,
            companion_message=companion_msg,
        )

    def run_scenario(self, observations: list[VLMObservation]) -> list[PipelineStepResult]:
        """Execute a sequence of multi-day observations in isolation."""
        results = []
        for idx, obs in enumerate(observations, start=1):
            res = self.process_observation(obs, day_index=idx)
            results.append(res)
        return results
