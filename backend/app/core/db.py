"""Postgres connection: engine, session factory, and a connectivity check."""

from functools import lru_cache

from sqlalchemy import Engine, create_engine, text
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import get_settings


@lru_cache
def get_engine() -> Engine:
    # Created lazily so importing this module never opens a connection.
    # pool_pre_ping drops dead connections instead of failing a request.
    return create_engine(get_settings().DATABASE_URL, pool_pre_ping=True)


@lru_cache
def get_session_factory() -> sessionmaker[Session]:
    return sessionmaker(bind=get_engine(), autoflush=False, expire_on_commit=False)


def check_db() -> None:
    """Run SELECT 1. Raises if Postgres is unreachable."""
    with get_engine().connect() as conn:
        conn.execute(text("SELECT 1"))
