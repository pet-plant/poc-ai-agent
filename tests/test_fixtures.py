import json
from pathlib import Path
import pytest
from plant_poc.config import SCENARIOS_DIR
from plant_poc.schemas import VLMObservation

EXPECTED_SCENARIOS = [
    "no_change.json",
    "new_symptom.json",
    "health_status_change.json",
    "severity_increase.json",
    "low_confidence.json",
    "improvement.json",
    "mixed_multiday.json",
]


def test_scenario_files_exist():
    for name in EXPECTED_SCENARIOS:
        path = SCENARIOS_DIR / name
        assert path.exists(), f"Missing scenario file: {name}"


@pytest.mark.parametrize("scenario_name", EXPECTED_SCENARIOS)
def test_scenario_validates_against_vlm_schema(scenario_name):
    path = SCENARIOS_DIR / scenario_name
    with open(path, "r") as f:
        data = json.load(f)

    assert "scenario" in data
    assert "description" in data
    assert "observations" in data
    assert len(data["observations"]) > 0

    for raw_obs in data["observations"]:
        obs = VLMObservation.model_validate(raw_obs)
        assert obs.plant_id
        assert obs.confidence >= 0.0
