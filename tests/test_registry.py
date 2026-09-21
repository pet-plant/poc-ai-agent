from datetime import datetime, timezone
import pytest
from plant_poc.registry import init_db, PlantRegistry
from plant_poc.schemas import (
    VLMObservation,
    Observation,
    HealthStatus,
    CarePlan,
    CareAction,
)


def test_registry_observation_round_trip():
    conn = init_db(":memory:")
    reg = PlantRegistry(conn)

    obs = VLMObservation(
        plant_id="plant-monstera-1",
        timestamp=datetime.now(timezone.utc),
        health_status=HealthStatus.POSSIBLY_UNHEALTHY,
        confidence=0.88,
        observations=[
            Observation(type="leaf_yellowing", severity="mild", confidence=0.85)
        ],
    )

    reg.save_observation(obs)
    retrieved = reg.get_previous_observation("plant-monstera-1")

    assert retrieved is not None
    assert retrieved.plant_id == obs.plant_id
    assert retrieved.health_status == obs.health_status
    assert retrieved.confidence == pytest.approx(obs.confidence, rel=1e-3)
    assert len(retrieved.observations) == 1
    assert retrieved.observations[0].type == "leaf_yellowing"
    assert retrieved.observations[0].severity == "mild"


def test_registry_plant_profile_and_care_plan():
    conn = init_db(":memory:")
    reg = PlantRegistry(conn)

    profile = reg.ensure_default_profile("plant-test")
    assert profile.plant_id == "plant-test"
    assert profile.species == "Monstera deliciosa"

    plan = CarePlan(
        plant_id="plant-test",
        assessment="Soil is waterlogged.",
        confidence=0.9,
        actions=[
            CareAction(action="Hold watering for 5 days.", priority=1),
        ],
    )
    reg.save_care_plan("plant-test", plan)
    plans = reg.get_recent_care_plans("plant-test", n=1)
    assert len(plans) == 1
    assert plans[0].assessment == "Soil is waterlogged."
    assert plans[0].actions[0].action == "Hold watering for 5 days."


def test_registry_migration_adds_missing_columns():
    import sqlite3
    # Create an old schema database without the new columns
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute(
        """
        CREATE TABLE observations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            plant_id TEXT NOT NULL,
            timestamp TEXT NOT NULL,
            health_status TEXT NOT NULL,
            confidence REAL NOT NULL,
            observations_json TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        """
    )

    from plant_poc.registry.store import _migrate_observations_table
    _migrate_observations_table(conn)

    cursor = conn.cursor()
    cursor.execute("PRAGMA table_info(observations)")
    cols = {row["name"] for row in cursor.fetchall()}
    assert "consensus_json" in cols
    assert "leaf_posture" in cols
    assert "leaf_color_detail" in cols
    assert "image_refs_json" in cols

