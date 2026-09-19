# PRD — POC: Post-VLM Pipeline (Event Engine → Knowledge RAG → Care Advisor → Companion)

**Status:** Draft for agent-driven implementation
**Scope:** Proof of concept only. Not production. No auth, no multi-tenant concerns, no MinIO/object storage, no real device integration.

---

## 1. Goal

Build a standalone, runnable POC that starts **after** the VLM observation step and proves out the rest of the pipeline:

```
VLM Observation (mocked input)
    → Event Engine (decide if action needed)
    → Care Advisor Agent (reason using Registry + Knowledge RAG)
    → Companion Layer (turn plan into friendly text)
```

Success = being able to pick a named scenario (or run all of them) from the command line, and see the correct trigger decision, structured care plan (when triggered), and friendly companion message for that scenario, end-to-end.

---

## 2. Explicitly out of scope for this POC

- The VLM itself / image capture / segmentation (`capture`, live `assessment` inference)
- Auth, roles, device bindings
- MinIO, S3-compatible storage, image handling of any kind
- Postgres-per-schema production setup — **use SQLite** for the POC
- The `orchestrator` event bus / async messaging — call functions directly, in-process
- Multi-user / multi-owner concerns — assume a single test user, a handful of test plants
- A real frontend — a CLI script or a minimal FastAPI + `curl` is enough

---

## 3. Input contract (what "after VLM" receives)

Define this as a Pydantic model. This is the only contract with the (currently out-of-scope) VLM step — mock data satisfying this schema is the POC's test fixture.

```python
class VLMObservation(BaseModel):
    plant_id: str
    timestamp: datetime
    health_status: Literal["healthy", "possibly_unhealthy", "unhealthy"]
    confidence: float  # 0-1
    observations: list[Observation]

class Observation(BaseModel):
    type: str            # e.g. "leaf_yellowing"
    severity: Literal["mild", "moderate", "severe"]
    confidence: float
```

Provide fixtures as **one file per scenario** under `fixtures/scenarios/`, not one big sequence — this is what lets you pick and re-run a single behavior on demand instead of always replaying everything. Each file is a short list (1–5 days) of `VLMObservation`s for one plant, isolating one behavior:

| Scenario file | Exercises | Expected trigger |
|---|---|---|
| `no_change.json` | Same health status, same symptoms, day after day | `NO_ACTION` |
| `new_symptom.json` | A symptom `type` appears that wasn't in the previous observation | `CARE_ADVICE_REQUIRED` |
| `health_status_change.json` | `health_status` flips (e.g. `healthy` → `possibly_unhealthy`) | `CARE_ADVICE_REQUIRED` |
| `severity_increase.json` | Same symptom `type`, severity escalates (`mild` → `severe`) | `CARE_ADVICE_REQUIRED` |
| `low_confidence.json` | `confidence` drops below the threshold | `REQUEST_MORE_INFORMATION` |
| `improvement.json` | A known symptom's severity decreases / resolves, nothing new appears | `NO_ACTION` |
| `mixed_multiday.json` | A longer 5-day sequence touching several of the above in one run, for an end-to-end regression check | mixed, per day |

Add scenarios here as you find more edge cases worth checking — the table is a starting set, not the ceiling.

---

## 4. Components to build

### 4.1 Plant Registry (minimal)

Not the full context — just enough to give the Event Engine and Care Advisor something to read/write.

- SQLite tables: `plants`, `observations`, `care_events` (empty/stub is fine), `diagnoses`, `care_plans`
- Functions (not a class hierarchy — keep it simple for a POC):
  - `save_observation(obs: VLMObservation) -> None`
  - `get_previous_observation(plant_id: str) -> VLMObservation | None`
  - `get_recent_observations(plant_id: str, n: int = 5) -> list[VLMObservation]`
  - `get_plant_profile(plant_id: str) -> PlantProfile`
  - `save_care_plan(plant_id: str, plan: CarePlan) -> None`

**Acceptance:** round-trip test — save an observation, read it back, matches input.

### 4.2 Event Engine

Deterministic logic. **No LLM call in this component.**

- Input: new `VLMObservation` + previous `VLMObservation` (from Registry)
- Output: one of `NO_ACTION`, `CARE_ADVICE_REQUIRED`, `REQUEST_MORE_INFORMATION`
- Rules (start with these, make thresholds configurable constants):
  - `confidence < 0.5` → `REQUEST_MORE_INFORMATION`
  - `health_status` changed from previous → `CARE_ADVICE_REQUIRED`
  - a new observation `type` not present in previous → `CARE_ADVICE_REQUIRED`
  - severity of a matching `type` increased → `CARE_ADVICE_REQUIRED`
  - otherwise → `NO_ACTION`
- Function signature: `evaluate(new: VLMObservation, previous: VLMObservation | None) -> TriggerResult`

**Acceptance:** unit tests for each rule branch, one test per scenario file in §3's table — assert the exact trigger for each.

### 4.3 Knowledge RAG

