from uuid import UUID

from pydantic import BaseModel

from app.schemas.common import DocLabel, ISTDatetime


class Chunk(BaseModel):
    chunk_id: UUID
    document_id: UUID
    domain: str
    text: str
    section_title: str
    page: int
    doc_label: DocLabel
    source_title: str
    source_url: str
    published_at: ISTDatetime | None = None
    token_count: int


class RetrievedChunk(Chunk):
    """A Chunk plus its retrieval scores. Extends Chunk so that citations
    can use the full metadata without a second lookup."""

    score: float
    rerank_score: float | None = None
