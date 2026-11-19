"""GET /api/v1/health: checks that every backing service is reachable."""

import logging
import uuid
from typing import Callable

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse

from app.core.db import check_db
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

logger = logging.getLogger("app.health")
router = APIRouter()

OK = {"status": "ok"}


def _run(check: Callable[[], None]) -> dict:
    """Run a check; turn any exception into an error object naming the problem."""
    try:
        check()
        return dict(OK)
    except Exception as exc:  # noqa: BLE001 - health must report every failure type
        return {"status": "error", "message": str(exc) or type(exc).__name__}


def check_postgres() -> dict:
    return _run(check_db)


def check_qdrant(store: VectorStore) -> dict:
    def check() -> None:
        store.connect()
        store.ensure_collection("_healthcheck", vector_size=4)

    return _run(check)


def check_storage(storage: Storage) -> dict:
    def check() -> None:
        key = "_healthcheck/probe.bin"
        payload = uuid.uuid4().bytes
        storage.put(key, payload)
        if storage.get(key) != payload:
            raise RuntimeError("storage read-back did not match what was written")

    return _run(check)


def check_gemini(llm: LLMProvider, embedder: EmbeddingProvider) -> dict:
    def check() -> None:
        llm.generate("Reply with the word ok.")
        if not embedder.embed(["ping"]):
            raise RuntimeError("embedding call returned no vectors")

    return _run(check)


@router.get("/health")
def health(
    request: Request,
    deep: bool = False,
    store: VectorStore = Depends(get_vector_store),
    storage: Storage = Depends(get_storage),
    llm: LLMProvider = Depends(get_llm),
    embedder: EmbeddingProvider = Depends(get_embedder),
):
    # Gemini calls cost quota, so the result is cached (filled at startup);
    # ?deep=true forces a fresh call.
    cached = getattr(request.app.state, "gemini_status", None)
    if deep or cached is None:
        cached = check_gemini(llm, embedder)
        request.app.state.gemini_status = cached

    services = {
        "postgres": check_postgres(),
        "qdrant": check_qdrant(store),
        "gemini": cached,
        "storage": check_storage(storage),
    }
    healthy = all(s["status"] == "ok" for s in services.values())
    body = {"status": "ok" if healthy else "degraded", "services": services}
    if not healthy:
        logger.warning("health_degraded", extra={"services": services})
    return JSONResponse(content=body, status_code=200 if healthy else 503)
