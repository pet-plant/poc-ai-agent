"""CLI Scenario Runner for the Post-VLM Pipeline POC."""

import argparse
import json
import sys
from io import TextIOWrapper
from pathlib import Path
from typing import Optional

from plant_poc.config import SCENARIOS_DIR, BASE_DIR
from plant_poc.llm import OllamaClient, MockLLMClient
from plant_poc.orchestration import PlantPipeline, PipelineStepResult
from plant_poc.schemas import VLMObservation, TriggerDecision
from plant_poc.vlm_adapter import parse_vlm_probe_result

# Default log output paths
LOG_PATH = BASE_DIR / "docs" / "scenario-results.log"
JSON_LOG_PATH = BASE_DIR / "docs" / "scenario-results.json"


class _Tee:
    """Writes to both stdout and an optional log file simultaneously."""

    def __init__(self, log_file: Optional[TextIOWrapper] = None):
        self._log = log_file

    def print(self, *args, **kwargs) -> None:  # noqa: A003
        print(*args, **kwargs)
        if self._log:
            # Replicate print() to the log file
            sep = kwargs.get("sep", " ")
            end = kwargs.get("end", "\n")
            self._log.write(sep.join(str(a) for a in args) + end)


def load_scenario_file(file_path: Path) -> tuple[str, str, list[VLMObservation]]:
    """Load scenario JSON returning (scenario_name, description, observations)."""
    with open(file_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    name = data.get("scenario", file_path.stem)
    desc = data.get("description", "No description available.")

    observations: list[VLMObservation] = []
    raw_list = data.get("observations") or data.get("probe_results", [])
    default_plant_id = data.get("plant_id", "plant-monstera-1")
    default_species = data.get("species", "Monstera deliciosa")

    for raw in raw_list:
        if isinstance(raw, dict) and "observation" in raw and isinstance(raw["observation"], dict) and "visible_stress_level" in raw["observation"]:
            # Native VLM PROBE RESULT payload
            p_id = raw.get("plant_id", default_plant_id)
            s_name = raw.get("species", default_species)
            observations.append(parse_vlm_probe_result(raw, plant_id=p_id, species=s_name))
        else:
            observations.append(VLMObservation.model_validate(raw))

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


def print_step_result(res: PipelineStepResult, tee: "_Tee") -> None:
    """Pretty print pipeline result for a single day (to terminal + optional log)."""
    obs = res.observation
    symptoms_summary = (
        ", ".join(f"{s.type}:{s.severity}" for s in obs.observations)
        if obs.observations
        else "no symptoms"
    )

    tee.print(f"\n  [Day {res.day_index}] Timestamp: {obs.timestamp.strftime('%Y-%m-%d %H:%M:%SZ')}")
    conf_detail = f"conf={obs.confidence:.2f}"
    if obs.consensus:
        conf_detail += f", consensus={obs.consensus.agreement:.2f} ({obs.consensus.runs} runs)"
    tee.print(f"  • Observation: status={obs.health_status.value} ({conf_detail}) | {symptoms_summary}")

    if obs.leaf_posture or obs.leaf_color_detail:
        visual_parts = []
        if obs.leaf_posture:
            visual_parts.append(f'posture="{obs.leaf_posture}"')
        if obs.leaf_color_detail:
            visual_parts.append(f'color="{obs.leaf_color_detail}"')
        tee.print(f"  • VLM Visual:  {' | '.join(visual_parts)}")

    tee.print(f"  • Trigger:     [{res.trigger_result.decision.value}] — {res.trigger_result.reason}")

    if res.companion_message:
        tee.print("\n  • Companion Output (Plant Voice):")
        for line in res.companion_message.splitlines():
            tee.print(f"    {line}")

    if res.care_plan:
        plan = res.care_plan
        tee.print(f"\n  • Care Plan:   Assessment: \"{plan.assessment}\" (conf={plan.confidence:.2f})")
        tee.print("    Actions:")
        for action in sorted(plan.actions, key=lambda a: a.priority):
            tee.print(f"      [{action.priority}] {action.action}")

    # Display the exact JSON response sent to the frontend for this day's check-in
    frontend_payload = res.to_frontend_dict()
    tee.print("\n  • Frontend JSON Response:")
    tee.print(json.dumps(frontend_payload, indent=4))


def format_scenario_json(
    name: str,
    path: Path,
    desc: str,
    results: list[PipelineStepResult],
) -> dict:
    """Format pipeline results into a clean, structured dictionary."""
    return {
        "scenario": name,
        "scenario_file": path.name,
        "description": desc,
        "days_processed": len(results),
        "steps": [res.to_frontend_dict() for res in results],
    }


def run_single_scenario(
    path: Path,
    use_mock: bool = False,
    use_companion_llm: bool = False,
    tee: Optional["_Tee"] = None,
) -> dict:
    """Execute a single scenario from file through an isolated pipeline."""
    if tee is None:
        tee = _Tee()
    name, desc, observations = load_scenario_file(path)
    tee.print("\n" + "=" * 80)
    tee.print(f"  SCENARIO: {name} ({path.name})")
    tee.print(f"  {desc}")
    tee.print("=" * 80)

    llm_client = MockLLMClient() if use_mock else OllamaClient()
    pipeline = PlantPipeline.create_default(
        llm_client=llm_client,
        use_companion_llm=use_companion_llm,
    )

    results = pipeline.run_scenario(observations)
    for res in results:
        print_step_result(res, tee)

    scenario_data = format_scenario_json(name, path, desc, results)

    tee.print("\n" + "-" * 80)
    tee.print(f"  Completed scenario: {name} ({len(results)} days processed)")
    tee.print("-" * 80)
    return scenario_data


def cmd_run_batch(
    scenario_arg: Optional[str] = None,
    use_mock: bool = False,
    use_companion_llm: bool = False,
    write_log: bool = False,
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

    # --scenario all always writes the log; single scenario writes only with --log
    should_log = write_log or scenario_arg.lower() == "all"

    log_file = None
    if should_log:
        LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        log_file = open(LOG_PATH, "w", encoding="utf-8")  # replaces existing log
        print(f"📝 Logging output to: {LOG_PATH}")

    try:
        tee = _Tee(log_file)

        # 2. Run all scenarios
        if scenario_arg.lower() == "all":
            tee.print("\n" + "#" * 80)
            tee.print("  RUNNING ALL SCENARIOS IN SEQUENCE")
            tee.print("#" * 80)
            success_count = 0
            batch_results = []
            for name, path, desc in scenarios:
                try:
                    s_data = run_single_scenario(
                        path,
                        use_mock=use_mock,
                        use_companion_llm=use_companion_llm,
                        tee=tee,
                    )
                    batch_results.append(s_data)
                    success_count += 1
                except Exception as e:
                    tee.print(f"\n[ERROR] Scenario {name} failed with error: {e}")

            tee.print("\n" + "=" * 80)
            tee.print(f"  BATCH SUMMARY: {success_count}/{len(scenarios)} scenarios completed successfully.")
            tee.print("=" * 80 + "\n")
            if should_log:
                print(f"✅ Results saved to: {LOG_PATH}")
                with open(JSON_LOG_PATH, "w", encoding="utf-8") as jf:
                    json.dump(batch_results, jf, indent=2)
                print(f"📊 Structured JSON saved to: {JSON_LOG_PATH}")
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
            tee.print(f"[ERROR] Scenario '{scenario_arg}' not found.")
            tee.print("Run 'plant-poc list-scenarios' to see available options.")
            sys.exit(1)

        s_data = run_single_scenario(
            target_path,
            use_mock=use_mock,
            use_companion_llm=use_companion_llm,
            tee=tee,
        )
        if should_log:
            print(f"✅ Results saved to: {LOG_PATH}")
            with open(JSON_LOG_PATH, "w", encoding="utf-8") as jf:
                json.dump([s_data], jf, indent=2)
            print(f"📊 Structured JSON saved to: {JSON_LOG_PATH}")
    finally:
        if log_file:
            log_file.close()


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
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Use LLM for companion layer (default: True). Use --no-companion-llm for template mode.",
    )
    run_parser.add_argument(
        "--log",
        action="store_true",
        help=f"Write output to {LOG_PATH} (replaces existing). Always on for --scenario all.",
    )

    args = parser.parse_args()

    if args.command == "list-scenarios":
        cmd_list_scenarios()
    elif args.command == "run-batch":
        use_companion_llm = args.companion_llm and not args.mock
        cmd_run_batch(
            scenario_arg=args.scenario,
            use_mock=args.mock,
            use_companion_llm=use_companion_llm,
            write_log=args.log,
        )
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
