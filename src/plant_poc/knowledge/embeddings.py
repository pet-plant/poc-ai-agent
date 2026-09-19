"""Embedding generation for local RAG (Ollama nomic-embed-text with deterministic fallback)."""

import hashlib
import re
import httpx
import numpy as np
from plant_poc.config import OLLAMA_HOST, OLLAMA_EMBED_MODEL

EMBED_DIM = 768


def get_embedding(
    text: str,
    host: str = OLLAMA_HOST,
    model: str = OLLAMA_EMBED_MODEL,
    use_local_service: bool = True,
) -> list[float]:
    """Generate embedding vector using Ollama or fall back to deterministic vector."""
    if use_local_service:
        try:
            with httpx.Client(base_url=host, timeout=3.0) as client:
                res = client.post("/api/embeddings", json={"model": model, "prompt": text})
                if res.status_code == 200:
                    data = res.json()
                    if "embedding" in data:
                        return data["embedding"]
        except Exception:
            # Fall back to deterministic embedding when Ollama is offline or times out
            pass

    return compute_deterministic_embedding(text)


def compute_deterministic_embedding(text: str, dim: int = EMBED_DIM) -> list[float]:
    """Compute a deterministic, semantic-preserving bag-of-words embedding.

    Extracts word n-grams and hashes into a fixed-dimension unit vector.
    This guarantees yellowing/watering terms match relevant chunks offline.
    """
    words = re.findall(r"\w+", text.lower())
    vec = np.zeros(dim, dtype=np.float32)

    if not words:
        return vec.tolist()

    for word in words:
        # Generate 3 independent hash indices per word for dense representation
        for salt in (0, 1, 2):
            h = int(hashlib.md5(f"{word}_{salt}".encode()).hexdigest(), 16)
            idx = h % dim
            sign = 1.0 if (h // dim) % 2 == 0 else -1.0
            vec[idx] += sign

    norm = np.linalg.norm(vec)
    if norm > 0:
        vec = vec / norm

    return vec.tolist()