- Ingestion script: takes 2–3 short admin-written `.md` or `.txt` care-guide snippets (write these yourself as fixtures — e.g. "Monstera watering", "Monstera yellowing leaves causes"), chunks them, embeds them, stores in a local vector store.
- **POC choice:** SQLite + `sqlite-vec` or a simple in-memory/FAISS index — do not stand up a separate vector DB service for a POC.
- Embedding model: any small local embedding model (e.g. via `sentence-transformers`, `all-MiniLM-L6-v2` — small enough to run alongside the LLMs on 16GB).
- Retrieval function exposed as a **tool**, not raw context dump:
  `search_plant_knowledge(species: str, topic: str | None, symptoms: list[str]) -> list[KnowledgeChunk]`

**Acceptance:** querying with `symptoms=["leaf_yellowing"]` returns the yellowing-causes chunk above an unrelated chunk (e.g. repotting instructions).

### 4.4 Care Advisor Agent

- Only runs when Event Engine returns `CARE_ADVICE_REQUIRED`.
- Tool-calling agent (not a single giant prompt with everything dumped in). Expose these as callable tools to the LLM:
  - `get_plant_profile()`
  - `get_recent_observations()`
  - `get_care_history()`
  - `search_plant_knowledge(...)`
- LLM: local model via Ollama (per the earlier discussion — a small instruction/reasoning model, e.g. Qwen3 8B Q4). Keep the model swappable via a config value / env var, not hardcoded.
- Output: **must validate against a Pydantic schema**, reject and retry once on validation failure.

```python
class CarePlan(BaseModel):
    plant_id: str
    assessment: str
    confidence: float
    actions: list[CareAction]

class CareAction(BaseModel):
    action: str
    priority: int
```

**Acceptance:** running the `new_symptom.json` scenario, the Advisor's output cites soil-moisture-related actions consistent with the seeded knowledge chunk (don't assert exact wording — assert the action list contains a watering-related action).

### 4.5 Companion Layer

- Input: `CarePlan` (structured, already decided)
- Output: plain friendly text
- **Hard rule to enforce in code, not just prompt instruction:** write a validation check that the Companion's LLM call cannot alter `actions`, `priority`, or `assessment` — pass the structured plan as read-only context and post-hoc verify the output doesn't silently drop or contradict an action (simple substring/keyword check is enough for a POC, not a full guarantee).
- Can be a lightweight LLM call (small model, e.g. Gemma 3 4B) or, for the very first pass of the POC, a template-based formatter with no LLM at all — **build the template version first**, add the LLM version second.

**Acceptance:** feeding the same `CarePlan` in produces text that mentions every `action.action` from the plan.

### 4.6 CLI / Scenario runner

This is what lets you check all behavior on demand rather than only running one fixed sequence.

