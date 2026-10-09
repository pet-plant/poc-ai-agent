"""Pydantic schemas representing input from the VLM and internal plant state."""

from datetime import datetime
from enum import Enum
from pydantic import BaseModel, Field


class HealthStatus(str, Enum):
    HEALTHY = "healthy"
    POSSIBLY_UNHEALTHY = "possibly_unhealthy"
    UNHEALTHY = "unhealthy"


class Observation(BaseModel):
    type: str  # e.g. "leaf_yellowing", "dry_tips", "drooping"
    severity: str  # "mild", "moderate", "severe"
    description: str  # Free-text description of the symptom from VLM


class VLMConsensus(BaseModel):
    """Consensus data from upstream VLM multi-run evaluation."""
    agreement: float = Field(
        ge=0.0,
        le=1.0,
        description="Fraction of runs that agreed on the health assessment (0.0 to 1.0)",
    )
    runs: int = Field(
        default=5,
        ge=1,
        description="Number of parallel VLM inference runs executed",
    )
    model_stated_average: float = Field(
        ge=0.0,
        le=1.0,
        description="Average of model's self-reported confidence across runs",
    )


class VLMObservation(BaseModel):
    plant_id: str
    species: str | None = Field(
        default=None,
        description="Plant species (e.g. 'Monstera deliciosa'). If provided, used to seed the plant profile.",
    )
    timestamp: datetime
    health_status: HealthStatus
    observations: list[Observation] = Field(default_factory=list)
    consensus: VLMConsensus | None = Field(
        default=None,
        description="Multi-run consensus data from VLM probe. Used by Event Engine for reliability gating.",
    )
    image_refs: list[str] = Field(
        default_factory=list,
        description="URIs/paths of images analyzed by VLM (for audit trail)",
    )
    description: str | None = Field(
        default=None,
        description="Summary visual description of symptoms observed",
    )
    companion_message: str | None = Field(
        default=None,
        description="Companion plant dialogue message generated for this observation",
    )

    @property
    def effective_confidence(self) -> float:
        """Derive confidence from consensus.model_stated_average for DB telemetry.

        Returns consensus.model_stated_average if consensus exists,
        otherwise a sensible default of 0.9.
        """
        if self.consensus is not None:
            return self.consensus.model_stated_average
        return 0.9


class PlantProfile(BaseModel):
    plant_id: str
    species: str
    nickname: str
    location: str
    care_preferences: dict[str, str] = Field(default_factory=dict)
    level: int = Field(default=1, ge=1, description="Gamification character level")
    xp_ratio: float = Field(
        default=0.0, ge=0.0, le=1.0, description="Progress ratio towards next level (0.0 to 1.0)"
    )
