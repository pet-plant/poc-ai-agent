# Final Architecture & Data Flow: Post-VLM Plant Care Pipeline

**Project:** `pet-plant` / Post-VLM Agentic Care Pipeline
**Document:** End-to-End Data Flow & Service Architecture Specification
**Status:** Approved Architecture (v2.0 — Latest)
**Date:** September 2026

---

## 1. Complete End-to-End Visual Data Flow

```mermaid
flowchart TD
    subgraph PERCEPTION["1. Upstream Perception & Vision Layer (VLM Owned)"]
        direction TB
        S1["Step 1: Daily Batch Image Capture<br/>(Camera Device Cron)"] --> S2{"Step 2: Fast Blur & Light Gate<br/>(Laplacian Variance)"}
        S2 -- "Blurry / Low Light" --> RETAKE["Autonomous Retake Loop<br/>(Max 3 Retries)"]
        RETAKE --> S1
        S2 -- "Quality Pass" --> S3["Step 3: Object Storage<br/>(MinIO / S3 Raw + Cropped)"]
        S3 --> S4["Step 4: Upstream Multi-Run VLM<br/>(5 Parallel Passes Day N vs N-1)"]
        S4 -- "Consensus Agreement &ge; 0.7" --> PROBE["Validated PROBE RESULT<br/>(Quality & Confidence Guaranteed)"]
        S4 -- "Low Consensus" --> RETAKE
    end

    PROBE --> S5

    subgraph POST_VLM["2. Post-VLM Agentic Pipeline (This Repository)"]
        direction TB
        S5["Step 5: Event Engine Gatekeeper"] --> S6["Step 6: Baseline Retrieval"]
        S6 <--> DB[("Plant Registry Database<br/>(PostgreSQL / SQLite)<br/>- plants<br/>- observations<br/>- care_plans<br/>- plant_milestones")]

        S5 --> BRANCH{"Event Engine Evaluation"}

        BRANCH -- "NO_ACTION<br/>(Steady / Healthy)" --> B_WRITE["Write Clean Observation"]
        B_WRITE --> B_TEMPLATE["Step 8b: Static Cheerful Template<br/>(0 LLM Tokens, sub-millisecond)"]

        BRANCH -- "CARE_ADVICE_REQUIRED<br/>(Health Drop / New Symptom)" --> C_WRITE["Write Observation + Care Plan"]
        C_WRITE --> M_CHECK{"Milestone Trigger?<br/>(Crisis / 3d Severe / Recovery)"}
        M_CHECK -- "Yes" --> M_WRITE["Record in plant_milestones"]
        M_CHECK -- "No" --> C_ADVISOR
        M_WRITE --> C_ADVISOR

        C_ADVISOR["Step 8c: Care Advisor Agent<br/>(Analytical Reasoning LLM)<br/>- 5-day observation trend<br/>- Species profile<br/>- Knowledge Base RAG"]
        C_ADVISOR --> PLAN["Structured CarePlan<br/>(Assessment & Action Items)"]

        PLAN --> C_COMPANION["Step 9c: Companion Agent<br/>(1st-Person Plant Persona)"]

        DB -- "Tier 1: Last 7 Days Rolling Window" --> C_COMPANION
        DB -- "Tier 2: Episodic Milestones<br/>(Injected only if symptom-relevant)" --> C_COMPANION

        C_COMPANION --> C_SAVE["Save companion_message<br/>to observations table"]
    end

    B_TEMPLATE --> DELIV_B["Step 9b: Silent Green Timeline Update"]
    C_SAVE --> DELIV_C["Step 11c: High-Priority Push Alert<br/>& Interactive Care Card"]

    subgraph DELIVERY["3. Mobile Frontend Delivery Layer (Flutter)"]
        DELIV_B
        DELIV_C
    end

    classDef perception fill:#1e293b,stroke:#38bdf8,stroke-width:2px,color:#f8fafc;
    classDef postVlm fill:#0f172a,stroke:#22c55e,stroke-width:2px,color:#f8fafc;
    classDef delivery fill:#1e1e2e,stroke:#a855f7,stroke-width:2px,color:#f8fafc;
    classDef db fill:#0369a1,stroke:#38bdf8,stroke-width:2px,color:#f8fafc;

    class S1,S2,RETAKE,S3,S4,PROBE perception;
    class S5,S6,BRANCH,B_WRITE,B_TEMPLATE,C_WRITE,M_CHECK,M_WRITE,C_ADVISOR,PLAN,C_COMPANION,C_SAVE postVlm;
    class DB db;
    class DELIV_B,DELIV_C delivery;
```

