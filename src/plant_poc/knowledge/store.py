"""Vector store factory and repository for knowledge chunks using LangChain."""

from __future__ import annotations

import hashlib
import os
import re
from typing import Any, Optional
import numpy as np

from langchain_core.documents import Document
from langchain_core.embeddings import Embeddings
from langchain_core.vectorstores import VectorStore

try:
    from langchain_core.vectorstores import InMemoryVectorStore
except ImportError:
    # langchain_core < 0.3 doesn't ship InMemoryVectorStore.
    # Provide a minimal shim matching the API surface we actually use.
    from typing import Iterable, Sequence

    class InMemoryVectorStore(VectorStore):  # type: ignore[no-redef]
        """Lightweight in-memory vector store compatible with langchain_core 0.2.x."""

        def __init__(self, embedding: Embeddings, **kwargs: Any):
            self._embedding = embedding
            self.store: dict[str, dict[str, Any]] = {}

        @property
        def embeddings(self) -> Embeddings:  # type: ignore[override]
            return self._embedding

        def add_texts(
            self,
            texts: Iterable[str],
            metadatas: Optional[list[dict[str, Any]]] = None,
            ids: Optional[list[str]] = None,
            **kwargs: Any,
        ) -> list[str]:
            text_list = list(texts)
            vectors = self._embedding.embed_documents(text_list)
            result_ids: list[str] = []
            for i, text in enumerate(text_list):
                doc_id = (
                    ids[i]
                    if ids and i < len(ids)
                    else hashlib.md5(text.encode(), usedforsecurity=False).hexdigest()
                )
                meta = metadatas[i] if metadatas and i < len(metadatas) else {}
                self.store[doc_id] = {"text": text, "metadata": meta, "vector": vectors[i]}
                result_ids.append(doc_id)
            return result_ids

        def similarity_search_with_score(
            self, query: str, k: int = 4, **kwargs: Any
        ) -> list[tuple[Document, float]]:
            if not self.store:
                return []
            q_vec = np.array(self._embedding.embed_query(query))
            scored: list[tuple[str, float]] = []
            for doc_id, entry in self.store.items():
                d_vec = np.array(entry["vector"])
                norm_q = np.linalg.norm(q_vec)
                norm_d = np.linalg.norm(d_vec)
                if norm_q > 0 and norm_d > 0:
                    score = float(np.dot(q_vec, d_vec) / (norm_q * norm_d))
                else:
                    score = 0.0
                scored.append((doc_id, score))
            scored.sort(key=lambda x: x[1], reverse=True)
            results: list[tuple[Document, float]] = []
            for doc_id, score in scored[:k]:
                entry = self.store[doc_id]
                doc = Document(page_content=entry["text"], metadata=entry.get("metadata", {}))
                results.append((doc, score))
            return results

        def similarity_search(self, query: str, k: int = 4, **kwargs: Any) -> list[Document]:
            return [doc for doc, _ in self.similarity_search_with_score(query, k, **kwargs)]

        @classmethod
        def from_texts(
            cls,
            texts: list[str],
            embedding: Embeddings,
            metadatas: Optional[list[dict[str, Any]]] = None,
            **kwargs: Any,
        ) -> "InMemoryVectorStore":
            store = cls(embedding=embedding)
            store.add_texts(texts, metadatas=metadatas)
            return store

from plant_poc.config import (
    LLM_PROVIDER,
    OLLAMA_EMBED_MODEL,
    OLLAMA_HOST,
    POSTGRES_URL,
    VECTOR_STORE_MODE,
)
from plant_poc.schemas import KnowledgeChunk

EMBED_DIM = 768


