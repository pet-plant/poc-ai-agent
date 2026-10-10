"""SQLite database connection and schema management for Plant Registry."""

import json
import sqlite3
from typing import Optional


def init_db(db_path: str = ":memory:") -> sqlite3.Connection:
    """Initialize SQLite database with required tables."""
    conn = sqlite3.connect(db_path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    with conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS plants (
                plant_id TEXT PRIMARY KEY,
                species TEXT NOT NULL,
                nickname TEXT NOT NULL,
                location TEXT NOT NULL,
                care_preferences_json TEXT NOT NULL DEFAULT '{}',
                level INTEGER NOT NULL DEFAULT 1,
                xp_ratio REAL NOT NULL DEFAULT 0.0
            );

            CREATE TABLE IF NOT EXISTS observations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                plant_id TEXT NOT NULL,
                timestamp TEXT NOT NULL,
                health_status TEXT NOT NULL,
                confidence REAL NOT NULL,
                observations_json TEXT NOT NULL,
                consensus_json TEXT,
                image_refs_json TEXT,
                description TEXT,
                companion_message TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (plant_id) REFERENCES plants(plant_id)
            );

            CREATE TABLE IF NOT EXISTS care_plans (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                care_plan_id TEXT,
                plant_id TEXT NOT NULL,
                status_label TEXT,
                assessment TEXT NOT NULL,
                confidence REAL NOT NULL,
                actions_json TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (plant_id) REFERENCES plants(plant_id)
            );

            CREATE TABLE IF NOT EXISTS care_actions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                care_plan_id TEXT NOT NULL,
                action_id TEXT NOT NULL,
                priority INTEGER NOT NULL DEFAULT 1,
                action TEXT NOT NULL,
                label TEXT NOT NULL,
                action_type TEXT NOT NULL DEFAULT 'other',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS plant_milestones (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                plant_id TEXT NOT NULL,
                timestamp TEXT NOT NULL,
                event_type TEXT NOT NULL,
                description TEXT NOT NULL,
                resolved_at TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (plant_id) REFERENCES plants(plant_id)
            );

            CREATE TABLE IF NOT EXISTS diagnoses (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                plant_id TEXT NOT NULL,
                diagnosis TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS care_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                plant_id TEXT NOT NULL,
                event_type TEXT NOT NULL,
                notes TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );

            -- Performance indexes matching repository queries
            CREATE INDEX IF NOT EXISTS idx_observations_plant_id
                ON observations(plant_id, id DESC);

            CREATE INDEX IF NOT EXISTS idx_observations_plant_ts
                ON observations(plant_id, timestamp DESC);

            CREATE INDEX IF NOT EXISTS idx_care_plans_plant_id
                ON care_plans(plant_id, id DESC);

            CREATE INDEX IF NOT EXISTS idx_care_actions_plan_priority
                ON care_actions(care_plan_id, priority ASC);

            CREATE INDEX IF NOT EXISTS idx_milestones_plant_id
                ON plant_milestones(plant_id, id ASC);

            CREATE INDEX IF NOT EXISTS idx_care_events_plant
                ON care_events(plant_id, event_type, created_at DESC);
            """
        )
        _migrate_observations_table(conn)
        _migrate_care_plans_table(conn)
        _migrate_care_actions_table(conn)
        _migrate_plants_table(conn)
    return conn


def _migrate_plants_table(conn: sqlite3.Connection) -> None:
    """Ensure newly added gamification columns exist in plants table for backward compatibility."""
    cursor = conn.cursor()
    cursor.execute("PRAGMA table_info(plants)")
    existing_cols = {row["name"] for row in cursor.fetchall()}

    new_cols = [
        ("level", "INTEGER NOT NULL DEFAULT 1"),
        ("xp_ratio", "REAL NOT NULL DEFAULT 0.0"),
    ]
    for col_name, col_def in new_cols:
        if col_name not in existing_cols:
            conn.execute(f"ALTER TABLE plants ADD COLUMN {col_name} {col_def}")


def _migrate_observations_table(conn: sqlite3.Connection) -> None:
    """Ensure schema migrations for observations table."""
    cursor = conn.cursor()
    cursor.execute("PRAGMA table_info(observations)")
    existing_cols = {row["name"] for row in cursor.fetchall()}

    new_cols = [
        ("consensus_json", "TEXT"),
        ("image_refs_json", "TEXT"),
        ("description", "TEXT"),
        ("companion_message", "TEXT"),
    ]
    for col_name, col_type in new_cols:
        if col_name not in existing_cols:
            conn.execute(f"ALTER TABLE observations ADD COLUMN {col_name} {col_type}")

    # Drop deprecated visual free-text columns if they exist
    for col in ("leaf_posture", "leaf_color_detail"):
        if col in existing_cols:
            try:
                conn.execute(f"ALTER TABLE observations DROP COLUMN {col}")
            except Exception:
                pass


def _migrate_care_plans_table(conn: sqlite3.Connection) -> None:
    """Ensure newly added nullable columns exist in care_plans table for backward compatibility."""
    cursor = conn.cursor()
    cursor.execute("PRAGMA table_info(care_plans)")
    existing_cols = {row["name"] for row in cursor.fetchall()}

    new_cols = [
        ("care_plan_id", "TEXT"),
        ("status_label", "TEXT"),
    ]
    for col_name, col_type in new_cols:
        if col_name not in existing_cols:
            conn.execute(f"ALTER TABLE care_plans ADD COLUMN {col_name} {col_type}")


def _migrate_care_actions_table(conn: sqlite3.Connection) -> None:
    """Ensure care_actions table exists and backfill from legacy care_plans.actions_json."""
    cursor = conn.cursor()
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS care_actions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            care_plan_id TEXT NOT NULL,
            action_id TEXT NOT NULL,
            priority INTEGER NOT NULL DEFAULT 1,
            action TEXT NOT NULL,
            label TEXT NOT NULL,
            action_type TEXT NOT NULL DEFAULT 'other',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        """
    )
    cursor.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_care_actions_plan_priority
            ON care_actions(care_plan_id, priority ASC);
        """
    )
    # Check if backfill needed
    cursor.execute("SELECT COUNT(*) as count FROM care_actions")
    if cursor.fetchone()["count"] == 0:
        cursor.execute("SELECT care_plan_id, id, actions_json FROM care_plans WHERE actions_json IS NOT NULL")
        for row in cursor.fetchall():
            cpid = row["care_plan_id"] or f"cp_{row['id']}"
            try:
                actions = json.loads(row["actions_json"])
                for a in actions:
                    conn.execute(
                        """
                        INSERT INTO care_actions (care_plan_id, action_id, priority, action, label, action_type)
                        VALUES (?, ?, ?, ?, ?, ?)
                        """,
                        (
                            cpid,
                            a.get("id", f"act_{cpid}"),
                            a.get("priority", 1),
                            a.get("action", ""),
                            a.get("label", a.get("action", "")[:20]),
                            a.get("type", "other"),
                        ),
                    )
            except Exception:
                pass