### Text Flow Diagram

```text
══════════════════════════════ 1. CLIENT & PERCEPTION LAYER (VLM Owned) ══════════════════

     [ Step 1: Batch Image Capture — Daily, Triggered by VLM Pipeline ] ◄────────────┐
                                      │                                               │
                                      ▼                                               │
               [ Step 2: Client-Side Fast Blur/Light Gate ]                           │
               (If quality fails: VLM pipeline automatically retakes — internal loop) │
               (Our post-VLM pipeline NEVER receives a low-quality scan)              │
                                      │ (Quality OK: Upload Image)                    │
                                      ▼                                               │
                  [ Step 3: Object Storage (MinIO / S3) ]                             │
                  - Stores raw photo (original resolution)                            │
                  - Stores thumbnail and cropped plant segment                        │
                                      │                                               │
                                      ▼                                               │
             [ Step 4: Upstream VLM Multi-Run Inference Engine ]                      │
             - Runs 5 parallel vision passes (Day N vs Day N-1)                      │
             - Computes consensus agreement score & confidence                        │
             - If retake needed: loops back to Step 1 automatically ─────────────────┘
             - Emits PROBE RESULT (only on success — quality guaranteed):
               • health_status: "healthy" | "possibly_unhealthy" | "unhealthy"
               • symptoms: [{"type": "...", "severity": "...", "confidence": ...}]
               • leaf_posture & leaf_color_detail
               • agreement score (0.0 - 1.0) — guaranteed > threshold here
                                      │
                                      ▼
══════════════════════════════ 2. POST-VLM PIPELINE ══════════════════════════════════

                                      │
                                      ▼
                   [ Step 5: Event Engine Gatekeeper ]
                                      │
                                      │ [ Step 6: READ Baseline Observation ]
                                      ▼
              [ Plant Registry DB (PostgreSQL / Multi-tenant) ]
              ┌──────────────────────────────────────────────────────────────┐
              │ plants            (profile — written once at setup)          │
              │  plant_id, species, nickname, location, pot_type             │
              ├──────────────────────────────────────────────────────────────┤
              │ observations      (daily log — stored FOREVER, never deleted)│
              │  plant_id, timestamp, health_status, symptoms,               │
              │  confidence, leaf_posture, leaf_color_detail,                │
              │  image_refs, companion_message                               │
              ├──────────────────────────────────────────────────────────────┤
              │ care_plans        (written on CARE_ADVICE_REQUIRED only)     │
              │  plant_id, timestamp, assessment, actions                    │
              ├──────────────────────────────────────────────────────────────┤
              │ plant_milestones  (major life events — stored FOREVER) ★     │
              │  plant_id, timestamp, event_type, description, resolved_at   │
              │  event_types: first_symptom | health_crisis | severe_episode │
              │               near_death | full_recovery                     │
              └──────────────────────────────────────────────────────────────┘
                                      │
                   ┌──────────────────┴──────────────────┐
                   │                                     │
                   ▼                                     ▼
             [ NO_ACTION ]                     [ CARE_ADVICE_REQUIRED ]
         (healthy / unchanged)               (health drop / new symptom)
                   │                                     │
                   │ [ Step 7b: WRITE ]                  │ [ Step 7c: WRITE ]
                   │   clean obs to                      │   observations table
                   │   observations table                │   + care_plans table
                   │                                     │   + plant_milestones
                   │                                     │   (if milestone triggered)
                   │                                     │
                   │                                     ▼
                   │                      [ Step 8c: Care Advisor Agent ]
                   │                      (Analytical Reasoning LLM)
                   │                      ├── Reads observations (5-day trend)
                   │                      ├── Reads plants (species / profile)
                   │                      └── Queries Knowledge RAG (VDB)
                   │                                     │
                   │                                     ▼
                   │                           [ Validated CarePlan ]
                   │                           (assessment, actions)
                   │                                     │
                   │                                     ▼
                   │                        [ Step 9c: Companion Agent ]
                   │                        (Persona LLM / Voice Engine)
                   │                        ├── Preserves CarePlan actions
                   │                        ├── Speaks in 1st-person voice
                   │                        ├── TWO-TIER MEMORY RETRIEVAL:
                   │                        │   • Short-term: observations (last 7 days)
                   │                        │   • Long-term: plant_milestones (all time,
                   │                        │     referenced only if relevant to symptom)
                   │                        └── Output saved to
                   │                            observations.companion_message
                   │                                     │
                   ▼                                     ▼
       [ Step 8b: STATIC TEMPLATE ]               [ Step 10c: LLM VOICE ]
       (0 tokens, < 1ms)                          (Tokens used only here)
       "I'm feeling great!                        "My leaves are drooping like
        Leaves are happy today."                   back in March, could you check
                                                   my soil moisture? 🌿"
                   │                                     │
                   └──────────────────┬──────────────────┘
                                      │
                                      ▼
══════════════════════════════ 3. USER DELIVERY LAYER ════════════════════════════════

                                      │
              ┌───────────────────────┴───────────────────────┐
              │                                               │
              ▼                                               ▼
 [ Step 9b: App Status Update ]             [ Step 11c: Push Alert
   (Steady / Healthy)                         & Care Card Delivery ]
 - Green status in timeline               - High-priority push notification
 - Peaceful check-in message              - Interactive action care cards
 - Zero notification spam                 - Plant speaks in 1st-person voice
                                            incorporating memory context
```

