#!/usr/bin/env python3
"""Portable test runner for verifying LLM pipeline outputs across plant health scenarios.

Offline execution using canned mock LLM responses — requires no running Ollama or OpenAI API.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

# Ensure project root and src are in sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
SRC_DIR = PROJECT_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from plant_poc.config import SCENARIOS_DIR
from plant_poc.llm.mock import MockChatModel
from plant_poc.orchestration import PlantPipeline
from plant_poc.schemas import TriggerDecision, VLMObservation

FIXTURES_DIR = Path(__file__).resolve().parent
RESPONSES_DIR = FIXTURES_DIR / "responses"
EXPECTED_DIR = FIXTURES_DIR / "expected_outputs"

SCENARIO_MAPPING: dict[str, dict[str, Any]] = {
    "no_change": {
        "file": "no_change.json",
        "expected": "scenario_no_change.json",
        "mock_advice": [],
        "mock_companion": "responses/companion/healthy_steady.json",
    },
    "new_symptom": {
        "file": "new_symptom.json",
        "expected": "scenario_new_symptom.json",
        "mock_advice": ["responses/advice/leaf_yellowing_mild.json"],
        "mock_companion": "responses/companion/care_advice_message.json",
    },
    "severity_increase": {
        "file": "severity_increase.json",
        "expected": "scenario_severity_increase.json",
        "mock_advice": [
            "responses/advice/leaf_yellowing_mild.json",
            "responses/advice/leaf_yellowing_severe.json",
        ],
        "mock_companion": "responses/companion/crisis_alert.json",
    },
    "improvement": {
        "file": "improvement.json",
        "expected": "scenario_improvement.json",
        "mock_advice": ["responses/advice/leaf_yellowing_severe.json"],
        "mock_companion": "responses/companion/improvement_recovery.json",
    },
    "health_status_change": {
        "file": "health_status_change.json",
        "expected": "scenario_health_status_change.json",
        "mock_advice": ["responses/advice/overwatering_stress.json"],
        "mock_companion": "responses/companion/care_advice_message.json",
    },
    "multi_day": {
        "file": "milestone_lifecycle.json",
        "expected": "scenario_multi_day.json",
        "mock_advice": [
            "responses/advice/fungal_infection.json",
            "responses/advice/multi_symptom.json",
        ],
        "mock_companion": "responses/companion/improvement_recovery.json",
    },
}


def load_canned_json(rel_path: str | None) -> dict[str, Any] | None:
    if not rel_path:
        return None
    full_path = FIXTURES_DIR / rel_path
    if not full_path.exists():
        return None
    with open(full_path, "r", encoding="utf-8") as f:
        return json.load(f)


def run_scenario(
    name: str,
    spec: dict[str, Any],
    verbose: bool = False,
) -> dict[str, Any]:
    scenario_path = SCENARIOS_DIR / spec["file"]
    with open(scenario_path, "r", encoding="utf-8") as f:
        scenario_data = json.load(f)

    expected_path = EXPECTED_DIR / spec["expected"]
    with open(expected_path, "r", encoding="utf-8") as f:
        expected_data = json.load(f)

    observations = [
        VLMObservation.model_validate(o) for o in scenario_data["observations"]
    ]

    # Prepare canned mock LLM responses
    canned_responses: list[str] = []
    for advice_path in spec.get("mock_advice", []):
        advice_json = load_canned_json(advice_path)
        if advice_json is not None:
            canned_responses.append(json.dumps(advice_json))

    companion_json = load_canned_json(spec.get("mock_companion"))
    if companion_json is not None and "message" in companion_json:
        # Provide companion message response for each step
        for _ in range(len(observations)):
            canned_responses.append(companion_json["message"])

    mock_llm = MockChatModel(responses=canned_responses)
    pipeline = PlantPipeline.create_default(llm=mock_llm)

    step_results = pipeline.run_scenario(observations)

    # Validate output against expected
    expected_decisions = expected_data.get("expected_decisions", [])
    actual_decisions = [r.trigger_result.decision.value for r in step_results]

    checks: list[tuple[str, bool, str]] = []

    # Check 1: Step counts match
    checks.append((
        "step_count",
        len(step_results) == len(observations),
        f"Expected {len(observations)} steps, got {len(step_results)}",
    ))

    # Check 2: Decisions match expected
    checks.append((
        "decision_sequence",
        actual_decisions == expected_decisions,
        f"Expected {expected_decisions}, got {actual_decisions}",
    ))

    # Check 3: Care plan generated when CARE_ADVICE_REQUIRED
    has_advice_decision = any(
        d == TriggerDecision.CARE_ADVICE_REQUIRED.value for d in actual_decisions
    )
    has_care_plan = any(r.care_plan is not None for r in step_results)
    if has_advice_decision:
        checks.append((
            "care_plan_generated",
            has_care_plan,
            "Care plan should be generated when CARE_ADVICE_REQUIRED",
        ))
        if has_care_plan:
            # Check actions in care plan
            for r in step_results:
                if r.care_plan:
                    checks.append((
                        "actions_normalized",
                        len(r.care_plan.actions) > 0,
                        f"Care plan must have actions (found {len(r.care_plan.actions)})",
                    ))
                    # Check action fields
                    for a in r.care_plan.actions:
                        checks.append((
                            f"action_schema_{a.id}",
                            bool(a.id and a.label and a.action and a.type),
                            f"Action {a.id} must have id, label, action, type",
                        ))
    else:
        checks.append((
            "no_spurious_care_plan",
            not has_care_plan,
            "No care plan expected for non-advice scenarios",
        ))

    # Check 4: Companion message present in all steps
    all_have_messages = all(bool(r.companion_message) for r in step_results)
    checks.append((
        "companion_message_generated",
        all_have_messages,
        "Every step should have a companion dialogue message",
    ))

    all_passed = all(passed for _, passed, _ in checks)

    output_details = [r.to_frontend_dict() for r in step_results]

    return {
        "scenario": name,
        "description": expected_data.get("description", ""),
        "passed": all_passed,
        "steps_count": len(step_results),
        "actual_decisions": actual_decisions,
        "expected_decisions": expected_decisions,
        "checks": checks,
        "frontend_output": output_details,
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run portable mock LLM scenario tests for Pet Plant pipeline"
    )
    parser.add_argument(
        "--scenario",
        choices=list(SCENARIO_MAPPING.keys()),
        help="Run only a specific scenario",
    )
    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Show detailed step output and checks",
    )
    parser.add_argument(
        "--output",
        "-o",
        type=Path,
        help="Export results summary to JSON file",
    )
    args = parser.parse_args()

    scenarios_to_run = (
        {args.scenario: SCENARIO_MAPPING[args.scenario]}
        if args.scenario
        else SCENARIO_MAPPING
    )

    print("=" * 68)
    print(" PET PLANT POC — OFFLINE MOCK LLM SCENARIO VERIFICATION ")
    print("=" * 68)

    results: list[dict[str, Any]] = []
    all_passed = True

    for name, spec in scenarios_to_run.items():
        res = run_scenario(name, spec, verbose=args.verbose)
        results.append(res)
        status_icon = "✓ PASS" if res["passed"] else "✗ FAIL"
        if not res["passed"]:
            all_passed = False

        print(f"\n[{status_icon}] Scenario: {name}")
        print(f"       Description: {res['description']}")
        print(f"       Decisions:   {' -> '.join(res['actual_decisions'])}")

        if args.verbose or not res["passed"]:
            for check_name, passed, msg in res["checks"]:
                mark = "  ✓" if passed else "  ✗"
                print(f"    {mark} {check_name}: {msg}")

            if args.verbose:
                for idx, step in enumerate(res["frontend_output"], 1):
                    print(f"\n      --- Day {idx} Result Envelope ---")
                    print(f"      Decision:  {step.get('decision')}")
                    if step.get("care_plan"):
                        cp = step["care_plan"]
                        print(f"      Headline:  {cp.get('status_label')}")
                        print(f"      Assessment: {cp.get('assessment')[:80]}...")
                        print(f"      Actions ({len(cp.get('actions', []))}):")
                        for act in cp.get("actions", []):
                            print(f"        • [{act.get('type')}] {act.get('label')}: {act.get('action')}")
                    msg_preview = step.get("companion_message", "")
                    if msg_preview:
                        print(f"      Companion: \"{msg_preview[:80]}...\"")

    print("\n" + "=" * 68)
    total = len(results)
    passed_count = sum(1 for r in results if r["passed"])
    print(f" SUMMARY: {passed_count}/{total} Scenarios Passed")
    print("=" * 68)

    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            json.dump(results, f, indent=2, default=str)
        print(f"Detailed output written to {args.output}")

    if not all_passed:
        sys.exit(1)


if __name__ == "__main__":
    main()
