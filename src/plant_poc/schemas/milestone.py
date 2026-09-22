"""Schemas for plant episodic life events and milestones."""

from datetime import datetime
from enum import Enum
from typing import Optional
from pydantic import BaseModel, Field


class MilestoneType(str, Enum):
    """Types of significant milestones in a plant's lifecycle."""
    FIRST_SYMPTOM = "first_symptom"
    HEALTH_CRISIS = "health_crisis"
    SEVERE_EPISODE = "severe_episode"
    NEAR_DEATH = "near_death"
    FULL_RECOVERY = "full_recovery"


class PlantMilestone(BaseModel):
    """Record of a major episodic life event in a plant's history."""
    id: Optional[int] = None
    plant_id: str
    timestamp: datetime
    event_type: MilestoneType
    description: str
    resolved_at: Optional[datetime] = None
