"""Vector retrieval with cosine similarity for plant knowledge."""

from typing import Optional
import numpy as np
from plant_poc.knowledge.store import KnowledgeStore
from plant_poc.knowledge.embeddings import get_embedding
from plant_poc.schemas import KnowledgeChunk, SearchResult


def cosine_similarity(v1: list[float], v2: list[float]) -> float:
    """Compute cosine similarity between two float vectors."""
    a = np.array(v1, dtype=np.float32)
    b = np.array(v2, dtype=np.float32)
    norm_a = np.linalg.norm(a)
    norm_b = np.linalg.norm(b)
    if norm_a == 0.0 or norm_b == 0.0:
        return 0.0
    return float(np.dot(a, b) / (norm_a * norm_b))


class KnowledgeRetriever:
    """Retrieves relevant care chunks based on species and symptom queries."""

    def __init__(self, store: KnowledgeStore):
        self.store = store

    def search_plant_knowledge(
        self,
        species: str,
        topic: Optional[str] = None,
        symptoms: Optional[list[str]] = None,
        top_k: int = 3,
    ) -> list[SearchResult]:
        """Search plant knowledge chunks ranked by similarity to species and symptoms."""
        query_parts = [species]
        if topic:
            query_parts.append(topic)
        if symptoms:
            query_parts.extend(symptoms)

        query_text = " ".join(query_parts)
        query_vec = get_embedding(query_text)

        chunks = self.store.get_all_chunks(species=species)
        if not chunks:
            # Fallback to all chunks regardless of species
            chunks = self.store.get_all_chunks()

        scored_results: list[SearchResult] = []
        for chunk in chunks:
            if not chunk.embedding:
                continue
            score = cosine_similarity(query_vec, chunk.embedding)
            # Add boost if topic directly matches symptoms
            if symptoms and any(s.lower() in chunk.topic.lower() for s in symptoms):
                score += 0.2
            if topic and topic.lower() in chunk.topic.lower():
                score += 0.1

            score = min(1.0, max(0.0, score))
            scored_results.append(SearchResult(chunk=chunk, score=score))

        # Rank by score descending
        scored_results.sort(key=lambda x: x.score, reverse=True)
        return scored_results[:top_k]
