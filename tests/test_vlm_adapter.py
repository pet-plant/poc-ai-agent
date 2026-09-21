"""Unit tests for the VLM Adapter."""

import pytest
from datetime import datetime

from plant_poc.schemas import HealthStatus
from plant_poc.vlm_adapter import (
    VLMAdapterError,
    parse_vlm_probe_result,
)


@pytest.fixture
def sample_probe_result() -> dict:
    return {
        "timestamp": "2026-09-21T10:00:00+10:00",
        "confidence": {
            "agreement": 1.0,
            "runs": 5,
            "model_stated_average": 0.95,
        },
        "severity": 2,
        "verdict": "worse",
        "observation": {
            "leaf_posture": "drooping and bent towards the floor",
            "leaf_color": "dark green with yellowish tips",
            "visible_damage": "brown edges and noticeable dryness on the lower leaves",
            "visible_stress_level": "moderate",
        },
        "image_refs": [
            "file:///images/monstera_day1.jpg",
            "file:///images/monstera_day2.jpg",
        ],
    }


def test_parse_valid_probe_result(sample_probe_result):
    obs = parse_vlm_probe_result(
        data=sample_probe_result,
        plant_id="plant-monstera-001",
        species="Monstera deliciosa",
    )

    assert obs.plant_id == "plant-monstera-001"
    assert obs.species == "Monstera deliciosa"
    assert obs.timestamp == datetime.fromisoformat("2026-09-21T10:00:00+10:00")
    assert obs.health_status == HealthStatus.POSSIBLY_UNHEALTHY
    assert obs.confidence == 0.95
    assert obs.leaf_posture == "drooping and bent towards the floor"
    assert obs.leaf_color_detail == "dark green with yellowish tips"
    assert len(obs.image_refs) == 2

    # Consensus checks
    assert obs.consensus is not None
    assert obs.consensus.agreement == 1.0
    assert obs.consensus.runs == 5
    assert obs.consensus.model_stated_average == 0.95

    # Symptom parsing
    obs_types = {o.type for o in obs.observations}
    assert "brown_edges" in obs_types
    assert "dry_tips" in obs_types
    assert "drooping" in obs_types


def test_parse_healthy_probe_no_damage():
    payload = {
        "timestamp": "2026-09-21T12:00:00",
        "confidence": {
            "agreement": 0.8,
            "runs": 5,
            "model_stated_average": 0.92,
        },
        "severity": 0,
        "verdict": "same",
        "observation": {
            "leaf_posture": "upright and firm",
            "leaf_color": "vibrant deep green",
            "visible_damage": "No visible damage.",
            "visible_stress_level": "none",
        },
    }

    obs = parse_vlm_probe_result(data=payload, plant_id="plant-pothos-1")
    assert obs.health_status == HealthStatus.HEALTHY
    assert len(obs.observations) == 0
    assert obs.consensus.agreement == 0.8


def test_parse_severe_stress_level():
    payload = {
        "observation": {
            "visible_damage": "severe leaf yellowing and necrotic brown spots",
            "visible_stress_level": "severe",
        },
        "confidence": {"agreement": 1.0, "runs": 5},
    }
    obs = parse_vlm_probe_result(data=payload, plant_id="plant-1")
    assert obs.health_status == HealthStatus.UNHEALTHY
    obs_types = {o.type for o in obs.observations}
    assert "leaf_yellowing" in obs_types
    assert "brown_spots" in obs_types


def test_parse_invalid_payload_raises():
    with pytest.raises(VLMAdapterError, match="Expected dict"):
        parse_vlm_probe_result("not a dict", plant_id="plant-1")  # type: ignore


def test_parse_invalid_timestamp_raises():
    payload = {
        "timestamp": "not-a-valid-timestamp",
        "observation": {"visible_stress_level": "none"},
    }
    with pytest.raises(VLMAdapterError, match="Invalid timestamp format"):
        parse_vlm_probe_result(payload, plant_id="plant-1")
