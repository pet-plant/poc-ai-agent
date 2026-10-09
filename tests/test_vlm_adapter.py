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
        "plant_id": "plant-monstera-001",
        "species": "Monstera deliciosa",
        "timestamp": "2026-09-21T10:00:00+10:00",
        "health_status": "possibly_unhealthy",
        "consensus": {
            "agreement": 1.0,
            "runs": 5,
            "model_stated_average": 0.95,
        },
        "observations": [
            {
                "type": "brown_edges",
                "severity": "moderate",
                "description": "brown edges and noticeable dryness on the lower leaves",
            },
            {
                "type": "drooping",
                "severity": "mild",
                "description": "drooping and bent towards the floor",
            },
        ],
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
    assert obs.effective_confidence == 0.95
    assert len(obs.image_refs) == 2

    # Consensus checks
    assert obs.consensus is not None
    assert obs.consensus.agreement == 1.0
    assert obs.consensus.runs == 5
    assert obs.consensus.model_stated_average == 0.95

    # Symptom parsing
    assert len(obs.observations) == 2
    obs_types = {o.type for o in obs.observations}
    assert "brown_edges" in obs_types
    assert "drooping" in obs_types
    for o in obs.observations:
        assert o.description != ""


def test_parse_healthy_probe_no_damage():
    payload = {
        "timestamp": "2026-09-21T12:00:00",
        "health_status": "healthy",
        "consensus": {
            "agreement": 0.8,
            "runs": 5,
            "model_stated_average": 0.92,
        },
        "observations": [],
    }

    obs = parse_vlm_probe_result(data=payload, plant_id="plant-pothos-1")
    assert obs.health_status == HealthStatus.HEALTHY
    assert len(obs.observations) == 0
    assert obs.consensus is not None
    assert obs.consensus.agreement == 0.8


def test_parse_severe_stress_level():
    payload = {
        "health_status": "unhealthy",
        "consensus": {
            "agreement": 1.0,
            "runs": 5,
            "model_stated_average": 0.98,
        },
        "observations": [
            {
                "type": "leaf_yellowing",
                "severity": "severe",
                "description": "severe chlorosis across all leaves",
            },
            {
                "type": "brown_spots",
                "severity": "severe",
                "description": "necrotic brown spots on foliage",
            },
        ],
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
        "health_status": "healthy",
    }
    with pytest.raises(VLMAdapterError, match="Invalid timestamp format"):
        parse_vlm_probe_result(payload, plant_id="plant-1")
