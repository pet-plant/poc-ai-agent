													

# Interface Specification: Upstream VLM Output & Downstream Frontend Response

**Project:** `pet-plant` / Post-VLM Agentic Care Pipeline
**Document:** External Interface Contract & Data Dictionary
**Target Audiences:** Upstream VLM Perception Team, Backend Server Team (MVCS), Downstream Frontend / Web Team
**Status:** Approved Interface Specification (v2.1 — Frontend MVCS Alignment)
**Date:** October 2026

---

## 1. System Interface Boundaries

```text
┌───────────────────────────────┐
│     Upstream Perception       │
│      (VLM Vision Model)       │
└───────────────┬───────────────┘
                │
                │  INTERFACE 1: VLM PROBE RESULT (JSON)
                │  Emitted once daily per plant after multi-run consensus
                ▼
┌───────────────────────────────┐
│    Post-VLM Agent Pipeline    │
│    (This Codebase / Engine)   │
└───────────────┬───────────────┘
                │
                │  PERSISTS DIRECTLY TO DB (SQLite / PostgreSQL)
                │  plants, observations, care_plans, care_events
                ▼
┌───────────────────────────────┐
│     Backend Server (MVCS)     │
│  (Controller / Service / Repo)│
└───────────────┬───────────────┘
                │
                │  INTERFACE 2: REST API (GET /companion/devices/me/state)
                │  Queried by web client on page load or refresh
                ▼
┌───────────────────────────────┐
│     Web Frontend Client       │
│        (Web App / UI)         │
└───────────────────────────────┘
```

---

## 2. Interface 1: Upstream VLM Pipeline $\rightarrow$ Agent Pipeline

### 2.1 Purpose & Perception SLA

The VLM Pipeline runs once per day per registered plant. It captures a photo, runs client-side blur checks (Laplacian variance), executes 5 inference passes comparing Day $N$ against Day $N-1$, and calculates an agreement consensus.

> [!IMPORTANT]
> **Upstream Quality Guarantee:**The VLM pipeline only delivers the `PROBE RESULT` after passing quality criteria:
>
> - Photo passes the sharpness/lighting threshold.
> - Multi-run agreement consensus is $\ge 0.70$.
> - If quality fails, the VLM pipeline automatically triggers an internal retake loop (max 3 retries). The post-VLM agent pipeline never receives unverified or blurry scans.

### 2.2 VLM Output Schema (Data Dictionary)

The agent pipeline accepts either the unified probe format or the raw observation dictionary via `plant_poc.vlm_adapter.parse_vlm_probe_result()`.

| Field                 | Type             |     Requirement     | Allowed Values / Format                                      | Description                                             |
| :-------------------- | :--------------- | :-----------------: | :----------------------------------------------------------- | :------------------------------------------------------ |
| `plant_id`          | `string`       | **Mandatory** | e.g.`"plant-monstera-1"`                                   | Unique identifier of the plant in the registry.         |
| `species`           | `string`       | **Optional** | Botanical name (e.g.`"Monstera deliciosa"`)                | Fallback species used if not already bound in database. |
| `timestamp`         | `string`       | **Mandatory** | ISO-8601 UTC (e.g.`"2026-09-22T08:00:00Z"`)                | Time of camera capture.                                 |
| `health_status`     | `string`       | **Mandatory** | `"healthy"` \| `"possibly_unhealthy"` \| `"unhealthy"` | Overall perceived plant health category.                |
| `confidence`        | `float`        | **Mandatory** | `0.0` to `1.0`                                           | Overall confidence score of the diagnosis.              |
| `consensus`         | `object`       | **Mandatory** | See §2.2.1                                                  | Agreement metrics across the 5 vision passes.           |
| `leaf_posture`      | `string`       | **Optional** | e.g.`"mild drooping"`, `"erect"`, `"curling upward"`   | Free-text posture description from visual inspection.   |
| `leaf_color_detail` | `string`       | **Optional** | e.g.`"dark green with yellow tips"`                        | Color analysis notes.                                   |
| `observations`      | `list[object]` | **Mandatory** | List of typed symptoms (can be empty`[]`)                  | Structured symptoms extracted by the vision model.      |
| `image_refs`        | `list[string]` | **Mandatory** | List of MinIO / S3 / local URI strings                       | Image asset references for the day's scan.              |

