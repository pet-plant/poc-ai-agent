"""SQLite database connection and schema management for Plant Registry."""

import sqlite3
from typing import Optional


def init_db(db_path: str = ":memory:") -> sqlite3.Connection:
    """Initialize SQLite database with required tables."""
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    with conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS plants (
                plant_id TEXT PRIMARY KEY,
                species TEXT NOT NULL,
                nickname TEXT NOT NULL,
                location TEXT NOT NULL,
                care_preferences_json TEXT NOT NULL DEFAULT '{}'
            );

            CREATE TABLE IF NOT EXISTS observations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                plant_id TEXT NOT NULL,
                timestamp TEXT NOT NULL,
                health_status TEXT NOT NULL,
                confidence REAL NOT NULL,
                observations_json TEXT NOT NULL,
                consensus_json TEXT,
                leaf_posture TEXT,
                leaf_color_detail TEXT,
                image_refs_json TEXT,
                companion_message TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (plant_id) REFERENCES plants(plant_id)
            );

            CREATE TABLE IF NOT EXISTS care_plans (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                plant_id TEXT NOT NULL,
                assessment TEXT NOT NULL,
                confidence REAL NOT NULL,
                actions_json TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (plant_id) REFERENCES plants(plant_id)
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
            """
        )
        _migrate_observations_table(conn)
    return conn


def _migrate_observations_table(conn: sqlite3.Connection) -> None:
    """Ensure newly added nullable columns exist in observations table for backward compatibility."""
    cursor = conn.cursor()
    cursor.execute("PRAGMA table_info(observations)")
    existing_cols = {row["name"] for row in cursor.fetchall()}

    new_cols = [
        ("consensus_json", "TEXT"),
        ("leaf_posture", "TEXT"),
        ("leaf_color_detail", "TEXT"),
        ("image_refs_json", "TEXT"),
        ("companion_message", "TEXT"),
    ]
    for col_name, col_type in new_cols:
        if col_name not in existing_cols:
            conn.execute(f"ALTER TABLE observations ADD COLUMN {col_name} {col_type}")