- `plant-poc list-scenarios` — prints every file found in `fixtures/scenarios/` with a one-line description (pull the description from a `"description"` field you add to each scenario JSON).
- `plant-poc run-batch --scenario <name>` — runs one named scenario through the full pipeline (§6's per-day output).
- `plant-poc run-batch --scenario all` — runs every scenario in `fixtures/scenarios/` back to back, one after another, so you can eyeball the whole behavior matrix in one pass.
- `plant-poc run-batch` with **no** `--scenario` flag — falls back to an interactive picker: list the available scenarios (same list as `list-scenarios`), prompt for a number, run the chosen one. This is the path for "let me just poke at it" without remembering exact file names.
- Each plant's SQLite state should reset per scenario run (fresh DB or a scenario-scoped `plant_id`) so scenarios never bleed into each other's "previous observation" state.

---

## 5. Directory layout — standalone multi-agent repo

This is meant to live in its own repo (not nested in `pet-plant/server`), laid out the way a multi-agent Python project should be from day one so it doesn't need a rewrite once it stops being a POC. The core ideas:

- **`agents/` holds only things that make an LLM call.** Registry and Knowledge are plain data-access modules, not agents — only Care Advisor and Companion are actual agents. Keeping that line sharp matters once there are more than two.
- **Each agent is its own subpackage** with its prompts and tool wrappers colocated, so adding a third agent later never means touching another agent's files.
- **`llm/` is an adapter layer.** Agents call an `LLMClient` interface, not Ollama directly — swapping models, or adding a second provider, stays a one-file change.
- **`orchestration/` owns call order and branching; agents don't know about each other.** The Care Advisor has no idea the Companion exists downstream, and vice versa — the pipeline module is the only place that wires them together.
- **`schemas/` is the shared contract layer** every module imports from — nothing defines its own ad hoc shape of an observation or a care plan.
- **`src/` layout** so it installs as a proper package (`pip install -e .`) instead of relying on script-relative imports.

```
plant-poc/
├── README.md
├── pyproject.toml
├── .env.example
├── src/
│   └── plant_poc/
│       ├── __init__.py
│       ├── config.py              # model names, thresholds, env — no hardcoding elsewhere
│       ├── schemas/                # shared Pydantic contracts, § 3 lives here
│       │   ├── __init__.py
│       │   ├── observation.py
│       │   ├── care_plan.py
│       │   └── knowledge.py
│       ├── registry/               # § 4.1 — plain data access, not an agent
│       │   ├── __init__.py
│       │   ├── store.py            # SQLite connection/schema
│       │   └── repository.py       # save_observation, get_recent_observations, ...
│       ├── event_engine/           # § 4.2 — deterministic, no LLM
│       │   ├── __init__.py
│       │   └── rules.py
│       ├── knowledge/              # § 4.3 — plain data access, not an agent
│       │   ├── __init__.py
│       │   ├── ingest.py
│       │   ├── retriever.py
│       │   └── store.py
│       ├── llm/                    # provider adapter layer
│       │   ├── __init__.py
│       │   ├── base.py             # LLMClient protocol
│       │   └── ollama_client.py
│       ├── agents/
│       │   ├── __init__.py
│       │   ├── base.py             # shared tool-calling loop + schema-validation retry
│       │   ├── care_advisor/       # § 4.4
│       │   │   ├── __init__.py
│       │   │   ├── agent.py
│       │   │   ├── prompts.py
│       │   │   └── tools.py        # get_plant_profile, search_plant_knowledge, ...
│       │   └── companion/          # § 4.5
│       │       ├── __init__.py
│       │       ├── agent.py
│       │       └── prompts.py
│       ├── orchestration/
│       │   ├── __init__.py
│       │   └── pipeline.py         # wires event_engine → care_advisor → companion
│       └── cli.py                  # `plant-poc run-batch` entrypoint
├── fixtures/
│   ├── scenarios/                  # one file per behavior, see § 3's table
│   │   ├── no_change.json
│   │   ├── new_symptom.json
│   │   ├── health_status_change.json
│   │   ├── severity_increase.json
│   │   ├── low_confidence.json
│   │   ├── improvement.json
│   │   └── mixed_multiday.json
│   └── knowledge/
│       ├── monstera-watering.md
│       └── monstera-yellowing.md
└── tests/
    ├── test_event_engine.py
    ├── test_knowledge_retriever.py
    ├── test_care_advisor.py
    └── test_companion.py
```

Once this design is proven out, the pieces map cleanly onto the real bounded contexts in `pet-plant/server` — `registry/` and `knowledge/` become the `registry` and `knowledge` contexts, `agents/care_advisor/` becomes `advice`, `agents/companion/` becomes `companion`, and `orchestration/` folds into `orchestrator`.

---

## 6. End-to-end acceptance criteria for the POC as a whole

Running `plant-poc run-batch --scenario <name>` for each scenario in §3's table should print, per day in that scenario:

1. The day's `VLMObservation` (or a one-line summary of it)
2. The Event Engine's trigger decision
3. If triggered: the retrieved knowledge chunks, the resulting `CarePlan`, and the Companion's final text
4. If not triggered: just `NO_ACTION`, nothing further runs

Cross-check the actual trigger against the "expected trigger" column in §3's scenario table for every scenario — that table **is** the acceptance spec, not just documentation. `--scenario all` should get through every scenario without crashing and should show a run of correct/incorrect triggers you can eyeball at a glance.

---

## 7. Suggested build order (for the implementing agent)

- [ ] 1. `schemas/` — all Pydantic models
- [ ] 2. `fixtures/scenarios/*.json` — write the scenario files from §3's table
- [ ] 3. `registry/` (`store.py` + `repository.py`) + its round-trip test
- [ ] 4. `event_engine/rules.py` + one test per scenario (pure logic, no LLM — do this before touching any model)
- [ ] 5. `fixtures/knowledge/*.md` — write 2-3 short care-guide snippets
- [ ] 6. `knowledge/` (`ingest.py`, `store.py`, `retriever.py`) — test retrieval quality
- [ ] 7. `llm/` (`base.py`, `ollama_client.py`) — the adapter both agents will call through
- [ ] 8. `agents/base.py` — shared tool-calling loop + schema-validation retry, used by both agents below
- [ ] 9. `agents/care_advisor/` — tool wrappers, prompts, agent logic against the local Ollama model
- [ ] 10. `agents/companion/` — template version first, then optional LLM version
- [ ] 11. `orchestration/pipeline.py` — wire event_engine → care_advisor → companion for one scenario at a time
- [ ] 12. `cli.py` — `list-scenarios`, `run-batch --scenario <name>`, `run-batch --scenario all`, and the no-flag interactive picker
- [ ] 13. Run `--scenario all`, check every result against §3's expected-trigger table

---

## 8. Open questions (flag, don't silently decide)

- Which local model tags are actually pullable in Ollama's library at implementation time (verify with `ollama list` / `ollama search` rather than assuming a name from this doc).
- Whether the Companion's "must not change facts" check should be stricter than a keyword match — fine as a stub for the POC, needs real design before this leaves POC stage.
- Whether `knowledge/store.py`'s vector store choice should carry forward into the real `knowledge` bounded context, or if that context ends up owning something different entirely.