#### 2.2.1 `consensus` Object Schema

| Field                    | Type        |     Requirement     | Range                                        | Description                                       |
| :----------------------- | :---------- | :-----------------: | :------------------------------------------- | :------------------------------------------------ |
| `agreement`            | `float`   | **Mandatory** | `0.0` to `1.0` (Production $\ge 0.70$) | Fraction of passes that agreed on the diagnosis.  |
| `runs`                 | `integer` | **Mandatory** | Typically`5`                               | Total number of parallel vision passes executed.  |
| `model_stated_average` | `float`   | **Mandatory** | `0.0` to `1.0`                           | Mean model self-confidence score across all runs. |

#### 2.2.2 `observations[]` (Symptom) Object Schema

| Field          | Type       |     Requirement     | Allowed Values                                                                                                                       | Description                                    |
| :------------- | :--------- | :-----------------: | :----------------------------------------------------------------------------------------------------------------------------------- | :--------------------------------------------- |
| `type`       | `string` | **Mandatory** | `"leaf_yellowing"` \| `"brown_edges"` \| `"dry_tips"` \| `"drooping"` \| `"wilting"` \| `"brown_spots"` \| `"curling"` | Standardized symptom identifier key.           |
| `severity`   | `string` | **Mandatory** | `"mild"` \| `"moderate"` \| `"severe"`                                                                                         | Categorical severity rating.                   |
| `confidence` | `float`  | **Mandatory** | `0.0` to `1.0`                                                                                                                   | Confidence specific to this symptom detection. |

---

### 2.3 Concrete VLM Response Examples

#### Example 1A: Symptom Detected (Care Required)

```json
{
  "plant_id": "plant-monstera-1",
  "species": "Monstera deliciosa",
  "timestamp": "2026-09-22T08:30:00Z",
  "health_status": "unhealthy",
  "confidence": 0.91,
  "consensus": {
    "agreement": 1.0,
    "runs": 5,
    "model_stated_average": 0.91
  },
  "leaf_posture": "heavily drooping and bent towards the floor",
  "leaf_color_detail": "severe chlorosis and brown necrotic margins",
  "observations": [
    {
      "type": "leaf_yellowing",
      "severity": "severe",
      "confidence": 0.90
    },
    {
      "type": "brown_edges",
      "severity": "moderate",
      "confidence": 0.88
    }
  ],
  "image_refs": [
    "s3://plant-photos/monstera-1/2026-09-22_raw.jpg",
    "s3://plant-photos/monstera-1/2026-09-22_crop.jpg"
  ]
}
```

#### Example 1B: Healthy Plant (No Action Needed)

```json
{
  "plant_id": "plant-pothos-2",
  "species": "Epipremnum aureum",
  "timestamp": "2026-09-22T09:00:00Z",
  "health_status": "healthy",
  "confidence": 0.97,
  "consensus": {
    "agreement": 1.0,
    "runs": 5,
    "model_stated_average": 0.97
  },
  "leaf_posture": "perky and upright",
  "leaf_color_detail": "vibrant green with yellow variegation",
  "observations": [],
  "image_refs": [
    "s3://plant-photos/pothos-2/2026-09-22_raw.jpg"
  ]
}
```

#### Example 1C: Early Stress / Borderline (`possibly_unhealthy`)

```json
{
  "plant_id": "plant-monstera-1",
  "species": "Monstera deliciosa",
  "timestamp": "2026-09-22T08:30:00Z",
  "health_status": "possibly_unhealthy",
  "confidence": 0.88,
  "consensus": {
    "agreement": 0.90,
    "runs": 5,
    "model_stated_average": 0.88
  },
  "leaf_posture": "mild drooping on lowest petioles",
  "leaf_color_detail": "deep green with slight yellow tips on bottom leaf",
  "observations": [
    {
      "type": "leaf_yellowing",
      "severity": "mild",
      "confidence": 0.85
    }
  ],
  "image_refs": [
    "s3://plant-photos/monstera-1/2026-09-22_raw.jpg"
  ]
}
```

