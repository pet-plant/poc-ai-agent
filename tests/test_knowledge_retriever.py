import pytest
from plant_poc.knowledge import (
    init_knowledge_db,
    KnowledgeStore,
    ingest_knowledge_directory,
    KnowledgeRetriever,
)
from plant_poc.config import KNOWLEDGE_DIR


def test_knowledge_ingestion_and_retrieval_ranking():
    conn = init_knowledge_db(":memory:")
    store = KnowledgeStore(conn)

    # Ingest markdown fixtures
    count = ingest_knowledge_directory(store, KNOWLEDGE_DIR)
    assert count >= 3, f"Expected at least 3 chunks ingested, got {count}"

    retriever = KnowledgeRetriever(store)

    # Query with symptoms=['leaf_yellowing']
    results = retriever.search_plant_knowledge(
        species="Monstera deliciosa",
        topic=None,
        symptoms=["leaf_yellowing"],
        top_k=3,
    )

    assert len(results) > 0
    top_chunk = results[0].chunk

    # Verify that the top result is the yellowing chunk
    assert "yellowing" in top_chunk.id.lower() or "yellowing" in top_chunk.topic.lower()
    assert "overwatering" in top_chunk.content.lower()

    # Verify that repotting chunk is ranked lower than yellowing chunk
    repotting_results = [r for r in results if "repotting" in r.chunk.id.lower()]
    if repotting_results:
        assert results[0].score > repotting_results[0].score
