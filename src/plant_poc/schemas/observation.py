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
    confidence: float = Field(ge=0.0, le=1.0)


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
    confidence: float = Field(ge=0.0, le=1.0)
    observations: list[Observation] = Field(default_factory=list)
    consensus: VLMConsensus | None = Field(
        default=None,
        description="Multi-run consensus data from VLM probe. Preferred over confidence for Event Engine decisions.",
    )
    leaf_posture: str | None = Field(
        default=None,
        description="VLM-detected leaf posture, e.g. 'upright', 'drooping', 'curled'",
    )
    leaf_color_detail: str | None = Field(
        default=None,
        description="VLM-detected color description, e.g. 'dark green with glossy texture'",
    )
    image_refs: list[str] = Field(
        default_factory=list,
        description="URIs/paths of images analyzed by VLM (for audit trail)",
    )
    companion_message: str | None = Field(
        default=None,
        description="Companion plant dialogue message generated for this observation",
    )


class PlantProfile(BaseModel):
    plant_id: str
    species: str
    nickname: str
    location: str
    care_preferences: dict[str, str] = Field(default_factory=dict)
