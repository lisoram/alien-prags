from datetime import datetime, timezone
from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.schemas import (
    Answer, Chunk, Citation, Document, DomainConfig, RetrievedChunk,
)

NOW = datetime(2026, 11, 18, 9, 0, tzinfo=timezone.utc)  # = 14:30 IST


def make_chunk(**over):
    base = dict(
        chunk_id=uuid4(), document_id=uuid4(), domain="demo", text="t",
        section_title="s", page=1, doc_label="public", source_title="T",
        source_url="http://x", published_at=NOW, token_count=3,
    )
    return {**base, **over}


def make_domain_config():
    return DomainConfig(
        name="demo", display_name="Demo",
        sources=[{"type": "folder", "path": "p"}, {"type": "web", "urls": ["http://a"]}],
        chunking=dict(strategy="fixed", max_tokens=500, overlap_tokens=50, keep_tables_whole=True),
        retrieval=dict(top_k=5, candidate_k=20, hybrid=True, keyword_weight=0.3, rerank=False),
        access=dict(allowed_roles=["admin"], default_doc_label="internal"),
        generation=dict(disclaimer="d", require_citations=True, refuse_topics=["x"]),
        eval=dict(min_recall_at_5=0.8, min_faithfulness=0.9, min_citation_precision=0.9, custom_checks=[]),
    )


INSTANCES = {
    "Document": lambda: Document(
        id=uuid4(), domain="demo", source_type="file", source_ref="r", storage_key="k",
        title="t", published_at=NOW, doc_label="public", content_hash="h", status="indexed",
        error_detail={"a": 1}, created_at=NOW, updated_at=NOW,
    ),
    "Chunk": lambda: Chunk(**make_chunk()),
    "RetrievedChunk": lambda: RetrievedChunk(**make_chunk(), score=0.9, rerank_score=None),
    "Citation": lambda: Citation(n=1, chunk_id=uuid4(), verified=True, source_title="t", page=2, source_url="u"),
    "Answer": lambda: Answer(
        domain="demo", answer_markdown="a [1]", status="answered",
        citations=[Citation(n=1, chunk_id=uuid4(), verified=True, source_title="t", page=2, source_url="u")],
        unsupported_sentences=["s"], disclaimer=None, model="m", prompt_version="v1", created_at=NOW,
    ),
    "DomainConfig": make_domain_config,
}


@pytest.mark.parametrize("name", INSTANCES)
def test_round_trip(name):
    original = INSTANCES[name]()
    restored = type(original).model_validate_json(original.model_dump_json())
    assert restored == original


def test_timestamps_serialize_in_ist():
    chunk = Chunk(**make_chunk())
    assert '"published_at":"2026-11-18T14:30:00+05:30"' in chunk.model_dump_json()


def test_naive_datetime_rejected():
    with pytest.raises(ValidationError):
        Chunk(**make_chunk(published_at=datetime(2026, 11, 18, 14, 30)))


def test_domain_config_rules():
    cfg = make_domain_config()
    assert cfg.enabled is False
    data = cfg.model_dump()
    with pytest.raises(ValidationError):
        DomainConfig(**{**data, "name": "Bad Name"})
    with pytest.raises(ValidationError):
        DomainConfig(**{**data, "retrieval": {**data["retrieval"], "keyword_weight": 1.5}})
