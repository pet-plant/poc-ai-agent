"""Ingestion of curated care guides from markdown into SQLite KnowledgeStore."""

import re
from pathlib import Path
from typing import Optional
from plant_poc.config import KNOWLEDGE_DIR
from plant_poc.knowledge.store import KnowledgeStore
from plant_poc.knowledge.embeddings import get_embedding
from plant_poc.schemas import KnowledgeChunk


def parse_markdown_guide(file_path: Path) -> KnowledgeChunk:
    """Parse a markdown knowledge guide into a KnowledgeChunk."""
    content = file_path.read_text(encoding="utf-8")
    filename = file_path.stem

    # Extract Species and Topic metadata if present
    species_match = re.search(r"\*\*Species:\*\*\s*(.+)", content)
    topic_match = re.search(r"\*\*Topic:\*\*\s*(.+)", content)

    species = species_match.group(1).strip() if species_match else "Monstera deliciosa"
    topic = topic_match.group(1).strip() if topic_match else filename

    embedding = get_embedding(content)

    return KnowledgeChunk(
        id=filename,
        species=species,
        topic=topic,
        content=content,
        metadata={"source": file_path.name},
        embedding=embedding,
    )


def ingest_knowledge_directory(
    store: KnowledgeStore,
    directory: Path = KNOWLEDGE_DIR,
) -> int:
    """Ingest all markdown files in directory into store."""
    count = 0
    if not directory.exists():
        return 0

    for path in directory.glob("*.md"):
        chunk = parse_markdown_guide(path)
        store.upsert_chunk(chunk)
        count += 1

    return count
