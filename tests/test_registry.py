from datetime import datetime, timezone
import pytest
from plant_poc.registry import init_db, PlantRegistry
from plant_poc.schemas import (
    VLMObservation,
    Observation,
    VLMConsensus,
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
        consensus=VLMConsensus(agreement=0.9, runs=5, model_stated_average=0.88),
        observations=[
            Observation(
                type="leaf_yellowing",
                severity="mild",
                description="slight yellowing on lower leaves",
            )
        ],
    )

    reg.save_observation(obs)
    retrieved = reg.get_previous_observation("plant-monstera-1")

    assert retrieved is not None
    assert retrieved.plant_id == obs.plant_id
    assert retrieved.health_status == obs.health_status
    assert retrieved.effective_confidence == pytest.approx(obs.effective_confidence, rel=1e-3)
    assert len(retrieved.observations) == 1
    assert retrieved.observations[0].type == "leaf_yellowing"
    assert retrieved.observations[0].severity == "mild"
    assert retrieved.observations[0].description == "slight yellowing on lower leaves"
    assert retrieved.description == "leaf_yellowing: slight yellowing on lower leaves"


def test_registry_plant_profile_and_care_plan():
    conn = init_db(":memory:")
    reg = PlantRegistry(conn)

    profile = reg.ensure_default_profile("plant-test")
    assert profile.plant_id == "plant-test"
    assert profile.species == "Monstera deliciosa"
    assert profile.level == 1
    assert profile.xp_ratio == 0.0

    # Test update_plant_progress
    reg.update_plant_progress("plant-test", level=2, xp_ratio=0.35)
    updated_profile = reg.get_plant_profile("plant-test")
    assert updated_profile is not None
    assert updated_profile.level == 2
    assert updated_profile.xp_ratio == 0.35

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
    # Create an old schema database without the new columns, but with obsolete columns
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
            leaf_posture TEXT,
            leaf_color_detail TEXT,
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
    assert "image_refs_json" in cols
    assert "description" in cols
    assert "companion_message" in cols
    # Ensure dropped columns are no longer in table
    assert "leaf_posture" not in cols
    assert "leaf_color_detail" not in cols

    # Test plants table migration
    conn.execute(
        """
        CREATE TABLE plants (
            plant_id TEXT PRIMARY KEY,
            species TEXT NOT NULL,
            nickname TEXT NOT NULL,
            location TEXT NOT NULL,
            care_preferences_json TEXT NOT NULL DEFAULT '{}'
        );
        """
    )
    from plant_poc.registry.store import _migrate_plants_table
    _migrate_plants_table(conn)
    cursor.execute("PRAGMA table_info(plants)")
    plant_cols = {row["name"] for row in cursor.fetchall()}
    assert "level" in plant_cols
    assert "xp_ratio" in plant_cols


def test_registry_milestones_crud():
    conn = init_db(":memory:")
    reg = PlantRegistry(conn)

    from plant_poc.schemas import PlantMilestone, MilestoneType

    milestone = PlantMilestone(
        plant_id="plant-monstera-1",
        timestamp=datetime(2026, 9, 2),
        event_type=MilestoneType.FIRST_SYMPTOM,
        description="First symptom detected",
    )
    m_id = reg.record_milestone(milestone)
    assert m_id > 0

    all_m = reg.get_milestones("plant-monstera-1")
    assert len(all_m) == 1
    assert all_m[0].event_type == MilestoneType.FIRST_SYMPTOM
    assert all_m[0].description == "First symptom detected"


def test_registry_companion_message_update_and_retrieval():
    conn = init_db(":memory:")
    reg = PlantRegistry(conn)

    ts = datetime(2026, 9, 2, 10, 0, 0)
    obs = VLMObservation(
        plant_id="plant-monstera-1",
        timestamp=ts,
        health_status=HealthStatus.HEALTHY,
    )
    reg.save_observation(obs)

    reg.update_observation_companion_message(
        plant_id="plant-monstera-1",
        timestamp=ts,
        companion_message="I'm feeling wonderful today!",
    )

    retrieved = reg.get_previous_observation("plant-monstera-1")
    assert retrieved is not None
    assert retrieved.companion_message == "I'm feeling wonderful today!"

    recent = reg.get_recent_observations("plant-monstera-1", n=7)
    assert len(recent) == 1
    assert recent[0].companion_message == "I'm feeling wonderful today!"
