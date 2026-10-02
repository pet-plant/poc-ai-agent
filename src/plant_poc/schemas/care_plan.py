"""Care plan, trigger decision, and trigger result schemas matching PRD §4."""

from enum import Enum
from typing import Literal
import uuid
from pydantic import BaseModel, Field

ActionType = Literal["water", "move", "inspect", "other"]


class TriggerDecision(str, Enum):
    NO_ACTION = "NO_ACTION"
    CARE_ADVICE_REQUIRED = "CARE_ADVICE_REQUIRED"
    REQUEST_MORE_INFORMATION = "REQUEST_MORE_INFORMATION"


class TriggerResult(BaseModel):
    decision: TriggerDecision
    reason: str


class CareAction(BaseModel):
    id: str = Field(
        default_factory=lambda: f"act_{uuid.uuid4().hex[:8]}",
        description="Unique identifier for button action tracking",
    )
    priority: int = Field(ge=1, description="1 is highest priority")
    action: str = Field(description="Detailed botanical action instruction")
    label: str = Field(
        default="Inspect plant",
        max_length=30,
        description="Short 2-3 word button label for mobile UI (e.g. 'Pause water')",
    )
    type: ActionType = Field(
        default="inspect",
        description="Action category for UI iconography: 'water' | 'move' | 'inspect' | 'other'",
    )


class CarePlan(BaseModel):
    id: str = Field(
        default_factory=lambda: f"cp_{uuid.uuid4().hex[:12]}",
        description="Unique identifier for historical tracking across app lifecycle",
    )
    plant_id: str
    status_label: str = Field(
        default="Plant issue detected",
        description="Short headline describing the issue (e.g. 'Overwatering stress')",
    )
    assessment: str
    confidence: float = Field(default=0.9, ge=0.0, le=1.0)
    actions: list[CareAction] = Field(default_factory=list)

