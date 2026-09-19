# Post-VLM Pipeline — Architecture & Scenario Trace

## Architecture Diagram

![Post-VLM Plant Care Pipeline Architecture](/Users/tinnapatplangsri/Documents/UTS%20semester%203/Industry%20project/codebase/poc-ai-agent/docs/architecture-diagram.jpg)

---

# File-by-File Execution Trace — All 7 Scenarios

This document traces **exactly** which file is called, in what order, with what data — for every scenario. Think of it as a manual debugger you can follow line-by-line.

---

## Entry Point (every scenario)

**Step 0: You type the command**

```bash
uv run plant-poc run-batch --scenario new_symptom
```

**→ File: `src/plant_poc/cli.py`**

`main()` is called. `argparse` parses `run-batch --scenario new_symptom`.
It calls `cmd_run_batch(scenario_arg="new_symptom")`.

That function:
1. Reads `fixtures/scenarios/new_symptom.json`
2. Creates a `PlantPipeline` via `PlantPipeline.create_default()`
3. Calls `pipeline.run_scenario(observations)` with the list of `VLMObservation` objects
4. Loops through the returned results and prints each day's output

---

## Setup (every time a pipeline is created)

**→ File: `src/plant_poc/orchestration/pipeline.py` — `PlantPipeline.create_default()`**

This factory creates three isolated, in-memory resources:

| What | File called | What it returns |
|------|-------------|-----------------|
| Empty plant registry DB | `registry/store.py → init_db(":memory:")` | SQLite connection (blank, no rows) |
| Empty knowledge DB | `knowledge/store.py → init_knowledge_db(":memory:")` | SQLite connection (blank) |
| Knowledge ingestion | `knowledge/ingest.py → ingest_knowledge_directory(store)` | Reads `fixtures/knowledge/*.md`, embeds each file, stores 3 chunks |
| Care Advisor Agent | `agents/care_advisor/agent.py → CareAdvisorAgent(llm, registry, retriever)` | Agent with 4 tools wired |
| Companion Agent | `agents/companion/agent.py → CompanionAgent()` | Template formatter |

After `create_default()` finishes, you have a fully wired, isolated pipeline. No data has been processed yet.

---

## Knowledge Ingestion Detail

**→ File: `src/plant_poc/knowledge/ingest.py`**

Scans `fixtures/knowledge/` for `.md` files. For each file:

1. Reads the markdown text
2. Extracts `**Species:**` and `**Topic:**` from the headers
3. Calls `embeddings.py → get_embedding(content)` to get a 768-dim float vector

**→ File: `src/plant_poc/knowledge/embeddings.py`**

Tries to call Ollama `nomic-embed-text` via HTTP. If Ollama is running → real embedding. If not → falls back to `compute_deterministic_embedding()` (hash-based, reproducible offline).

**→ File: `src/plant_poc/knowledge/store.py`**

`upsert_chunk()` inserts the chunk into SQLite `knowledge_chunks` table:

```
id="monstera-yellowing", species="Monstera deliciosa", topic="leaf_yellowing", content="...", embedding=[...768 floats...]
id="monstera-watering",  species="Monstera deliciosa", topic="watering",      content="...", embedding=[...768 floats...]
id="monstera-repotting", species="Monstera deliciosa", topic="repotting",     content="...", embedding=[...768 floats...]
```

Knowledge store is now ready. 3 chunks indexed.

---

## How `run_scenario()` Works

**→ File: `orchestration/pipeline.py → run_scenario(observations)`**

Loops through the list of `VLMObservation` objects (one per day). For each observation calls `process_observation(obs, day_index=N)`:

```python
def process_observation(obs, day_index):
    previous = registry.get_previous_observation(obs.plant_id)    # 1. Read SQLite
    trigger_result = evaluate(new=obs, previous=previous)          # 2. Deterministic rules
    registry.save_observation(obs)                                  # 3. Write to SQLite
    if trigger_result.decision == CARE_ADVICE_REQUIRED:
        care_plan = care_advisor.advise(obs, trigger_result)       # 4. LLM tool loop
        message   = companion.generate_message(care_plan, profile) # 5. Format message
    return PipelineStepResult(...)
```

---

## Scenario 1: `no_change.json` — All Days → `NO_ACTION`

```json
Day 1: health=healthy, confidence=0.95, observations=[]
Day 2: health=healthy, confidence=0.94, observations=[]
```

### Day 1
**→ `registry/repository.py → get_previous_observation("plant-monstera-1")`**
SQLite has zero rows → returns `None`

