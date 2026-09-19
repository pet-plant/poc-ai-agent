"""Observation and plant profile schemas matching PRD §3 and §4."""

from datetime import datetime
from enum import Enum
from typing import Literal
from pydantic import BaseModel, Field


class HealthStatus(str, Enum):
    HEALTHY = "healthy"
    POSSIBLY_UNHEALTHY = "possibly_unhealthy"
    UNHEALTHY = "unhealthy"


class Observation(BaseModel):
    type: str  # e.g. "leaf_yellowing", "drooping", "brown_spots"
    severity: Literal["mild", "moderate", "severe"]
    confidence: float = Field(ge=0.0, le=1.0)


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


class PlantProfile(BaseModel):
    plant_id: str
    species: str
    nickname: str
    location: str
    care_preferences: dict[str, str] = Field(default_factory=dict)
