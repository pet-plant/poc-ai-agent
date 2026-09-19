"""Tool definitions and adapter bindings for the Care Advisor Agent."""

from typing import Optional
from plant_poc.agents.base import AgentTool
from plant_poc.registry import PlantRegistry
from plant_poc.knowledge import KnowledgeRetriever


def build_care_advisor_tools(
    registry: PlantRegistry,
    retriever: KnowledgeRetriever,
) -> list[AgentTool]:
    """Build the list of AgentTools wired to registry and knowledge retriever."""

    def get_plant_profile(plant_id: str) -> dict:
        profile = registry.get_plant_profile(plant_id)
        if not profile:
            profile = registry.ensure_default_profile(plant_id)
        return profile.model_dump()

    def get_recent_observations(plant_id: str, n: int = 5) -> list[dict]:
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

    def get_care_history(plant_id: str, n: int = 3) -> list[dict]:
        plans = registry.get_recent_care_plans(plant_id, n=n)
        return [p.model_dump() for p in plans]

    def search_plant_knowledge(
        species: str,
        topic: Optional[str] = None,
        symptoms: Optional[list[str]] = None,
    ) -> list[dict]:
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
        AgentTool(
            name="get_plant_profile",
            description="Retrieve plant species, location, and care preferences.",
            parameters={
                "type": "object",
                "properties": {
                    "plant_id": {
                        "type": "string",
                        "description": "Unique identifier of the plant",
                    }
                },
                "required": ["plant_id"],
            },
            func=get_plant_profile,
        ),
        AgentTool(
            name="get_recent_observations",
            description="Retrieve chronological recent observations for the plant.",
            parameters={
                "type": "object",
                "properties": {
                    "plant_id": {
                        "type": "string",
                        "description": "Unique identifier of the plant",
                    },
                    "n": {
                        "type": "integer",
                        "description": "Number of observations to return (default 5)",
                    },
                },
                "required": ["plant_id"],
            },
            func=get_recent_observations,
        ),
        AgentTool(
            name="get_care_history",
            description="Retrieve previous care plans and diagnostic history for the plant.",
            parameters={
                "type": "object",
                "properties": {
                    "plant_id": {
                        "type": "string",
                        "description": "Unique identifier of the plant",
                    },
                    "n": {
                        "type": "integer",
                        "description": "Number of care plans to return (default 3)",
                    },
                },
                "required": ["plant_id"],
            },
            func=get_care_history,
        ),
        AgentTool(
            name="search_plant_knowledge",
            description="Search curated botanical knowledge for species and symptom causes.",
            parameters={
                "type": "object",
                "properties": {
                    "species": {
                        "type": "string",
                        "description": "Plant species name, e.g. 'Monstera deliciosa'",
                    },
                    "topic": {
                        "type": "string",
                        "description": "Care topic like 'watering', 'yellowing', 'repotting'",
                    },
                    "symptoms": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "List of symptom keywords, e.g. ['leaf_yellowing']",
                    },
                },
                "required": ["species"],
            },
            func=search_plant_knowledge,
        ),
    ]
