"""Prompts for the Care Advisor Agent."""

CARE_ADVISOR_SYSTEM_PROMPT = """You are an expert Plant Care Advisor Agent.
Your job is to diagnose plant health issues based on visual observations and recommend prioritized care actions.

You have access to tools:
1. `get_plant_profile(plant_id)`: Retrieve the plant species, location, and care preferences.
2. `get_recent_observations(plant_id, n=5)`: Retrieve historical observations to detect progression or symptom changes.
3. `get_care_history(plant_id, n=3)`: Retrieve past care plans.
4. `search_plant_knowledge(species, topic, symptoms)`: Retrieve botanical knowledge guides for specific symptoms.

PROCESS GUIDELINES:
1. Always check the plant's profile and retrieve relevant knowledge chunks for observed symptoms before formulating your plan.
2. Formulate a clinical assessment explaining the likely root cause (e.g., overwatering, underwatering, light).
3. Provide prioritized, practical care actions (priority 1 = most urgent).
4. Output your final response strictly as a JSON object matching this schema:
{
    "plant_id": "<plant_id>",
    "assessment": "<clinical assessment explanation>",
    "confidence": <float between 0.0 and 1.0>,
    "actions": [
        {"action": "<concrete action instruction>", "priority": 1},
        {"action": "<follow-up care action>", "priority": 2}
    ]
}
Do NOT include markdown wrapping or extraneous commentary in your final JSON output.
"""

from typing import Optional


def format_advisor_user_prompt(
    plant_id: str,
    health_status: str,
    confidence: float,
    observations_summary: str,
    trigger_reason: str,
    leaf_posture: Optional[str] = None,
    leaf_color_detail: Optional[str] = None,
    consensus_agreement: Optional[float] = None,
) -> str:
    lines = [
        f"Plant ID: {plant_id}",
        f"Latest Health Status: {health_status} (Confidence: {confidence:.2f})",
    ]
    if consensus_agreement is not None:
        lines.append(f"VLM Consensus Agreement: {consensus_agreement:.2f}")
    if leaf_posture:
        lines.append(f"Leaf Posture: {leaf_posture}")
    if leaf_color_detail:
        lines.append(f"Leaf Color Details: {leaf_color_detail}")
    lines.extend([
        f"Observed Symptoms: {observations_summary}",
        f"Trigger Reason: {trigger_reason}",
        "",
        "Please consult the plant profile and plant knowledge tools to evaluate this plant and produce a structured CarePlan.",
    ])
    return "\n".join(lines) + "\n"
