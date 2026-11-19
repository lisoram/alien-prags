"""Domain service: the one place other modules ask "what are the rules for this domain?".

    get_domain(name)                        -> LoadedDomain | None
    list_domains(enabled_only=True, role=None) -> list[LoadedDomain]
    get_glossary(name)                      -> Glossary | None
    reload()                                -> ReloadResult   (startup + admin reload)

The loaded domains live in memory as one immutable snapshot that reload() swaps
in whole, so readers never see a half-updated registry.
"""

import logging
import threading
from dataclasses import dataclass, replace
from datetime import datetime
from pathlib import Path

from sqlalchemy import text
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import get_settings
from app.core.db import get_session_factory
from app.domains.glossary import Glossary
from app.domains.loader import LoadedDomain, PackIssue, scan_packs
from app.schemas import IST

logger = logging.getLogger("app.domains.service")

_reload_lock = threading.Lock()


@dataclass(frozen=True)
class ReloadResult:
    loaded: list[str]
    failed: list[PackIssue]


@dataclass(frozen=True)
class _Snapshot:
    domains: dict[str, LoadedDomain]
    failures: list[PackIssue]


_snapshot = _Snapshot(domains={}, failures=[])


# ---------- Reads (what other modules call) ----------

def get_domain(name: str) -> LoadedDomain | None:
    return _snapshot.domains.get(name)


def list_domains(enabled_only: bool = True, role: str | None = None) -> list[LoadedDomain]:
    """Loaded domains sorted by name. role=None means "don't filter by role"."""
    result = []
    for domain in sorted(_snapshot.domains.values(), key=lambda d: d.config.name):
        if enabled_only and not domain.enabled:
            continue
        if role is not None and role not in domain.config.access.allowed_roles:
            continue
        result.append(domain)
    return result


def get_glossary(name: str) -> Glossary | None:
    domain = _snapshot.domains.get(name)
    return domain.glossary if domain else None


def get_load_failures() -> list[PackIssue]:
    return list(_snapshot.failures)


# ---------- Reload ----------

def _fetch_eval_run_ids(factory: sessionmaker[Session]) -> dict[str, str | None]:
    with factory() as session:
        rows = session.execute(text("SELECT name, last_eval_run_id FROM domains")).all()
    return {name: run_id for name, run_id in rows}


def _apply_enable_gate(
    packs: list[LoadedDomain], eval_run_ids: dict[str, str | None], allow_unevaluated: bool
) -> list[LoadedDomain]:
    """A domain that says enabled: true but has no eval run stays disabled.

    "Has a passing eval run" is approximated by last_eval_run_id being set; Module 9
    (which creates eval runs) will tighten this to "the run passed".
    """
    gated = []
    for pack in packs:
        if pack.config.enabled and not eval_run_ids.get(pack.config.name) and not allow_unevaluated:
            logger.warning(
                "domain_kept_disabled_no_eval_run",
                extra={
                    "domain": pack.config.name,
                    "hint": "domain.yaml says enabled: true but no passing eval run exists yet",
                },
            )
            pack = replace(pack, enabled=False)
        elif pack.config.enabled and allow_unevaluated and not eval_run_ids.get(pack.config.name):
            logger.warning(
                "domain_enabled_without_eval_run_dev_override",
                extra={"domain": pack.config.name, "setting": "ALLOW_UNEVALUATED_DOMAINS"},
            )
        gated.append(pack)
    return gated


_UPSERT = text(
    """
    INSERT INTO domains (name, display_name, enabled, config_hash, loaded_at)
    VALUES (:name, :display_name, :enabled, :config_hash, :loaded_at)
    ON CONFLICT (name) DO UPDATE SET
        display_name = excluded.display_name,
        enabled = excluded.enabled,
        config_hash = excluded.config_hash,
        loaded_at = excluded.loaded_at
    """
)


def _sync_to_db(packs: list[LoadedDomain], factory: sessionmaker[Session]) -> None:
    """Upsert one row per loaded pack. Never touches last_ingested_at / last_eval_run_id."""
    now = datetime.now(IST)
    with factory() as session:
        for pack in packs:
            session.execute(
                _UPSERT,
                {
                    "name": pack.config.name,
                    "display_name": pack.config.display_name,
                    "enabled": pack.enabled,
                    "config_hash": pack.config_hash,
                    "loaded_at": now,
                },
            )
        session.commit()


def reload(
    domains_dir: Path | None = None,
    session_factory: sessionmaker[Session] | None = None,
    allow_unevaluated: bool | None = None,
) -> ReloadResult:
    """Re-scan domains/, validate every pack, sync Postgres, and swap in the new snapshot.

    Arguments default to the app settings; tests pass their own.
    """
    global _snapshot
    settings = get_settings()
    domains_dir = domains_dir if domains_dir is not None else Path(settings.DOMAINS_DIR)
    factory = session_factory or get_session_factory()
    if allow_unevaluated is None:
        allow_unevaluated = settings.ALLOW_UNEVALUATED_DOMAINS

    with _reload_lock:
        packs, issues = scan_packs(domains_dir)
        packs = _apply_enable_gate(packs, _fetch_eval_run_ids(factory), allow_unevaluated)
        _sync_to_db(packs, factory)  # if this raises, the old snapshot stays in place
        _snapshot = _Snapshot(domains={p.config.name: p for p in packs}, failures=issues)

    result = ReloadResult(loaded=sorted(_snapshot.domains), failed=issues)
    logger.info(
        "domains_reloaded",
        extra={
            "loaded": result.loaded,
            "enabled": [d.config.name for d in list_domains(enabled_only=True)],
            "failed_count": len(issues),
        },
    )
    return result