---

## 2. Step-by-Step Execution Sequence

### Phase 1: Client & Perception (VLM Owned)

- **Step 1:** The VLM pipeline triggers a daily batch image capture (not a manual user tap).
- **Step 2:** Fast client-side Laplacian blur/lighting check. If quality fails, the VLM pipeline retakes automatically — no user prompt is shown. Our post-VLM pipeline only ever receives a passing scan.
- **Step 3:** Valid images are uploaded to Object Storage (MinIO / S3).
- **Step 4:** The Upstream VLM runs 5 parallel inference passes (Day N vs Day N-1), computes consensus agreement, and — only after a successful scan — emits the structured `PROBE RESULT`. If retake is needed, it loops back to Step 1 internally.

### Phase 2: Post-VLM Pipeline

- **Step 5:** The Event Engine receives the `PROBE RESULT` as the gatekeeper.
- **Step 6:** Event Engine queries the **Plant Registry DB** for the plant's baseline from the `observations` table, and the plant's static profile from the `plants` table.
- **Deterministic Pipeline Routing:**
  Image quality and consensus are fully guaranteed upstream by the perception gate. The Event Engine evaluates the differential between the new observation and baseline to route directly to one of two operational pathways:
  - **Path B (`NO_ACTION`) — Steady / Healthy:**
    - **Step 7b:** Saves the clean observation to the `observations` table.
    - **Step 8b:** Instantly pulls a static cheerful template (0 tokens, sub-millisecond).
    - **Step 9b:** Updates plant status to green in the app timeline without notifications.
  - **Path C (`CARE_ADVICE_REQUIRED`) — Health Drop / New Symptom:**
    - **Step 7c:** Saves the clean observation to `observations`. Saves prescribed care to `care_plans`. If a milestone threshold is crossed (e.g. first symptom, 3+ consecutive `UNHEALTHY` days), writes an entry to `plant_milestones`.
    - **Step 8c:** Care Advisor Agent reasons over the 5-day `observations` trend, plant species profile, and Knowledge RAG to produce a structured `CarePlan`.
    - **Step 9c:** Companion Agent translates the `CarePlan` into first-person plant voice using **Two-Tier Memory**:
      - **Short-term Memory:** Reads the last 7 days of `observations` to maintain day-to-day conversational continuity.
      - **Long-term Episodic Memory:** Reads `plant_milestones` (all-time), but **only references past crises if semantically relevant** to the current symptom (e.g. recurring yellowing). If unrelated, it stays silent about past milestones.
      - The generated message is saved to `observations.companion_message`.
    - **Step 10c:** Emits the final dialogue message.
    - **Step 11c:** High-priority push notification and interactive care card delivered to the mobile app frontend.

---

## 3. Plant Registry DB: Four Tables

| Table | Purpose | Retention |
|---|---|---|
| `plants` | Static plant profile: species, nickname, location, pot type | Forever (updated only on profile change) |
| `observations` | Daily health snapshots: symptoms, VLM data, `companion_message` | Forever — all records kept |
| `care_plans` | Prescribed care actions per `CARE_ADVICE_REQUIRED` event | Forever — all records kept |
| `plant_milestones` | Major life events: `first_symptom`, `health_crisis`, `severe_episode`, `near_death`, `full_recovery` | Forever — never deleted |

---

## 4. Two-Tier Memory & Milestone Architecture

The Companion Agent uses a two-tier memory architecture to avoid token bloat and hallucinated memory recitations while preserving emotional continuity.

