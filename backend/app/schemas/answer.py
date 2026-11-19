from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field

from app.schemas.common import ISTDatetime

AnswerStatus = Literal["answered", "insufficient_evidence", "refused", "failed"]


class Citation(BaseModel):
    n: int
    chunk_id: UUID
    verified: bool
    source_title: str
    page: int
    source_url: str


class Answer(BaseModel):
    domain: str
    answer_markdown: str
    status: AnswerStatus
    citations: list[Citation] = Field(default_factory=list)
    unsupported_sentences: list[str] = Field(default_factory=list)
    disclaimer: str | None = None
    model: str
    prompt_version: str
    created_at: ISTDatetime
