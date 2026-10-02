"""Knowledge RAG package (LangChain VectorStore-based)."""

from plant_poc.knowledge.store import (
    init_knowledge_db,
    KnowledgeStore,
    get_embeddings,
    get_vector_store,
    FallbackEmbeddings,
    compute_deterministic_embedding,
)
from plant_poc.knowledge.ingest import ingest_knowledge_directory
from plant_poc.knowledge.retriever import KnowledgeRetriever, cosine_similarity

__all__ = [
    "init_knowledge_db",
    "KnowledgeStore",
    "get_embeddings",
    "get_vector_store",
    "FallbackEmbeddings",
    "compute_deterministic_embedding",
    "ingest_knowledge_directory",
    "KnowledgeRetriever",
    "cosine_similarity",
]