**→ `event_engine/rules.py → evaluate(new=Day1, previous=None)`**
```
Rule 1: confidence 0.95 >= 0.50 ✓ (pass)
Rule 2: no symptoms to check ✓
Rule 3: previous=None, health=HEALTHY, no symptoms
→ NO_ACTION ("Baseline observation recorded as healthy with no symptoms.")
```

**→ `registry/repository.py → save_observation(Day1)`**
`ensure_default_profile()` inserts "Monty" plant row. Then inserts Day1 observation row.

**No LLM called. No Care Advisor. No Companion.**

### Day 2
**→ `registry/repository.py → get_previous_observation("plant-monstera-1")`**
Finds Day1 row → deserializes to `VLMObservation(health=HEALTHY, observations=[])`

**→ `event_engine/rules.py → evaluate(new=Day2, previous=Day1)`**
```
Rule 1: confidence 0.94 >= 0.50 ✓
Rule 2: no symptoms ✓
Rule 3: previous exists, skip
Rule 4: HEALTHY rank=1 vs HEALTHY rank=1 → no worsening ✓
Rule 5: prev_symptoms={}, new_symptoms={} → no new types ✓
Rule 6: no matching types → no severity change ✓
Rule 7: ranks equal → no improvement
Rule 8: DEFAULT → NO_ACTION ("No new symptoms, no severity increase...")
```

**No LLM called.**

---

## Scenario 2: `new_symptom.json` — Day 2 → `CARE_ADVICE_REQUIRED`

```json
Day 1: health=healthy, confidence=0.92, observations=[]
Day 2: health=possibly_unhealthy, confidence=0.90, observations=[{type:"leaf_yellowing", severity:"mild", confidence:0.88}]
```

### Day 1 → `NO_ACTION` (same as Scenario 1)

### Day 2

**→ `registry/repository.py → get_previous_observation()`**
Returns Day1: `health=HEALTHY, observations=[]`

**→ `event_engine/rules.py → evaluate(Day2, Day1)`**
```
Rule 1: 0.90 >= 0.50 ✓
Rule 2: symptom confidence 0.88 >= 0.50 ✓
Rule 3: previous exists, skip
Rule 4: POSSIBLY_UNHEALTHY rank=2 > HEALTHY rank=1 → worsened!
→ CARE_ADVICE_REQUIRED ("Health status worsened from healthy to possibly_unhealthy")
```

**→ `registry/repository.py → save_observation(Day2)`** — Day2 written to SQLite.

**→ `agents/care_advisor/agent.py → advise(obs, trigger_result)`**

Builds user prompt (from `agents/care_advisor/prompts.py`):
```
Plant ID: plant-monstera-1
Latest Health Status: possibly_unhealthy (Confidence: 0.90)
Observed Symptoms: leaf_yellowing (mild, conf=0.88)
Trigger Reason: Health status worsened from healthy to possibly_unhealthy.
```

**→ `agents/base.py → run_tool_agent(...)`**

**Turn 1 — sends to Ollama:**
```
[system]: You are an expert Plant Care Advisor...
[user]:   Plant ID: plant-monstera-1...
tools available: [get_plant_profile, get_recent_observations, get_care_history, search_plant_knowledge]
```

**Ollama responds:** tool call `search_plant_knowledge(species="Monstera deliciosa", symptoms=["leaf_yellowing"])`

**→ `agents/care_advisor/tools.py → search_plant_knowledge()`**

**→ `knowledge/retriever.py → search_plant_knowledge("Monstera deliciosa", symptoms=["leaf_yellowing"])`**
1. Query text: `"Monstera deliciosa leaf_yellowing"`
2. Get query embedding via `embeddings.py`
3. Fetch all 3 chunks from `knowledge/store.py`
4. Cosine similarity scored:
   - `monstera-yellowing`: base_sim + 0.2 topic boost → score ≈ 0.85
   - `monstera-watering`:  base_sim → score ≈ 0.70
   - `monstera-repotting`: base_sim → score ≈ 0.55
5. Returns top 2: yellowing chunk + watering chunk

**Turn 2 — sends to Ollama with tool result:**
```
[system]: ...
[user]:   Plant ID: plant-monstera-1...
[assistant tool_calls]: search_plant_knowledge(...)
[tool]: [{"topic":"leaf_yellowing","content":"Causes: overwatering...","score":0.85}, ...]
```

**Ollama responds:** final JSON CarePlan
```json
{"plant_id":"plant-monstera-1","assessment":"Likely overwatering...","confidence":0.90,"actions":[...]}
```

**→ `agents/base.py → extract_json_from_text()` → `CarePlan.model_validate()`**
Pydantic validates. If error → sends error back + retries once. On success → returns `CarePlan`.