### 2.4 VLM Health Classification Rules for Vision Team

To ensure seamless integration with the Event Engine, the VLM model should assign `health_status` using the following criteria:

| `health_status`                | Visual Stress Level | Typical Symptoms                                                     | Visual Indicators                                                                                                            |
| :------------------------------- | :------------------ | :------------------------------------------------------------------- | :--------------------------------------------------------------------------------------------------------------------------- |
| **`healthy`**            | None                | `observations: []` (empty)                                         | Foliage is turgid, upright, natural uniform color, no lesions or drooping.                                                   |
| **`possibly_unhealthy`** | Mild to Moderate    | Symptoms with`mild` or `moderate` severity                       | Slight drooping on lower stems, initial tip crisping/browning, localized minor yellowing on 1 leaf. Serves as early warning. |
| **`unhealthy`**          | Severe              | Symptoms with`severe` severity (or multiple co-occurring symptoms) | Widespread chlorosis (multiple yellow leaves), severe limpness/wilting, extensive necrosis, rotting stem bases.              |

---

## 3. Interface 2: Backend REST API $\rightarrow$ Web Frontend Client

### 3.1 Purpose & Delivery Modes

The post-VLM pipeline processes the observation and persists all state directly to the database. The backend server (MVCS) queries this state via repository/service and exposes `GET /companion/devices/me/state` wrapped in a standard `BaseResponse` envelope where `data: <object>` holds the state payload (or serialized directly in tests via `PipelineStepResult.to_frontend_dict()`). The web client uses this payload to update the UI across three delivery modes:

1. **Steady / Healthy (`NO_ACTION`)**: Silent timeline update. Green indicator in UI, cheerful companion check-in card, zero alert popup, `care_plan: null`.
2. **Action Needed (`CARE_ADVICE_REQUIRED`)**: High-priority alert banner, red/amber indicator, interactive care card with prioritized action checklist, 2–3 word button labels, and 1st-person plant voice.
3. **Fallback Photo Retake (`REQUEST_MORE_INFORMATION`)**: Friendly photo retake prompt in UI when image quality or consensus falls below threshold (`< 0.50`), with `care_plan: null`.

### 3.2 Base HTTP Response Envelope (`BaseResponse<T>`)

All responses emitted by the backend server for client endpoints follow a unified response envelope. The actual business payload is nested under the `data` field:

```json
{
  "success": true,
  "data": { ... },
  "message": null,
  "error": null
}
```

#### Envelope Field Specification

| Field | Type | Requirement | Description |
| :--- | :--- | :---: | :--- |
| `success` | `boolean` | **Mandatory** | `true` for successful operations (`2xx`), `false` on failures (`4xx`/`5xx`). |
| `data` | `object` \| `null` | **Nullable** | The payload object on success; `null` when an error occurs. |
| `message` | `string` \| `null` | **Optional (Nullable)** | Human-readable explanation or diagnostic message; `null` if none. |
| `error` | `object` \| `null` | **Optional (Nullable)** | Structured error details when `success: false`; `null` on success. |
| `error.code` | `string` | **Mandatory on error** | Machine-readable error code (e.g. `LLM_UNAVAILABLE`, `INTERNAL_SERVER_ERROR`). |
| `error.details` | `object` \| `null` | **Optional (Nullable)** | Additional contextual data or diagnostic details. |

---

### 3.3 `data` Object Schema: Plant Companion State (Data Dictionary)

When `success` is `true`, the `data` object contains the following fields:

| Field                 | Type                   |     Requirement     | Allowed Values                                                                               | Description & Frontend UI Mapping                                              |
| :-------------------- | :--------------------- | :-----------------: | :------------------------------------------------------------------------------------------- | :----------------------------------------------------------------------------- |
| `plant_id`          | `string`             | **Mandatory** | String identifier                                                                            | Target plant ID to route to the correct UI screen.                             |
| `name`              | `string`             | **Mandatory** | Non-empty string (e.g.`"Monty"`)                                                           | Plant nickname displayed at the top of the screen.                             |
| `species`           | `string`             | **Mandatory** | Botanical name (e.g.`"Monstera deliciosa"`)                                                | Botanical species reference.                                                   |
| `dayCount`          | `integer`            | **Mandatory** | $\ge 1$                                                                                    | 1-indexed sequential observation counter for this plant.                       |
| `timestamp`         | `string`             | **Mandatory** | ISO-8601 UTC string                                                                          | Timestamp of the processed scan.                                               |
| `wateredTimestamp`  | `string` \| `null` | **Optional (Nullable)** | ISO-8601 UTC string or`null`                                                               | Timestamp of last watering event recorded in`care_events`; `null` if unwatered.|
| `level`             | `integer`            | **Mandatory** | $\ge 1$ (default `1`)                                                                    | Gamification character level.                                                  |
| `xpRatio`           | `float`              | **Mandatory** | `0.0` to `1.0` (default `0.0`)                                                         | Progress ratio towards next level for UI progress bar.                         |
| `health_status`     | `string`             | **Mandatory** | `"healthy"` \| `"possibly_unhealthy"` \| `"unhealthy"`                                 | Status badge color (Green / Amber / Red).                                      |
| `decision`          | `string`             | **Mandatory** | `"NO_ACTION"` \| `"CARE_ADVICE_REQUIRED"` \| `"REQUEST_MORE_INFORMATION"`              | Controls whether to render care card, silent timeline, or photo retake prompt. |
| `companion_message` | `string`             | **Mandatory** | Non-empty string                                                                             | **1st-person speech bubble** spoken by the plant.                        |
| `care_plan`         | `object` \| `null` | **Optional (Nullable)** | `null` on `NO_ACTION` / `REQUEST_MORE_INFORMATION`, Object on `CARE_ADVICE_REQUIRED` | Detailed botanical action plan (See §3.3.1); `null` when healthy/retake.        |

> [!NOTE]
> **Milestones in Companion Voice:** Raw `milestones_triggered` arrays are omitted from the client response. The Companion Agent automatically weaves relevant episodic milestones (e.g., past overwatering or recoveries) directly into the 1st-person `companion_message` speech bubble.

#### 3.3.1 `care_plan` Object Schema

| Field            | Type             |     Requirement     | Description                                                                        |
| :--------------- | :--------------- | :-----------------: | :--------------------------------------------------------------------------------- |
| `id`           | `string`       | **Mandatory** | Unique identifier for this care plan (e.g.`"cp_a7b8c9d0e1f2"`).                  |
| `status_label` | `string`       | **Mandatory** | Short summary headline for the care card (e.g.`"Overwatering stress"`).          |
| `assessment`   | `string`       | **Mandatory** | Botanical reasoning explaining root cause (e.g. overwatering, fungal).             |
| `actions`      | `list[object]` | **Mandatory** | Ordered list of action items (`[{"id": "...", "priority": 1, ...}]`, see below). |

> [!NOTE]
> **Confidence Handling:** `confidence` is excluded from the public frontend JSON contract to avoid user confusion from uncalibrated LLM scores. It remains preserved internally in the backend database (`care_plans` table) for model telemetry and audit logging.

#### 3.3.2 `care_plan.actions[]` Object Schema

| Field        | Type        |     Requirement     | Allowed Values                                            | Description                                                         |
| :----------- | :---------- | :-----------------: | :-------------------------------------------------------- | :------------------------------------------------------------------ |
| `id`       | `string`  | **Mandatory** | e.g.`"act_8e4b1a2c"`                                    | Unique action identifier for tracking user completions.             |
| `priority` | `integer` | **Mandatory** | $\ge 1$ (1 is highest priority)                         | Relative priority of the action item.                               |
| `action`   | `string`  | **Mandatory** | Full botanical instruction string                         | Detailed explanation shown in action card or modal.                 |
| `label`    | `string`  | **Mandatory** | 2–3 words (max 30 chars)                                 | **Short button text** for Web UI (e.g. `"Pause water"`).            |
| `type`     | `string`  | **Mandatory** | `"water"` \| `"move"` \| `"inspect"` \| `"other"` | Categorical action type for UI iconography and navigation.          |