def compute_deterministic_embedding(text: str, dim: int = EMBED_DIM) -> list[float]:
    """Compute a deterministic, semantic-preserving bag-of-words embedding.

    Extracts word n-grams and hashes into a fixed-dimension unit vector.
    Guarantees offline test suites and dev environments work reliably without external services.
    """
    words = re.findall(r"\w+", text.lower())
    vec = np.zeros(dim, dtype=np.float32)

    if not words:
        return vec.tolist()

    for word in words:
        for salt in (0, 1, 2):
            h = int(
                hashlib.md5(f"{word}_{salt}".encode(), usedforsecurity=False).hexdigest(),
                16,
            )
            idx = h % dim
            sign = 1.0 if (h // dim) % 2 == 0 else -1.0
            vec[idx] += sign

    norm = np.linalg.norm(vec)
    if norm > 0:
        vec = vec / norm

    return vec.tolist()


class FallbackEmbeddings(Embeddings):
    """LangChain Embeddings wrapper with deterministic fallback for offline resilience."""

    def __init__(self, primary: Optional[Embeddings] = None):
        self.primary = primary

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        if self.primary:
            try:
                return self.primary.embed_documents(texts)
            except Exception:
                pass
        return [compute_deterministic_embedding(t) for t in texts]

    def embed_query(self, text: str) -> list[float]:
        if self.primary:
            try:
                return self.primary.embed_query(text)
            except Exception:
                pass
        return compute_deterministic_embedding(text)


def get_embeddings(provider: Optional[str] = None) -> Embeddings:
    """Return LangChain Embeddings model based on provider."""
    resolved_provider = (provider or LLM_PROVIDER or "ollama").lower()

    primary: Optional[Embeddings] = None
    if resolved_provider == "ollama":
        try:
            from langchain_ollama import OllamaEmbeddings
            primary = OllamaEmbeddings(base_url=OLLAMA_HOST, model=OLLAMA_EMBED_MODEL)
        except Exception:
            pass
    elif resolved_provider == "openai":
        try:
            from langchain_openai import OpenAIEmbeddings
            primary = OpenAIEmbeddings()
        except Exception:
            pass
    elif resolved_provider in ("anthropic", "gemini", "google"):
        try:
            from langchain_openai import OpenAIEmbeddings
            primary = OpenAIEmbeddings()
        except Exception:
            pass

    return FallbackEmbeddings(primary=primary)


def get_vector_store(
    mode: Optional[str] = None,
    embeddings: Optional[Embeddings] = None,
) -> VectorStore:
    """Vector store factory: InMemoryVectorStore (dev/test) or PGVector (production)."""
    resolved_mode = (mode or VECTOR_STORE_MODE or "memory").lower()
    embed_model = embeddings or get_embeddings()

    if resolved_mode == "memory":
        return InMemoryVectorStore(embedding=embed_model)
    elif resolved_mode == "pgvector":
        from langchain_postgres import PGVector
        return PGVector(
            connection=POSTGRES_URL,
            embeddings=embed_model,
            collection_name="plant_knowledge",
        )
    else:
        raise ValueError(f"Unknown vector store mode: {resolved_mode}")


def init_knowledge_db(db_path: str = ":memory:") -> Any:
    """Backward compatibility helper for tests and old callers."""
    return None


class KnowledgeStore:
    """Knowledge store repository wrapping a LangChain VectorStore."""

    def __init__(
        self,
        conn: Any = None,
        mode: Optional[str] = None,
        vector_store: Optional[VectorStore] = None,
        embeddings: Optional[Embeddings] = None,
    ):
        self.mode = mode or VECTOR_STORE_MODE
        self.embeddings = embeddings or get_embeddings()
        if vector_store is not None:
            self._vector_store = vector_store
        else:
            self._vector_store = get_vector_store(self.mode, self.embeddings)

    @property
    def vector_store(self) -> VectorStore:
        return self._vector_store

    def upsert_chunk(self, chunk: KnowledgeChunk) -> None:
        """Insert or update a knowledge chunk in vector store."""
        meta = dict(chunk.metadata or {})
        meta["species"] = chunk.species
        meta["topic"] = chunk.topic
        meta["id"] = chunk.id
        self._vector_store.add_texts(
            texts=[chunk.content],
            metadatas=[meta],
            ids=[chunk.id],
        )

    def get_all_chunks(self, species: Optional[str] = None) -> list[KnowledgeChunk]:
        """Fetch all chunks from the vector store, optionally filtered by species."""
        chunks: list[KnowledgeChunk] = []
        if isinstance(self._vector_store, InMemoryVectorStore):
            for doc_id, doc in self._vector_store.store.items():
                doc_species = doc.get("metadata", {}).get("species", "")
                if species and doc_species.lower() != species.lower():
                    continue
                chunks.append(
                    KnowledgeChunk(
                        id=doc.get("metadata", {}).get("id", doc_id),
                        species=doc_species,
                        topic=doc.get("metadata", {}).get("topic", ""),
                        content=doc.get("text", ""),
                        metadata=doc.get("metadata", {}),
                    )
                )
        return chunks
