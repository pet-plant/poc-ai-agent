# poc-ai-agent — Post-VLM Plant Care Pipeline

A proof-of-concept multi-agent pipeline that runs **after** a Vision Language Model (VLM) observes a plant photo.
Given a structured observation, it decides whether care advice is needed, reasons over plant history and knowledge, and delivers the care plan as a first-person message **spoken by the plant itself**.

---

## Architecture

```
fixtures/scenarios/*.json   ← mock VLM observations (input)
         │
         ▼
      cli.py                ← entry point (plant-poc CLI)
         │
         ▼
orchestration/pipeline.py  ← wires everything together
    │              │
    ▼              ▼
registry/      event_engine/rules.py   ← deterministic, no LLM
(SQLite)            │
                    ├── NO_ACTION           → done
                    ├── REQUEST_MORE_INFO   → done
                    └── CARE_ADVICE_REQUIRED
                              │
                    ┌─────────┴──────────┐
                    ▼                    ▼
          knowledge/ (RAG)     agents/care_advisor/
          embeddings +         reasons over history
          cosine search        & knowledge → CarePlan
                                         │
                                         ▼
                               agents/companion/
                               plant speaks as itself
                               (first-person, LLM)
```

---

## Setup

> Requires Python ≥ 3.12 and [uv](https://github.com/astral-sh/uv) (or plain pip).

```bash
# Install dependencies and the CLI
uv pip install -e .
# or
pip install -e .
```

Copy and configure environment variables:

```bash
cp .env.example .env
```

| Variable                 | Default                     | Description                                |
| ------------------------ | --------------------------- | ------------------------------------------ |
| `OLLAMA_HOST`          | `http://localhost:11434`  | Ollama server URL                          |
| `OLLAMA_MODEL`         | `qwen2.5:latest`          | LLM used by Care Advisor + Companion       |
| `OLLAMA_EMBED_MODEL`   | `nomic-embed-text:latest` | Embedding model for Knowledge RAG          |
| `CONFIDENCE_THRESHOLD` | `0.5`                     | Below this confidence → request more info |
| `DEFAULT_SPECIES`      | `Monstera deliciosa`      | Fallback species when not in observation   |
| `SQLITE_DB_PATH`       | `:memory:`                | DB path (`:memory:` resets each run)     |

### Ollama setup (required for LLM features)

```bash
ollama serve                          # start Ollama if not running
ollama pull qwen2.5:latest            # LLM for Care Advisor + Companion
ollama pull nomic-embed-text:latest   # embedding model for Knowledge RAG
```

> **Without Ollama running**, the Care Advisor will fail and the Companion will fall back to a plain `[LLM unavailable]` summary template.

---

## Running Scenarios

```bash
# Run all 7 scenarios back to back (automatically writes docs/scenario-results.log)
plant-poc run-batch --scenario all

# Run a specific scenario by name (use --log to write/replace docs/scenario-results.log)
plant-poc run-batch --scenario health_status_change --log
plant-poc run-batch --scenario severity_increase
plant-poc run-batch --scenario new_symptom
plant-poc run-batch --scenario low_confidence
plant-poc run-batch --scenario improvement
plant-poc run-batch --scenario no_change
plant-poc run-batch --scenario mixed_multiday

# Additional CLI flags:
#   --companion-llm   Use LLM for companion persona projection instead of template
#   --mock            Use mock LLM responses offline (no Ollama required)
#   --log             Write/replace docs/scenario-results.log (default on for 'all')

# List all available scenarios
plant-poc list-scenarios

# Interactive picker (no flags — prompts you to choose)
plant-poc run-batch
```

### Scenario table

| Scenario                 | What it tests                                            | Expected trigger             |
| ------------------------ | -------------------------------------------------------- | ---------------------------- |
| `no_change`            | Same health + symptoms every day                         | `NO_ACTION`                |
| `new_symptom`          | A new symptom type appears                               | `CARE_ADVICE_REQUIRED`     |
| `health_status_change` | Health status flips (e.g. healthy → possibly_unhealthy) | `CARE_ADVICE_REQUIRED`     |
| `severity_increase`    | Same symptom, severity escalates                         | `CARE_ADVICE_REQUIRED`     |
| `low_confidence`       | Confidence drops below threshold                         | `REQUEST_MORE_INFORMATION` |
| `improvement`          | Severity decreases, nothing new                          | `NO_ACTION`                |
| `mixed_multiday`       | 5-day sequence covering multiple cases                   | Mixed per day                |

---

## Running Tests

```bash
# Run all tests
pytest

# Run with verbose output
pytest -v

# Run a specific test file
pytest tests/test_event_engine.py -v
pytest tests/test_companion.py -v
pytest tests/test_care_advisor.py -v
pytest tests/test_registry.py -v
pytest tests/test_knowledge_retriever.py -v
pytest tests/test_pipeline.py -v
pytest tests/test_e2e_scenarios.py -v

# Run tests matching a keyword
pytest -k "event_engine" -v
pytest -k "companion" -v
```

> Most tests use `MockLLMClient` and run **fully offline** (no Ollama needed).
> Tests in `test_care_advisor.py` and `test_e2e_scenarios.py` that hit the real LLM are skipped automatically when Ollama is unavailable.

---

## Project Structure

```
src/plant_poc/
├── config.py            # env vars + shared constants
├── schemas/             # shared Pydantic models (VLMObservation, CarePlan, ...)
├── registry/            # SQLite plant profiles, observations, care plans
├── event_engine/        # deterministic trigger rules (zero LLM)
├── knowledge/           # RAG: ingest → embed → cosine search
├── llm/                 # Ollama adapter (LLMClient interface)
├── agents/
│   ├── base.py          # shared tool-calling loop + schema-retry
│   ├── care_advisor/    # LLM agent → produces CarePlan
│   └── companion/       # plant speaks as itself in first-person
├── orchestration/
│   └── pipeline.py      # wires event_engine → care_advisor → companion
└── cli.py               # plant-poc CLI entry point

fixtures/
├── scenarios/           # one JSON file per test scenario
└── knowledge/           # .md care guides ingested into RAG

tests/                   # pytest test suite (offline-first)
```
