# Mock LLM Integration Test Fixtures

> **Purpose:** Portable, offline test fixtures for verifying LLM pipeline outputs
> across all plant health scenarios — without requiring a running Ollama or OpenAI API.

## Directory Layout

```
mock_llm/
├── README.md                   # This file
├── responses/                  # Canned LLM response JSON files
│   ├── advice/                 # CarePlan (Care Advisor) mock responses
│   │   ├── healthy_baseline.json
│   │   ├── leaf_yellowing_mild.json
│   │   ├── leaf_yellowing_severe.json
│   │   ├── overwatering_stress.json
│   │   ├── underwatering_drought.json
│   │   ├── fungal_infection.json
│   │   ├── pest_infestation.json
│   │   ├── light_stress.json
│   │   └── multi_symptom.json
│   └── companion/              # Companion dialogue mock responses
│       ├── healthy_steady.json
│       ├── care_advice_message.json
│       ├── improvement_recovery.json
│       ├── retake_photo.json
│       └── crisis_alert.json
├── expected_outputs/           # Full pipeline expected outputs per scenario
│   ├── scenario_no_change.json
│   ├── scenario_new_symptom.json
│   ├── scenario_severity_increase.json
│   ├── scenario_improvement.json
│   ├── scenario_low_confidence.json
│   ├── scenario_health_status_change.json
│   └── scenario_multi_day.json
└── run_mock_tests.py           # Self-contained test runner script
```

## Quick Start

```bash
# From the poc-ai-agent project root:
cd fixtures/mock_llm

# Run all mock scenario tests (no LLM, no network)
python run_mock_tests.py

# Run a specific scenario
python run_mock_tests.py --scenario new_symptom

# Verbose output with full JSON diffs
python run_mock_tests.py --verbose

# Export results to JSON
python run_mock_tests.py --output results.json
```

## How It Works

1. **`responses/advice/`** — Contains pre-computed CarePlan JSONs that mock what the LLM *should* return for each plant condition. These are fed into `MockChatModel` as canned responses.

2. **`responses/companion/`** — Contains pre-computed companion dialogue strings for each pipeline branch (healthy, advice-needed, retake-photo, improvement).

3. **`expected_outputs/`** — Contains the complete expected `PipelineStepResult.to_frontend_dict()` output for each scenario. The test runner compares the actual pipeline output against these golden files.

4. **`run_mock_tests.py`** — Loads scenario fixtures from `fixtures/scenarios/`, injects the correct mock responses, runs the pipeline, and validates the output matches `expected_outputs/`.

## Adapting for the Server Repo

These fixtures follow the same schema contract defined in `docs/server-specification.md`. To use in the server repo:

1. Copy `responses/advice/` → `server/tests/mlops/fixtures/advice/`
2. Copy `responses/companion/` → `server/tests/mlops/fixtures/companion/`
3. Adapt `run_mock_tests.py` to import from `src.mlops.advice.runtime` / `src.mlops.companion.runtime`
4. The JSON schema for `CarePlan` and `CareAction` is identical (3NF normalized actions list)

## Schema Contract

All mock CarePlan responses conform to:

```json
{
  "plant_id": "plant-monstera-1",
  "status_label": "Short headline (≤40 chars)",
  "assessment": "Detailed botanical assessment paragraph",
  "confidence": 0.90,
  "actions": [
    {
      "id": "act_xxxxxxxx",
      "priority": 1,
      "action": "Detailed botanical action instruction",
      "label": "Short label (≤30 chars)",
      "type": "water|move|inspect|other"
    }
  ]
}
```
