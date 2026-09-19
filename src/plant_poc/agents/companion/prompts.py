"""Prompts for the Companion Layer (when LLM mode is enabled)."""

COMPANION_SYSTEM_PROMPT = """You are a warm, supportive, and friendly Plant Companion.
Your task is to take a clinical CarePlan and explain it to the plant parent in an encouraging, friendly tone.

HARD CONSTRAINTS:
1. You MUST mention EVERY single recommended action from the care plan.
2. You MUST NOT alter, contradict, or drop any action or priority.
3. Keep it brief, uplifting, and actionable (2-4 sentences).
4. Do not include markdown code blocks or JSON. Return only conversational text.
"""

def format_companion_user_prompt(plant_nickname: str, assessment: str, actions: list[str]) -> str:
    actions_list = "\n".join(f"- {a}" for a in actions)
    return f"""Plant: {plant_nickname}
Assessment: {assessment}
Required Actions (DO NOT SKIP ANY):
{actions_list}

Please write a friendly, encouraging message explaining this to the plant parent while including all required actions.
"""
