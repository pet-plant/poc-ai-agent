"""Repository data access functions for plants, observations, and care plans."""

import json
import sqlite3
from datetime import datetime
from typing import Optional

from plant_poc.schemas import (
    VLMObservation,
    VLMConsensus,
    PlantProfile,
    CarePlan,
    CareAction,
    Observation,
    HealthStatus,
)


class PlantRegistry:
    """Encapsulates plant registry data operations over a SQLite connection."""

    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    def ensure_default_profile(
        self,
        plant_id: str,
        species: str = "Monstera deliciosa",
        nickname: str = "Monty",
        location: str = "Living Room Window",
    ) -> PlantProfile:
        """Seed a default profile for plant_id if not present."""
        profile = self.get_plant_profile(plant_id)
        if profile is not None:
            return profile

        with self.conn:
            self.conn.execute(
                """
                INSERT OR IGNORE INTO plants (plant_id, species, nickname, location, care_preferences_json)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    plant_id,
                    species,
                    nickname,
                    location,
                    json.dumps({"watering": "When top 2 inches dry", "light": "Bright indirect"}),
                ),
            )
        return self.get_plant_profile(plant_id)  # type: ignore

    def get_plant_profile(self, plant_id: str) -> Optional[PlantProfile]:
        """Fetch plant profile by ID."""
        cursor = self.conn.cursor()
        cursor.execute(
            "SELECT plant_id, species, nickname, location, care_preferences_json FROM plants WHERE plant_id = ?",
            (plant_id,),
        )
        row = cursor.fetchone()
        if not row:
            return None

        prefs = json.loads(row["care_preferences_json"]) if row["care_preferences_json"] else {}
        return PlantProfile(
            plant_id=row["plant_id"],
            species=row["species"],
            nickname=row["nickname"],
            location=row["location"],
            care_preferences=prefs,
        )

    def save_observation(self, obs: VLMObservation) -> None:
        """Save a new VLM observation."""
        kwargs: dict = {"plant_id": obs.plant_id}
        if obs.species:
            kwargs["species"] = obs.species
        self.ensure_default_profile(**kwargs)
        obs_dicts = [o.model_dump() for o in obs.observations]
        consensus_json = obs.consensus.model_dump_json() if obs.consensus else None
        image_refs_json = json.dumps(obs.image_refs) if obs.image_refs else None
        with self.conn:
            self.conn.execute(
                """
                INSERT INTO observations
                (plant_id, timestamp, health_status, confidence, observations_json,
                 consensus_json, leaf_posture, leaf_color_detail, image_refs_json)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    obs.plant_id,
                    obs.timestamp.isoformat(),
                    obs.health_status.value,
                    obs.confidence,
                    json.dumps(obs_dicts),
                    consensus_json,
                    obs.leaf_posture,
                    obs.leaf_color_detail,
                    image_refs_json,
                ),
            )

    def get_previous_observation(self, plant_id: str) -> Optional[VLMObservation]:
        """Fetch the most recent past observation for a plant."""
        cursor = self.conn.cursor()
        cursor.execute(
            """
            SELECT plant_id, timestamp, health_status, confidence, observations_json,
                   consensus_json, leaf_posture, leaf_color_detail, image_refs_json
            FROM observations
            WHERE plant_id = ?
            ORDER BY id DESC
            LIMIT 1
            """,
            (plant_id,),
        )
        row = cursor.fetchone()
        if not row:
            return None
        return self._row_to_vlm_observation(row)

    def get_recent_observations(self, plant_id: str, n: int = 5) -> list[VLMObservation]:
        """Fetch recent observations up to n items in chronological order."""
        cursor = self.conn.cursor()
        cursor.execute(
            """
            SELECT plant_id, timestamp, health_status, confidence, observations_json,
                   consensus_json, leaf_posture, leaf_color_detail, image_refs_json
            FROM observations
            WHERE plant_id = ?
            ORDER BY id DESC
            LIMIT ?
            """,
            (plant_id, n),
        )
        rows = cursor.fetchall()
        observations = [self._row_to_vlm_observation(r) for r in rows]
        observations.reverse()  # Return chronological
        return observations

    def save_care_plan(self, plant_id: str, plan: CarePlan) -> None:
        """Save an approved or generated care plan."""
        actions_dicts = [a.model_dump() for a in plan.actions]
        with self.conn:
            self.conn.execute(
                """
                INSERT INTO care_plans (plant_id, assessment, confidence, actions_json)
                VALUES (?, ?, ?, ?)
                """,
                (
                    plant_id,
                    plan.assessment,
                    plan.confidence,
                    json.dumps(actions_dicts),
                ),
            )

    def get_recent_care_plans(self, plant_id: str, n: int = 3) -> list[CarePlan]:
        """Fetch recent care plans for plant."""
        cursor = self.conn.cursor()
        cursor.execute(
            """
            SELECT plant_id, assessment, confidence, actions_json
            FROM care_plans
            WHERE plant_id = ?
            ORDER BY id DESC
            LIMIT ?
            """,
            (plant_id, n),
        )
        rows = cursor.fetchall()
        plans = []
        for r in rows:
            actions_raw = json.loads(r["actions_json"])
            actions = [CareAction.model_validate(a) for a in actions_raw]
            plans.append(
                CarePlan(
                    plant_id=r["plant_id"],
                    assessment=r["assessment"],
                    confidence=r["confidence"],
                    actions=actions,
                )
            )
        return plans

    def _row_to_vlm_observation(self, row: sqlite3.Row) -> VLMObservation:
        obs_raw = json.loads(row["observations_json"])
        observations = [Observation.model_validate(o) for o in obs_raw]

        consensus = None
        if "consensus_json" in row.keys() and row["consensus_json"]:
            consensus = VLMConsensus.model_validate_json(row["consensus_json"])

        leaf_posture = row["leaf_posture"] if "leaf_posture" in row.keys() else None
        leaf_color_detail = row["leaf_color_detail"] if "leaf_color_detail" in row.keys() else None

        image_refs: list[str] = []
        if "image_refs_json" in row.keys() and row["image_refs_json"]:
            image_refs = json.loads(row["image_refs_json"])

        return VLMObservation(
            plant_id=row["plant_id"],
            timestamp=datetime.fromisoformat(row["timestamp"]),
            health_status=HealthStatus(row["health_status"]),
            confidence=row["confidence"],
            observations=observations,
            consensus=consensus,
            leaf_posture=leaf_posture,
            leaf_color_detail=leaf_color_detail,
            image_refs=image_refs,
        )