---

### 3.4 Concrete Response Examples

#### Example 2A: Success Response — `CARE_ADVICE_REQUIRED` (Push Alert & Action Card)

```json
{
  "success": true,
  "data": {
    "plant_id": "plant-monstera-1",
    "name": "Monty",
    "species": "Monstera deliciosa",
    "dayCount": 2,
    "timestamp": "2026-09-22T08:30:00Z",
    "wateredTimestamp": "2026-09-19T14:20:00Z",
    "level": 1,
    "xpRatio": 0.0,
    "health_status": "unhealthy",
    "decision": "CARE_ADVICE_REQUIRED",
    "companion_message": "Hey there! My lower leaves are turning yellow and drooping, just like back when we overwatered in March. Could you pause watering for 5 days so my roots can get some oxygen? 🌿",
    "care_plan": {
      "id": "cp_a7b8c9d0e1f2",
      "status_label": "Overwatering stress",
      "assessment": "Severe chlorosis and drooping indicates soil moisture saturation leading to root hypoxia. Immediate water restriction is essential.",
      "actions": [
        {
          "id": "act_8e4b1a2c",
          "priority": 1,
          "action": "Hold watering for 5 days until top 2 inches of soil are dry to the touch.",
          "label": "Pause water",
          "type": "water"
        },
        {
          "id": "act_9f5c2b3d",
          "priority": 2,
          "action": "Check drainage holes at the bottom of the pot are unblocked.",
          "label": "Drain tray",
          "type": "inspect"
        },
        {
          "id": "act_0a6d3c4e",
          "priority": 3,
          "action": "Move to a bright location with indirect sunlight to assist transpiration.",
          "label": "Move plant",
          "type": "move"
        }
      ]
    }
  },
  "message": null,
  "error": null
}
```

#### Example 2B: Success Response — `NO_ACTION` (Silent Green Timeline Update)

```json
{
  "success": true,
  "data": {
    "plant_id": "plant-pothos-2",
    "name": "Perky",
    "species": "Epipremnum aureum",
    "dayCount": 5,
    "timestamp": "2026-09-22T09:00:00Z",
    "wateredTimestamp": "2026-09-20T10:00:00Z",
    "level": 1,
    "xpRatio": 0.0,
    "health_status": "healthy",
    "decision": "NO_ACTION",
    "companion_message": "I'm feeling great today! My leaves are perky and getting plenty of light. 🌱✨",
    "care_plan": null
  },
  "message": null,
  "error": null
}
```

#### Example 2C: Error Response — LLM Service Unavailable (`LLM_UNAVAILABLE`)

Returned (HTTP 503) when the post-VLM agent pipeline cannot communicate with the configured LLM provider (Ollama, OpenAI, Claude, Gemini) during Care Advisor reasoning:

```json
{
  "success": false,
  "data": null,
  "message": "AI reasoning service (LLM) is currently unavailable. Please verify provider connectivity.",
  "error": {
    "code": "LLM_UNAVAILABLE",
    "details": {
      "provider": "ollama",
      "model": "llama3.2:latest",
      "reason": "Connection refused at http://localhost:11434"
    }
  }
}
```

#### Example 2D: Error Response — General Internal Server Error (`INTERNAL_SERVER_ERROR`)

Returned (HTTP 500) when an unexpected backend or database fault occurs during state retrieval or pipeline execution:

```json
{
  "success": false,
  "data": null,
  "message": "An unexpected internal server error occurred while processing the plant companion state.",
  "error": {
    "code": "INTERNAL_SERVER_ERROR",
    "details": {
      "request_id": "req_8f1b2c3d4e5f",
      "reason": "Database connection timeout while querying plant state"
    }
  }
}
```

---