**→ `registry/repository.py → save_care_plan()`** — Plan persisted to SQLite.

**→ `agents/companion/agent.py → generate_message(care_plan, profile)`**

Template mode (default):
```python
action_lines = "  • Stop watering immediately...\n  • Ensure drainage holes..."
return "Hey there! Here's an update on Monty:\n{assessment}\n\n...{action_lines}\n\nYou've got this!"
```

Result is printed by `cli.py → print_step_result()`.

---

## Scenario 3: `health_status_change.json` — Day 2 → `CARE_ADVICE_REQUIRED`

```json
Day 1: health=healthy, conf=0.95, observations=[]
Day 2: health=possibly_unhealthy, conf=0.89, observations=[]   ← NO symptoms, just status flip
```

### Day 2

**→ `event_engine/rules.py`**
```
Rule 4: POSSIBLY_UNHEALTHY rank=2 > HEALTHY rank=1 → worsened
→ CARE_ADVICE_REQUIRED ("Health status worsened from healthy to possibly_unhealthy")
```

Same Care Advisor + Companion flow. The Ollama prompt will say `Observed Symptoms: No specific symptoms reported.`
The model still consults RAG and produces a precautionary care plan.

---

## Scenario 4: `severity_increase.json` — Day 1 & 2 → `CARE_ADVICE_REQUIRED`

```json
Day 1: health=possibly_unhealthy, observations=[{leaf_yellowing, severity:mild}]
Day 2: health=unhealthy, observations=[{leaf_yellowing, severity:severe}]
```

### Day 1 — first observation, not healthy

**→ `event_engine/rules.py → evaluate(Day1, previous=None)`**
```
Rule 3: previous=None, health=POSSIBLY_UNHEALTHY (not HEALTHY)
→ CARE_ADVICE_REQUIRED ("Initial observation detected symptoms or non-healthy status.")
```

Full Care Advisor + Companion flow runs on Day 1.

### Day 2

**→ `event_engine/rules.py → evaluate(Day2, Day1)`**
```
Rule 4: UNHEALTHY rank=3 > POSSIBLY_UNHEALTHY rank=2 → worsened
→ CARE_ADVICE_REQUIRED ("Health status worsened from possibly_unhealthy to unhealthy")
```

