"""Vector retrieval for plant knowledge using LangChain VectorStore."""

from __future__ import annotations

from typing import Optional
from langchain_core.vectorstores import VectorStoreRetriever

from plant_poc.knowledge.store import KnowledgeStore
from plant_poc.schemas import KnowledgeChunk, SearchResult


def cosine_similarity(v1: list[float], v2: list[float]) -> float:
    """Compute cosine similarity between two float vectors."""
    import numpy as np
    a = np.array(v1, dtype=np.float32)
    b = np.array(v2, dtype=np.float32)
    norm_a = np.linalg.norm(a)
    norm_b = np.linalg.norm(b)
    if norm_a == 0.0 or norm_b == 0.0:
        return 0.0
    return float(np.dot(a, b) / (norm_a * norm_b))


class KnowledgeRetriever:
    """Retrieves relevant care chunks based on species and symptom queries using LangChain VectorStore."""

    def __init__(self, store: KnowledgeStore):
        self.store = store
        self._retriever: VectorStoreRetriever = store.vector_store.as_retriever(
            search_kwargs={"k": 5}
        )

    def as_retriever(self) -> VectorStoreRetriever:
        """Access underlying LangChain VectorStoreRetriever."""
        return self._retriever

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

        # Retrieve candidates with similarity scores
        try:
            results_with_scores = self.store.vector_store.similarity_search_with_score(
                query_text, k=max(top_k * 2, 5)
            )
        except Exception:
            # Fallback to standard similarity search if scores unsupported
            docs = self.store.vector_store.similarity_search(query_text, k=max(top_k * 2, 5))
            results_with_scores = [(d, 0.5) for d in docs]

        scored_results: list[SearchResult] = []
        for doc, raw_score in results_with_scores:
            score = float(raw_score)
            doc_species = doc.metadata.get("species", "")
            doc_topic = doc.metadata.get("topic", "")
            doc_id = doc.metadata.get("id") or getattr(doc, "id", "") or "chunk"

            # Apply domain boosts
            if symptoms and any(s.lower() in doc_topic.lower() for s in symptoms):
                score += 0.2
            if topic and topic.lower() in doc_topic.lower():
                score += 0.1
            if species and doc_species and species.lower() in doc_species.lower():
                score += 0.05

            score = min(1.0, max(0.0, score))

            chunk = KnowledgeChunk(
                id=doc_id,
                species=doc_species or species,
                topic=doc_topic or doc_id,
                content=doc.page_content,
                metadata={k: v for k, v in doc.metadata.items() if k not in ("species", "topic", "id")},
            )
            scored_results.append(SearchResult(chunk=chunk, score=score))

        scored_results.sort(key=lambda x: x.score, reverse=True)
        return scored_results[:top_k]
