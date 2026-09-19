"""CLI Scenario Runner for the Post-VLM Pipeline POC."""

import argparse
import json
import sys
from pathlib import Path
from typing import Optional

from plant_poc.config import SCENARIOS_DIR
from plant_poc.llm import OllamaClient, MockLLMClient
from plant_poc.orchestration import PlantPipeline, PipelineStepResult
from plant_poc.schemas import VLMObservation, TriggerDecision


def load_scenario_file(file_path: Path) -> tuple[str, str, list[VLMObservation]]:
    """Load scenario JSON returning (scenario_name, description, observations)."""
    with open(file_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    name = data.get("scenario", file_path.stem)
    desc = data.get("description", "No description available.")
    observations = [
        VLMObservation.model_validate(raw) for raw in data.get("observations", [])
    ]
    return name, desc, observations


def get_available_scenarios() -> list[tuple[str, Path, str]]:
    """Scan scenarios directory returning list of (name, file_path, description)."""
    scenarios = []
    if not SCENARIOS_DIR.exists():
        return []

    for path in sorted(SCENARIOS_DIR.glob("*.json")):
        try:
            name, desc, _ = load_scenario_file(path)
            scenarios.append((name, path, desc))
        except Exception as e:
            scenarios.append((path.stem, path, f"Error loading: {e}"))
    return scenarios


def cmd_list_scenarios() -> None:
    """Print all available scenarios with their descriptions."""
    scenarios = get_available_scenarios()
    print("\n" + "=" * 80)
    print("  AVAILABLE PLANT POC SCENARIOS")
    print("=" * 80)
    if not scenarios:
        print(f"No scenario files found in {SCENARIOS_DIR}")
        return

    for idx, (name, path, desc) in enumerate(scenarios, start=1):
        print(f"[{idx}] {name:<26} | {path.name:<28}")
        print(f"    Description: {desc}")
        print("-" * 80)
    print()


def print_step_result(res: PipelineStepResult) -> None:
    """Pretty print pipeline result for a single day."""
    obs = res.observation
    symptoms_summary = (
        ", ".join(f"{s.type}:{s.severity}" for s in obs.observations)
        if obs.observations
        else "no symptoms"
    )

    print(f"\n  [Day {res.day_index}] Timestamp: {obs.timestamp.strftime('%Y-%m-%d %H:%M:%SZ')}")
    print(f"  • Observation: status={obs.health_status.value} (conf={obs.confidence:.2f}) | {symptoms_summary}")
    print(f"  • Trigger:     [{res.trigger_result.decision.value}] — {res.trigger_result.reason}")

    if res.trigger_result.decision == TriggerDecision.CARE_ADVICE_REQUIRED and res.care_plan:
        plan = res.care_plan
        print(f"  • Care Plan:   Assessment: \"{plan.assessment}\" (conf={plan.confidence:.2f})")
        print("    Actions:")
        for action in sorted(plan.actions, key=lambda a: a.priority):
            print(f"      [{action.priority}] {action.action}")

        if res.companion_message:
            print("\n  • Companion Output:")
            for line in res.companion_message.splitlines():
                print(f"    {line}")
    elif res.trigger_result.decision == TriggerDecision.REQUEST_MORE_INFORMATION:
        print("  • Notice:      Image observation confidence too low. No care plan generated.")
    else:
        print("  • Notice:      No action needed. Plant is steady or improving.")


def run_single_scenario(
    path: Path,
    use_mock: bool = False,
    use_companion_llm: bool = False,
) -> bool:
    """Execute a single scenario from file through an isolated pipeline."""
    name, desc, observations = load_scenario_file(path)
    print("\n" + "=" * 80)
    print(f"  SCENARIO: {name} ({path.name})")
    print(f"  {desc}")
    print("=" * 80)

    llm_client = MockLLMClient() if use_mock else OllamaClient()
    pipeline = PlantPipeline.create_default(
        llm_client=llm_client,
        use_companion_llm=use_companion_llm,
    )

    results = pipeline.run_scenario(observations)
    for res in results:
        print_step_result(res)

    print("\n" + "-" * 80)
    print(f"  Completed scenario: {name} ({len(results)} days processed)")
    print("-" * 80)
    return True


def cmd_run_batch(
    scenario_arg: Optional[str] = None,
    use_mock: bool = False,
    use_companion_llm: bool = False,
) -> None:
    """Handle run-batch command."""
    scenarios = get_available_scenarios()
    if not scenarios:
        print(f"No scenario files found in {SCENARIOS_DIR}")
        return

    # 1. Interactive picker if no scenario specified
    if not scenario_arg:
        cmd_list_scenarios()
        while True:
            try:
                choice = input("Select scenario number (or 'all', 'q' to quit): ").strip()
                if choice.lower() in ("q", "quit", "exit"):
                    return
                if choice.lower() == "all":
                    scenario_arg = "all"
                    break
                idx = int(choice)
                if 1 <= idx <= len(scenarios):
                    scenario_arg = scenarios[idx - 1][1].name
                    break
                print(f"Please enter a number between 1 and {len(scenarios)}.")
            except ValueError:
                print("Invalid input. Please enter a valid number or 'all'.")

    # 2. Run all scenarios
    if scenario_arg.lower() == "all":
        print("\n" + "#" * 80)
        print("  RUNNING ALL SCENARIOS IN SEQUENCE")
        print("#" * 80)
        success_count = 0
        for name, path, desc in scenarios:
            try:
                run_single_scenario(path, use_mock=use_mock, use_companion_llm=use_companion_llm)
                success_count += 1
            except Exception as e:
                print(f"\n[ERROR] Scenario {name} failed with error: {e}")

        print("\n" + "=" * 80)
        print(f"  BATCH SUMMARY: {success_count}/{len(scenarios)} scenarios completed successfully.")
        print("=" * 80 + "\n")
        return

    # 3. Run single named scenario
    # Resolve by exact filename, filename without extension, or scenario name
    target_path = None
    for name, path, _ in scenarios:
        if scenario_arg in (name, path.name, path.stem):
            target_path = path
            break

    if not target_path:
        # Check if direct path was provided
        direct_path = Path(scenario_arg)
        if direct_path.exists():
            target_path = direct_path
        elif (SCENARIOS_DIR / scenario_arg).exists():
            target_path = SCENARIOS_DIR / scenario_arg
        elif (SCENARIOS_DIR / f"{scenario_arg}.json").exists():
            target_path = SCENARIOS_DIR / f"{scenario_arg}.json"

    if not target_path or not target_path.exists():
        print(f"[ERROR] Scenario '{scenario_arg}' not found.")
        print("Run 'plant-poc list-scenarios' to see available options.")
        sys.exit(1)

    run_single_scenario(target_path, use_mock=use_mock, use_companion_llm=use_companion_llm)


def main() -> None:
    """CLI entrypoint."""
    parser = argparse.ArgumentParser(
        prog="plant-poc",
        description="Post-VLM Pipeline Proof of Concept CLI",
    )
    subparsers = parser.add_subparsers(dest="command", help="Subcommand to execute")

    # list-scenarios
    subparsers.add_parser("list-scenarios", help="List all scenario fixtures")

    # run-batch
    run_parser = subparsers.add_parser("run-batch", help="Run scenario(s) through the pipeline")
    run_parser.add_argument(
        "--scenario",
        type=str,
        default=None,
        help="Scenario name, file name, or 'all'. Omit for interactive menu.",
    )
    run_parser.add_argument(
        "--mock",
        action="store_true",
        help="Use offline mock LLM instead of live Ollama.",
    )
    run_parser.add_argument(
        "--companion-llm",
        action="store_true",
        help="Use LLM for companion layer instead of template mode.",
    )

    args = parser.parse_args()

    if args.command == "list-scenarios":
        cmd_list_scenarios()
    elif args.command == "run-batch":
        cmd_run_batch(
            scenario_arg=args.scenario,
            use_mock=args.mock,
            use_companion_llm=args.companion_llm,
        )
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
