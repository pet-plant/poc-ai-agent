# Interface Specification: Upstream VLM Output & Downstream Frontend Response

**Project:** `pet-plant` / Post-VLM Agentic Care Pipeline
**Document:** External Interface Contract & Data Dictionary
**Target Audiences:** Upstream VLM Perception Team, Downstream Mobile / Frontend Team
**Status:** Approved Interface Specification (v2.0 — Latest)
**Date:** September 2026

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
                │  INTERFACE 2: FRONTEND DELIVERY PAYLOAD (JSON)
                │  Emitted for client rendering, push alerts & timeline
                ▼
┌───────────────────────────────┐
│    Mobile App / Frontend      │
│      (Flutter Client)         │
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

| `health_status` | Visual Stress Level | Typical Symptoms | Visual Indicators |
| :--- | :--- | :--- | :--- |
| **`healthy`** | None | `observations: []` (empty) | Foliage is turgid, upright, natural uniform color, no lesions or drooping. |
| **`possibly_unhealthy`** | Mild to Moderate | Symptoms with `mild` or `moderate` severity | Slight drooping on lower stems, initial tip crisping/browning, localized minor yellowing on 1 leaf. Serves as early warning. |
| **`unhealthy`** | Severe | Symptoms with `severe` severity (or multiple co-occurring symptoms) | Widespread chlorosis (multiple yellow leaves), severe limpness/wilting, extensive necrosis, rotting stem bases. |

---

## 3. Interface 2: Agent Pipeline $\rightarrow$ Frontend / Mobile Client

### 3.1 Purpose & Delivery Modes

The post-VLM pipeline processes the observation and produces a serialized response via `PipelineStepResult.to_frontend_dict()`. The mobile client uses this payload to update the UI across two delivery modes:

1. **Steady / Healthy (`NO_ACTION`)**: Silent timeline update. Green indicator in UI, cheerful companion check-in card, zero push notification alert.
2. **Action Needed (`CARE_ADVICE_REQUIRED`)**: High-priority push notification, red/amber indicator, interactive care card with prioritized action checklist, and 1st-person plant voice.

### 3.2 Frontend Payload Schema (Data Dictionary)

| Field                    | Type                   |     Requirement     | Allowed Values                                                | Description & Frontend UI Mapping                                    |
| :----------------------- | :--------------------- | :-----------------: | :------------------------------------------------------------ | :------------------------------------------------------------------- |
| `day`                  | `integer`            | **Mandatory** | $\ge 1$                                                     | 1-indexed sequential observation counter for this plant.             |
| `plant_id`             | `string`             | **Mandatory** | String identifier                                             | Target plant ID to route to the correct UI screen.                   |
| `timestamp`            | `string`             | **Mandatory** | ISO-8601 UTC string                                           | Timestamp of the processed scan.                                     |
| `health_status`        | `string`             | **Mandatory** | `"healthy"` \| `"possibly_unhealthy"` \| `"unhealthy"`  | Status badge color (Green / Yellow / Red).                           |
| `decision`             | `string`             | **Mandatory** | `"NO_ACTION"` \| `"CARE_ADVICE_REQUIRED"`                 | Controls whether to render care card or silent timeline.             |
| `companion_message`    | `string`             | **Mandatory** | Non-empty string                                              | **1st-person speech bubble** spoken by the plant.              |
| `milestones_triggered` | `list[object]`       | **Mandatory** | List (empty`[]` if none)                                    | Milestone badges to celebrate or log in plant history (See §3.2.1). |
| `care_plan`            | `object` \| `null` | **Optional** | `null` on `NO_ACTION`, Object on `CARE_ADVICE_REQUIRED` | Detailed botanical action plan (See §3.2.2).                        |

#### 3.2.1 `milestones_triggered[]` Object Schema

| Field           | Type       |     Requirement     | Allowed Values                                                                                                | Description                                                                |
| :-------------- | :--------- | :-----------------: | :------------------------------------------------------------------------------------------------------------ | :------------------------------------------------------------------------- |
| `event_type`  | `string` | **Mandatory** | `"first_symptom"` \| `"health_crisis"` \| `"severe_episode"` \| `"near_death"` \| `"full_recovery"` | Milestone category key.                                                    |
| `description` | `string` | **Mandatory** | Human-readable string                                                                                         | Timeline description (e.g.`"Severe condition for 3+ consecutive days"`). |
| `timestamp`   | `string` | **Mandatory** | ISO-8601 UTC string                                                                                           | Time milestone was recognized.                                             |

