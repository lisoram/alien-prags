import os

# Must be set before app modules import: create_app() reads Settings at import time.
os.environ.update(
    DATABASE_URL="postgresql+psycopg://test:test@localhost:5432/test",
    QDRANT_URL="http://localhost:6333",
    GEMINI_API_KEY="test-key",
    GEMINI_GENERATION_MODEL="test-gen-model",
    GEMINI_EMBEDDING_MODEL="test-embed-model",
    CORS_ORIGINS="http://localhost:3000",
)

import pytest
from fastapi.testclient import TestClient

from app.api import health
from app.core.providers import (
    EmbeddingProvider,
    LLMProvider,
    Storage,
    VectorStore,
    get_embedder,
    get_llm,
    get_storage,
    get_vector_store,
)
from app.main import app


class FakeLLM(LLMProvider):
    def generate(self, prompt: str) -> str:
        return "ok"


class FakeEmbedder(EmbeddingProvider):
    def embed(self, texts):
        return [[0.1, 0.2] for _ in texts]


class FakeVectorStore(VectorStore):
    def __init__(self, fail: str | None = None):
        self.fail = fail

    def connect(self) -> None:
        if self.fail:
            raise ConnectionError(self.fail)

    def ensure_collection(self, name, vector_size) -> None:
        self.connect()

    def health(self) -> None:
        self.connect()


class MemoryStorage(Storage):
    def __init__(self):
        self.data = {}

    def put(self, key, data):
        self.data[key] = data

    def get(self, key):
        return self.data[key]

    def exists(self, key):
        return key in self.data


@pytest.fixture
def make_client(monkeypatch):
    """Build a TestClient with fake providers. Not used as a context manager,
    so the startup lifespan (which needs real Postgres) is skipped."""

    def _make(qdrant_fail: str | None = None) -> TestClient:
        monkeypatch.setattr(health, "check_db", lambda: None)
        app.state.gemini_status = None  # reset cache between tests
        app.dependency_overrides[get_llm] = lambda: FakeLLM()
        app.dependency_overrides[get_embedder] = lambda: FakeEmbedder()
        app.dependency_overrides[get_vector_store] = lambda: FakeVectorStore(qdrant_fail)
        app.dependency_overrides[get_storage] = lambda: MemoryStorage()
        return TestClient(app)

    yield _make
    app.dependency_overrides.clear()
