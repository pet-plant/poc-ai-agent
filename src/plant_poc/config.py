"""Central configuration for the Post-VLM Pipeline POC."""

import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent.parent
FIXTURES_DIR = BASE_DIR / "fixtures"
SCENARIOS_DIR = FIXTURES_DIR / "scenarios"
KNOWLEDGE_DIR = FIXTURES_DIR / "knowledge"

OLLAMA_HOST = os.getenv("OLLAMA_HOST", "http://localhost:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "qwen2.5:latest")
OLLAMA_EMBED_MODEL = os.getenv("OLLAMA_EMBED_MODEL", "nomic-embed-text:latest")

CONFIDENCE_THRESHOLD = float(os.getenv("CONFIDENCE_THRESHOLD", "0.5"))
DEFAULT_SPECIES = os.getenv("DEFAULT_SPECIES", "Monstera deliciosa")
DEFAULT_SQLITE_PATH = os.getenv("SQLITE_DB_PATH", ":memory:")