### 3.4 The `possibly_unhealthy` Status (Amber Early Warning)

`possibly_unhealthy` represents a borderline stress condition (mild wilting, early tip browning, slight drooping) where proactive early intervention can prevent critical damage.

#### Decision Transition Matrix

The Event Engine ranks health statuses: `healthy (1) < possibly_unhealthy (2) < unhealthy (3)`:

| Previous Status        | New Status             | Event Engine Decision        | Milestone Triggered               | Frontend UI Behavior                                                        |
| :--------------------- | :--------------------- | :--------------------------- | :-------------------------------- | :-------------------------------------------------------------------------- |
| `healthy`            | `possibly_unhealthy` | `CARE_ADVICE_REQUIRED`     | `first_symptom` (if first time) | **Amber Badge + Gentle Prevention Card** (low stress checklist)       |
| `possibly_unhealthy` | `possibly_unhealthy` | `NO_ACTION` (if unchanged) | None                              | **Amber Badge + Stable Monitoring Card** (no push notification)       |
| `possibly_unhealthy` | `unhealthy`          | `CARE_ADVICE_REQUIRED`     | `health_crisis`                 | **Red Badge + Urgent Care Card + High Priority Push Alert**           |
| `unhealthy`          | `possibly_unhealthy` | `NO_ACTION`                | None                              | **Amber Badge + Recovery Progress Card** (cheering recovery progress) |

#### Example 2C: Early Intervention Payload (`possibly_unhealthy`)

```json
{
  "plant_id": "plant-monstera-1",
  "name": "Monty",
  "species": "Monstera deliciosa",
  "dayCount": 3,
  "timestamp": "2026-09-22T08:30:00Z",
  "wateredTimestamp": "2026-09-20T08:30:00Z",
  "level": 1,
  "xpRatio": 0.0,
  "health_status": "possibly_unhealthy",
  "decision": "CARE_ADVICE_REQUIRED",
  "companion_message": "Hey friend! Just noticed the tips of my lower leaves are getting a bit crisp. Could you check if the air is too dry or if I'm too close to the AC vent? 🌿",
  "care_plan": {
    "id": "cp_c3d4e5f6a1b2",
    "status_label": "Dry tip warning",
    "assessment": "Mild dry tips indicate localized low humidity or initial moisture stress. Early intervention prevents leaf browning.",
    "actions": [
      {
        "id": "act_1b2c3d4e",
        "priority": 1,
        "action": "Mist foliage lightly or move away from direct air conditioning flow.",
        "label": "Mist leaves",
        "type": "water"
      },
      {
        "id": "act_2c3d4e5f",
        "priority": 2,
        "action": "Verify top 1 inch of soil moisture before scheduled watering.",
        "label": "Check soil",
        "type": "inspect"
      }
    ]
  }
}
```

#### Example 2D: `REQUEST_MORE_INFORMATION` Payload (Photo Retake Card)

```json
{
  "plant_id": "plant-monstera-1",
  "name": "Monty",
  "species": "Monstera deliciosa",
  "dayCount": 2,
  "timestamp": "2026-09-22T08:30:00Z",
  "wateredTimestamp": null,
  "level": 1,
  "xpRatio": 0.0,
  "health_status": "unhealthy",
  "decision": "REQUEST_MORE_INFORMATION",
  "companion_message": "Hmm, I couldn't get a clear look at my leaves in that photo — it might be a bit too blurry or dark. Could you snap another clear photo for me?",
  "care_plan": null
}
```

---

## 4. Verification Tools for Teams

### For VLM Team

* Test your output against `parse_vlm_probe_result(data, plant_id)` in `src/plant_poc/vlm_adapter.py`.
* Run test suite:
  ```bash
  pytest tests/test_vlm_adapter.py -v
  ```

### For Frontend / Web Team

* Consume `PipelineStepResult.to_frontend_dict()` directly as JSON.
* Run mock scenarios from CLI to generate live sample payloads:
  ```bash
  plant-poc run-batch --scenario milestone_lifecycle --mock
  ```
* Review real generated batch output in `docs/scenario-results.json`.
