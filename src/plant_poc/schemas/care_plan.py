"""Care plan, trigger decision, and trigger result schemas matching PRD §4."""

from enum import Enum
from pydantic import BaseModel, Field


class TriggerDecision(str, Enum):
    NO_ACTION = "NO_ACTION"
    CARE_ADVICE_REQUIRED = "CARE_ADVICE_REQUIRED"
    REQUEST_MORE_INFORMATION = "REQUEST_MORE_INFORMATION"


class TriggerResult(BaseModel):
    decision: TriggerDecision
    reason: str


class CareAction(BaseModel):
    action: str
    priority: int = Field(ge=1, description="1 is highest priority")


class CarePlan(BaseModel):
    plant_id: str
    assessment: str
    confidence: float = Field(ge=0.0, le=1.0)
    actions: list[CareAction] = Field(default_factory=list)
