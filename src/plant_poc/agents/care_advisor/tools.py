"""Tool definitions and adapter bindings for the Care Advisor Agent using LangChain @tool."""

from __future__ import annotations

from typing import Optional
from langchain_core.tools import BaseTool, tool

from plant_poc.knowledge import KnowledgeRetriever
from plant_poc.registry import PlantRegistry


def build_care_advisor_tools(
    registry: PlantRegistry,
    retriever: KnowledgeRetriever,
) -> list[BaseTool]:
    """Build the list of LangChain BaseTools wired to registry and knowledge retriever."""

    @tool
    def get_plant_profile(plant_id: str) -> dict:
        """Retrieve plant species, location, and care preferences."""
        profile = registry.get_plant_profile(plant_id)
        if not profile:
            profile = registry.ensure_default_profile(plant_id)
        return profile.model_dump()

    @tool
    def get_recent_observations(plant_id: str, n: int = 5) -> list[dict]:
        """Retrieve chronological recent observations for the plant."""
        obs_list = registry.get_recent_observations(plant_id, n=n)
        return [
            {
                "timestamp": o.timestamp.isoformat(),
                "health_status": o.health_status.value,
                "confidence": o.confidence,
                "observations": [item.model_dump() for item in o.observations],
            }
            for o in obs_list
        ]

    @tool
    def get_care_history(plant_id: str, n: int = 3) -> list[dict]:
        """Retrieve previous care plans and diagnostic history for the plant."""
        plans = registry.get_recent_care_plans(plant_id, n=n)
        return [p.model_dump() for p in plans]

    @tool
    def search_plant_knowledge(
        species: str,
        topic: Optional[str] = None,
        symptoms: Optional[list[str]] = None,
    ) -> list[dict]:
        """Search curated botanical knowledge for species and symptom causes."""
        results = retriever.search_plant_knowledge(
            species=species, topic=topic, symptoms=symptoms or [], top_k=2
        )
        return [
            {
                "topic": r.chunk.topic,
                "content": r.chunk.content,
                "score": round(r.score, 3),
            }
            for r in results
        ]

    return [
        get_plant_profile,
        get_recent_observations,
        get_care_history,
        search_plant_knowledge,
    ]