#### 3.2.2 `care_plan` Object Schema

| Field          | Type             |     Requirement     | Description                                                                 |
| :------------- | :--------------- | :-----------------: | :-------------------------------------------------------------------------- |
| `assessment` | `string`       | **Mandatory** | Botanical reasoning explaining root cause (e.g. overwatering, fungal).      |
| `confidence` | `float`        | **Mandatory** | Care advisor confidence in the recommendation (`0.0` - `1.0`).          |
| `actions`    | `list[object]` | **Mandatory** | Ordered list of action items (`[{"priority": 1, "action": "..."}, ...]`). |

---

### 3.3 Concrete Frontend Response Examples

#### Example 2A: `CARE_ADVICE_REQUIRED` Payload (Push Alert & Action Card)

```json
{
  "day": 2,
  "plant_id": "plant-monstera-1",
  "timestamp": "2026-09-22T08:30:00Z",
  "health_status": "unhealthy",
  "decision": "CARE_ADVICE_REQUIRED",
  "companion_message": "Hey there! My lower leaves are turning yellow and drooping, just like back when we overwatered in March. Could you pause watering for 5 days so my roots can get some oxygen? 🌿",
  "milestones_triggered": [
    {
      "event_type": "health_crisis",
      "description": "Health dropped to unhealthy: leaf_yellowing (severe)",
      "timestamp": "2026-09-22T08:30:00Z"
    }
  ],
  "care_plan": {
    "assessment": "Severe chlorosis and drooping indicates soil moisture saturation leading to root hypoxia. Immediate water restriction is essential.",
    "confidence": 0.95,
    "actions": [
      {
        "priority": 1,
        "action": "Hold watering for 5 days until the top 2 inches of soil are dry to the touch."
      },
      {
        "priority": 2,
        "action": "Ensure drainage holes at the bottom of the pot are unblocked."
      },
      {
        "priority": 3,
        "action": "Move to a bright location with indirect sunlight to assist transpiration."
      }
    ]
  }
}
```

#### Example 2B: `NO_ACTION` Payload (Silent Green Timeline Update)

```json
{
  "day": 5,
  "plant_id": "plant-pothos-2",
  "timestamp": "2026-09-22T09:00:00Z",
  "health_status": "healthy",
  "decision": "NO_ACTION",
  "companion_message": "I'm feeling great today! My leaves are perky and getting plenty of light. 🌱✨",
  "milestones_triggered": [],
  "care_plan": null
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
  "day": 3,
  "plant_id": "plant-monstera-1",
  "timestamp": "2026-09-22T08:30:00Z",
  "health_status": "possibly_unhealthy",
  "decision": "CARE_ADVICE_REQUIRED",
  "companion_message": "Hey friend! Just noticed the tips of my lower leaves are getting a bit crisp. Could you check if the air is too dry or if I'm too close to the AC vent? 🌿",
  "milestones_triggered": [
    {
      "event_type": "first_symptom",
      "description": "First symptom observed: dry_tips (mild)",
      "timestamp": "2026-09-22T08:30:00Z"
    }
  ],
  "care_plan": {
    "assessment": "Mild dry tips indicate localized low humidity or initial moisture stress. Early intervention prevents leaf browning.",
    "confidence": 0.88,
    "actions": [
      {
        "priority": 1,
        "action": "Mist foliage lightly or move away from direct air conditioning flow."
      },
      {
        "priority": 2,
        "action": "Verify top 1 inch of soil moisture before scheduled watering."
      }
    ]
  }
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

### For Mobile / Frontend Team

* Consume `PipelineStepResult.to_frontend_dict()` directly as JSON.
* Run mock scenarios from CLI to generate live sample payloads:
  ```bash
  plant-poc run-batch --scenario milestone_lifecycle --mock
  ```
* Review real generated batch output in `docs/scenario-results.json`.
