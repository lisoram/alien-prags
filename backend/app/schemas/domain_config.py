"""Shape of a domain.yaml file, with validation rules.

Every sub-model forbids unknown keys, so a typo in domain.yaml fails loudly
instead of being silently ignored. Cross-checks that need the outside world
(folder name, registered connectors/checks, prompt.md) live in the loader.
"""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationInfo, field_validator, model_validator

from app.schemas.common import DocLabel


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class SourceConfig(_Strict):
    type: str = Field(min_length=1)
    path: str | None = None
    urls: list[str] | None = None

    @model_validator(mode="after")
    def _needs_a_location(self) -> "SourceConfig":
        if not self.path and not self.urls:
            raise ValueError("a source needs either 'path' or 'urls'")
        return self


class ChunkingConfig(_Strict):
    strategy: Literal["by_heading", "by_clause", "semantic", "fixed"]
    max_tokens: int = Field(gt=0)
    overlap_tokens: int = Field(ge=0)
    keep_tables_whole: bool

    @field_validator("overlap_tokens")
    @classmethod
    def _overlap_below_max(cls, v: int, info: ValidationInfo) -> int:
        max_tokens = info.data.get("max_tokens")
        if max_tokens is not None and v >= max_tokens:
            raise ValueError(f"overlap_tokens ({v}) must be less than max_tokens ({max_tokens})")
        return v


class RetrievalConfig(_Strict):
    top_k: int = Field(gt=0)
    candidate_k: int = Field(gt=0)
    hybrid: bool
    keyword_weight: float = Field(ge=0, le=1)
    rerank: bool

    @field_validator("candidate_k")
    @classmethod
    def _candidates_cover_top_k(cls, v: int, info: ValidationInfo) -> int:
        top_k = info.data.get("top_k")
        if top_k is not None and v < top_k:
            raise ValueError(f"candidate_k ({v}) must be >= top_k ({top_k})")
        return v


class AccessConfig(_Strict):
    allowed_roles: list[str] = Field(min_length=1)
    default_doc_label: DocLabel


class GenerationConfig(_Strict):
    disclaimer: str
    require_citations: bool
    refuse_topics: list[str]


class EvalConfig(_Strict):
    min_recall_at_5: float = Field(ge=0, le=1)
    min_faithfulness: float = Field(ge=0, le=1)
    min_citation_precision: float = Field(ge=0, le=1)
    custom_checks: list[str]


class DomainConfig(_Strict):
    name: str = Field(pattern=r"^[a-z][a-z0-9_-]*$")  # lowercase slug
    display_name: str = Field(min_length=1)
    enabled: bool = False
    sources: list[SourceConfig] = Field(min_length=1)
    chunking: ChunkingConfig
    retrieval: RetrievalConfig
    access: AccessConfig
    generation: GenerationConfig
    eval: EvalConfig
