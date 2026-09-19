"""Knowledge RAG schemas matching PRD §4.3."""

from pydantic import BaseModel, Field


class KnowledgeChunk(BaseModel):
    id: str
    species: str
    topic: str
    content: str
    metadata: dict[str, str] = Field(default_factory=dict)
    embedding: list[float] = Field(default_factory=list)


class SearchResult(BaseModel):
    chunk: KnowledgeChunk
    score: float = Field(ge=0.0, le=1.0)
