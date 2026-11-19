"""Thin interfaces for external services, plus one implementation each.

Calling code depends only on the abstract classes (LLMProvider,
EmbeddingProvider, VectorStore, Storage) and gets instances from the
get_*() factories. Swapping Gemini or Qdrant later means adding a class
here and changing a factory, not touching callers.
"""

from abc import ABC, abstractmethod
from functools import lru_cache
from pathlib import Path

from app.core.config import get_settings


# ---------- Interfaces ----------

class LLMProvider(ABC):
    @abstractmethod
    def generate(self, prompt: str) -> str: ...


class EmbeddingProvider(ABC):
    @abstractmethod
    def embed(self, texts: list[str]) -> list[list[float]]: ...


class VectorStore(ABC):
    @abstractmethod
    def connect(self) -> None: ...

    @abstractmethod
    def ensure_collection(self, name: str, vector_size: int) -> None:
        """Create the collection if it doesn't exist. Safe to call repeatedly."""

    @abstractmethod
    def health(self) -> None:
        """Raise if the store is unreachable."""


class Storage(ABC):
    """Key/value blob storage. Keys are '/'-separated relative paths, which
    map onto both a local folder and an S3 bucket."""

    @abstractmethod
    def put(self, key: str, data: bytes) -> None: ...

    @abstractmethod
    def get(self, key: str) -> bytes: ...

    @abstractmethod
    def exists(self, key: str) -> bool: ...


# ---------- Gemini ----------

class GeminiLLMProvider(LLMProvider):
    def __init__(self, api_key: str, model: str):
        from google import genai  # imported here so tests never need the SDK client

        self._client = genai.Client(api_key=api_key)
        self._model = model

    def generate(self, prompt: str) -> str:
        response = self._client.models.generate_content(model=self._model, contents=prompt)
        return response.text or ""


class GeminiEmbeddingProvider(EmbeddingProvider):
    def __init__(self, api_key: str, model: str):
        from google import genai

        self._client = genai.Client(api_key=api_key)
        self._model = model

    def embed(self, texts: list[str]) -> list[list[float]]:
        response = self._client.models.embed_content(model=self._model, contents=texts)
        return [list(e.values or []) for e in (response.embeddings or [])]


# ---------- Qdrant ----------

class QdrantVectorStore(VectorStore):
    def __init__(self, url: str, api_key: str | None = None):
        self._url = url
        self._api_key = api_key
        self._client = None

    def connect(self) -> None:
        if self._client is None:
            from qdrant_client import QdrantClient

            # check_compatibility=False: skip the client/server version probe,
            # which would otherwise log a warning on every connect.
            self._client = QdrantClient(
                url=self._url, api_key=self._api_key, timeout=5, check_compatibility=False
            )

    def ensure_collection(self, name: str, vector_size: int) -> None:
        from qdrant_client.models import Distance, VectorParams

        self.connect()
        if not self._client.collection_exists(name):
            self._client.create_collection(
                collection_name=name,
                vectors_config=VectorParams(size=vector_size, distance=Distance.COSINE),
            )

    def health(self) -> None:
        self.connect()
        self._client.get_collections()


# ---------- Local storage ----------

class LocalStorage(Storage):
    def __init__(self, root: str | Path):
        self._root = Path(root).resolve()
        self._root.mkdir(parents=True, exist_ok=True)

    def _path(self, key: str) -> Path:
        path = (self._root / key).resolve()
        # Block keys like "../secret" from escaping the storage root.
        if not path.is_relative_to(self._root):
            raise ValueError(f"Storage key escapes the storage root: {key!r}")
        return path

    def put(self, key: str, data: bytes) -> None:
        path = self._path(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)

    def get(self, key: str) -> bytes:
        return self._path(key).read_bytes()

    def exists(self, key: str) -> bool:
        return self._path(key).is_file()


# ---------- Factories ----------
# Cached so the whole app shares one client per service.

@lru_cache
def get_llm() -> LLMProvider:
    s = get_settings()
    return GeminiLLMProvider(api_key=s.GEMINI_API_KEY, model=s.GEMINI_GENERATION_MODEL)


@lru_cache
def get_embedder() -> EmbeddingProvider:
    s = get_settings()
    return GeminiEmbeddingProvider(api_key=s.GEMINI_API_KEY, model=s.GEMINI_EMBEDDING_MODEL)


@lru_cache
def get_vector_store() -> VectorStore:
    s = get_settings()
    # An empty "QDRANT_API_KEY=" in .env means "no key", not an empty key.
    return QdrantVectorStore(url=s.QDRANT_URL, api_key=s.QDRANT_API_KEY or None)


@lru_cache
def get_storage() -> Storage:
    s = get_settings()
    if s.STORAGE_BACKEND == "local":
        return LocalStorage(s.STORAGE_LOCAL_ROOT)
    raise ValueError(f"Unsupported STORAGE_BACKEND: {s.STORAGE_BACKEND}")
