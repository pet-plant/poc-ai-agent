"""SQLite store for knowledge chunks and vector embeddings."""

import json
import sqlite3
from typing import Optional
from plant_poc.schemas import KnowledgeChunk


def init_knowledge_db(db_path: str = ":memory:") -> sqlite3.Connection:
    """Initialize SQLite database for knowledge chunks."""
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    with conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS knowledge_chunks (
                id TEXT PRIMARY KEY,
                species TEXT NOT NULL,
                topic TEXT NOT NULL,
                content TEXT NOT NULL,
                metadata_json TEXT NOT NULL DEFAULT '{}',
                embedding_json TEXT NOT NULL DEFAULT '[]'
            );
            """
        )
    return conn


class KnowledgeStore:
    """Repository for managing knowledge chunks in SQLite."""

    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    def upsert_chunk(self, chunk: KnowledgeChunk) -> None:
        """Insert or update a knowledge chunk."""
        with self.conn:
            self.conn.execute(
                """
                INSERT OR REPLACE INTO knowledge_chunks
                (id, species, topic, content, metadata_json, embedding_json)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    chunk.id,
                    chunk.species,
                    chunk.topic,
                    chunk.content,
                    json.dumps(chunk.metadata),
                    json.dumps(chunk.embedding),
                ),
            )

    def get_all_chunks(self, species: Optional[str] = None) -> list[KnowledgeChunk]:
        """Fetch all chunks, optionally filtered by plant species."""
        cursor = self.conn.cursor()
        if species:
            cursor.execute(
                "SELECT id, species, topic, content, metadata_json, embedding_json FROM knowledge_chunks WHERE species = ?",
                (species,),
            )
        else:
            cursor.execute(
                "SELECT id, species, topic, content, metadata_json, embedding_json FROM knowledge_chunks"
            )
        rows = cursor.fetchall()
        chunks = []
        for r in rows:
            chunks.append(
                KnowledgeChunk(
                    id=r["id"],
                    species=r["species"],
                    topic=r["topic"],
                    content=r["content"],
                    metadata=json.loads(r["metadata_json"]),
                    embedding=json.loads(r["embedding_json"]),
                )
            )
        return chunks
