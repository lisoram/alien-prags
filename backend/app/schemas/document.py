from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel

from app.schemas.common import DocLabel, ISTDatetime

DocumentStatus = Literal["fetched", "extracted", "chunked", "indexed", "failed", "needs_ocr"]


class Document(BaseModel):
    id: UUID
    domain: str
    source_type: str
    source_ref: str
    storage_key: str
    title: str
    published_at: ISTDatetime | None = None
    doc_label: DocLabel
    content_hash: str
    status: DocumentStatus
    error_detail: dict[str, Any] | None = None
    created_at: ISTDatetime
    updated_at: ISTDatetime