```mermaid
flowchart LR
    subgraph INPUT["Daily Trigger"]
        OBS["New Observation<br/>(CARE_ADVICE_REQUIRED)"]
        CARE["CarePlan<br/>(Care Advisor)"]
    end

    subgraph MEMORY["Two-Tier Memory Store"]
        direction TB
        T1["Tier 1: Short-Term Rolling Window<br/>- Last 7 calendar days of observations<br/>- Symptoms, care actions, companion responses<br/>- Provides immediate conversational continuity"]
        T2["Tier 2: Long-Term Episodic Milestones<br/>- Major life events across all-time history<br/>- Filtered: ONLY surfaced if semantically<br/>  relevant to current active symptoms"]
    end

    subgraph AGENT["Companion Agent"]
        PROMPT["Persona Prompt<br/>- 1st-person voice<br/>- Preserves botanical actions<br/>- Strict anti-hallucination rules"]
    end

    subgraph OUTPUT["Frontend Result"]
        MSG["companion_message<br/>saved to observations DB"]
    end

    INPUT --> AGENT
    T1 --> AGENT
    T2 -. "If symptom-relevant" .-> AGENT
    AGENT --> OUTPUT
```

### Deterministic Milestone Triggers
1. **`first_symptom`**: The first time any health issue appears on a previously healthy plant.
2. **`health_crisis`**: Sudden drop to `UNHEALTHY` (e.g., severe fungal spread or root rot symptoms).
3. **`severe_episode`**: A severe condition persisting for **3 or more consecutive days**.
4. **`near_death`**: Persistent critical distress for **7 or more consecutive days**.
5. **`full_recovery`**: Complete transition back to `HEALTHY` with zero symptoms after an episode.

---

## 5. Mobile Delivery Contract

> [!NOTE]
> For the full data dictionary, field-by-field constraints, and VLM/Frontend interface contracts, see **[docs/interface-specification.md](file:///Users/tinnapatplangsri/Documents/UTS%20semester%203/Industry%20project/codebase/poc-ai-agent/docs/interface-specification.md)**.

The output delivered to the Flutter mobile app follows a unified payload:

```json
{
  "plant_id": "monstera_01",
  "timestamp": "2026-09-22T08:00:00Z",
  "trigger_result": "CARE_ADVICE_REQUIRED",
  "milestones_triggered": [
    {
      "event_type": "first_symptom",
      "description": "First symptom observed: leaf_yellowing (moderate)"
    }
  ],
  "care_plan": {
    "diagnosis_ref": "Overwatering induced chlorosis",
    "assessment": "Leaf yellowing indicates root moisture saturation.",
    "immediate_actions": [
      {
        "action": "Hold watering for 5 days",
        "priority": "HIGH",
        "instructions": "Allow top 2 inches of soil to dry out completely."
      }
    ]
  },
  "companion_message": "Hey there! My lower leaf is starting to yellow, just like back when we overwatered. Could you pause watering for a few days so my roots can breathe? 🌿"
}
```

---

## 6. Architecture Evolution & Superseded Concepts (Changelog)

This document represents **v2.0 (Latest)**. The table below records all previous designs that were rendered obsolete:

| Superseded / Obsolete Design | Latest v2.0 Production Design | Architectural Rationale |
| :--- | :--- | :--- |
| **Branch A User Clarification Loop**<br>(Old Step 9a: asking user for more info on low confidence) | **Upstream Hardware/VLM Retake Loop**<br>(Steps 2 & 4: automatic retakes on blur or low consensus) | Moved image quality validation to the edge device. The post-VLM pipeline only receives high-confidence scans; zero user notification friction. |
| **5-Table Schema with Separate `diagnoses`**<br>(Initial draft in `plant-poc-prd.md`) | **4-Table Unified Schema**<br>(`plants`, `observations`, `care_plans`, `plant_milestones`) | `diagnoses` merged into `care_plans`, `companion_message` stored directly on `observations`, and `plant_milestones` dedicated to long-term memory. |
| **Interactive Bi-Directional Chatbot**<br>(Assumed real-time chat sessions) | **Single-Shot 1st-Person Push/Card**<br>(Step 9b / 11c) | Daily autonomous care cards eliminate chat session overhead and better match daily plant growth rates. |
| **Unbounded Raw History for Companion**<br>(Passing entire observation log to LLM) | **Two-Tier Memory System**<br>(7-day rolling window + relevant episodic milestones) | Prevents context window explosion and prevents unprompted recitation of ancient, resolved crises. |
| **LangChain / LangGraph Dependencies** | **Pure Python + Pydantic + SQLite/Postgres** | Minimizes dependency bloat, guarantees sub-second execution, and provides complete deterministic control. |