*(Even if Rule 4 hadn't fired, Rule 6 would: `severe rank=3 > mild rank=1` → severity escalation)*

Care Advisor + Companion run again.

---

## Scenario 5: `low_confidence.json` — Day 2 → `REQUEST_MORE_INFORMATION`

```json
Day 1: health=healthy, conf=0.90, observations=[]
Day 2: health=unhealthy, conf=0.35, observations=[{leaf_yellowing, severity:severe, conf:0.30}]
```

### Day 2

**→ `event_engine/rules.py → evaluate(Day2, Day1)`**
```
Rule 1: overall confidence 0.35 < threshold 0.50
→ REQUEST_MORE_INFORMATION (exits immediately, never reaches Rule 2–8)
```

**No LLM called. No Care Advisor. No Companion.**
The pipeline short-circuits at Rule 1.

---

## Scenario 6: `improvement.json` — Day 2 → `NO_ACTION`

```json
Day 1: health=unhealthy, conf=0.92, observations=[{leaf_yellowing, severity:severe}]
Day 2: health=possibly_unhealthy, conf=0.91, observations=[{leaf_yellowing, severity:mild}]
```

### Day 1 → `CARE_ADVICE_REQUIRED` (first observation with symptoms)

### Day 2

**→ `event_engine/rules.py → evaluate(Day2, Day1)`**
```
Rule 1: 0.91 >= 0.50 ✓
Rule 2: symptom conf 0.85 >= 0.50 ✓
Rule 3: previous exists, skip
Rule 4: POSSIBLY_UNHEALTHY rank=2 < UNHEALTHY rank=3 → IMPROVED (not worsened) ✓
Rule 5: prev={"leaf_yellowing":...}, new={"leaf_yellowing":...} → same types, no new ✓
Rule 6: mild rank=1 < severe rank=3 → IMPROVED (not increased) ✓
Rule 7: new_health_rank=2 < prev_health_rank=3 → improved!
→ NO_ACTION ("Health status improved from unhealthy to possibly_unhealthy")
```

**No LLM called on Day 2.**

---

## Scenario 7: `mixed_multiday.json` — 5-day mixed

```json
Day 1: health=healthy, conf=0.95, observations=[]
Day 2: health=possibly_unhealthy, conf=0.90, observations=[{leaf_yellowing:mild}]
Day 3: health=unhealthy, conf=0.92, observations=[{leaf_yellowing:severe}]
Day 4: health=possibly_unhealthy, conf=0.89, observations=[{leaf_yellowing:mild}]
Day 5: health=possibly_unhealthy, conf=0.40, observations=[{leaf_yellowing:mild}]
```

Each day, `previous` is the just-stored observation from SQLite.

| Day | Previous (from SQLite) | Rule fires | Decision | LLM? |
|-----|------------------------|------------|----------|-------|
| 1 | None | Rule 3: first obs, healthy, no symptoms | `NO_ACTION` | No |
| 2 | Day1 (healthy, no obs) | Rule 4: POSSIBLY_UNHEALTHY > HEALTHY | `CARE_ADVICE_REQUIRED` | **Yes** |
| 3 | Day2 (possibly_unhealthy, mild) | Rule 4: UNHEALTHY > POSSIBLY_UNHEALTHY | `CARE_ADVICE_REQUIRED` | **Yes** |
| 4 | Day3 (unhealthy, severe) | Rule 7: POSSIBLY_UNHEALTHY < UNHEALTHY (improved) | `NO_ACTION` | No |
| 5 | Day4 (possibly_unhealthy, mild) | Rule 1: 0.40 < 0.50 | `REQUEST_MORE_INFORMATION` | No |

---

## Key Files Summary (Quick Reference)

| File | Role | Called when |
|------|------|-------------|
| `src/plant_poc/cli.py` | Entry point, loads fixture JSON, prints results | Always first |
| `src/plant_poc/config.py` | Constants: Ollama URL, threshold=0.50, fixture paths | On import everywhere |
| `src/plant_poc/schemas/` | Pydantic data contracts | When loading/validating any data |
| `src/plant_poc/orchestration/pipeline.py` | Wires all components per day | Once per scenario |
| `src/plant_poc/registry/store.py` | Creates SQLite tables | During `create_default()` |
| `src/plant_poc/registry/repository.py` | Read/write observations, profiles, care plans | Every day |
| `src/plant_poc/event_engine/rules.py` | 8-rule triage, zero LLM | Every day |
| `src/plant_poc/knowledge/ingest.py` | Reads `.md` → embeds → stores | Once at setup |
| `src/plant_poc/knowledge/embeddings.py` | Vector via Ollama or hash fallback | During ingest + each RAG query |
| `src/plant_poc/knowledge/store.py` | SQLite CRUD for knowledge chunks | During ingest + retrieval |
| `src/plant_poc/knowledge/retriever.py` | Cosine similarity + topic boost → top-K chunks | When `search_plant_knowledge` tool is called |
| `src/plant_poc/llm/base.py` | `LLMClient` protocol + `MockLLMClient` | When any agent sends a message |
| `src/plant_poc/llm/ollama_client.py` | HTTP POST to Ollama `/api/chat` | When Care Advisor needs real inference |
| `src/plant_poc/agents/base.py` | Tool-calling loop, JSON extraction, retry logic | Every Care Advisor call |
| `src/plant_poc/agents/care_advisor/prompts.py` | System + user prompt templates | Before each Ollama call |
| `src/plant_poc/agents/care_advisor/tools.py` | 4 `AgentTool` objects wired to registry + retriever | During `create_default()` |
| `src/plant_poc/agents/care_advisor/agent.py` | Drives full advisor flow | When trigger=`CARE_ADVICE_REQUIRED` |
| `src/plant_poc/agents/companion/validator.py` | Checks action keywords exist in output text | After Companion generates text (LLM mode) |
| `src/plant_poc/agents/companion/agent.py` | Template formatter (or LLM with fallback) | After every `CarePlan` is produced |

---

## Decision Rule Order (Event Engine — quick cheat sheet)

```
evaluate(new, previous):
  Rule 1: new.confidence < 0.50                    → REQUEST_MORE_INFORMATION  (exits)
  Rule 2: any symptom.confidence < 0.50            → REQUEST_MORE_INFORMATION  (exits)
  Rule 3: previous is None:
          healthy + no symptoms                     → NO_ACTION                 (exits)
          else                                      → CARE_ADVICE_REQUIRED      (exits)
  Rule 4: health_rank(new) > health_rank(previous) → CARE_ADVICE_REQUIRED      (exits)
  Rule 5: new symptom TYPE not in previous         → CARE_ADVICE_REQUIRED      (exits)
  Rule 6: same TYPE but severity_rank increased    → CARE_ADVICE_REQUIRED      (exits)
  Rule 7: health_rank(new) < health_rank(previous) → NO_ACTION                 (exits)
  Rule 8: DEFAULT                                  → NO_ACTION
```

Rules fire in order — first match wins. Rules 1 & 2 always run first and always short-circuit.
