"""Подключение к БД. MVP — SQLite, v1 — PostgreSQL (DATABASE_URL)."""
from __future__ import annotations

import os
from pathlib import Path

from sqlalchemy import create_engine, event
from sqlalchemy.orm import DeclarativeBase, sessionmaker

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DB = ROOT / "data" / "antifraud.db"


def make_engine(url: str | None = None):
    url = url or os.environ.get("DATABASE_URL")
    if not url:
        DEFAULT_DB.parent.mkdir(parents=True, exist_ok=True)
        url = f"sqlite:///{DEFAULT_DB.as_posix()}"
    kwargs = {}
    if url.startswith("sqlite"):
        kwargs["connect_args"] = {"check_same_thread": False}
        if url in ("sqlite://", "sqlite:///:memory:"):
            from sqlalchemy.pool import StaticPool

            kwargs["poolclass"] = StaticPool
    eng = create_engine(url, future=True, **kwargs)
    if url.startswith("sqlite"):

        @event.listens_for(eng, "connect")
        def _pragma(dbapi_conn, _):
            cur = dbapi_conn.cursor()
            cur.execute("PRAGMA foreign_keys=ON")
            cur.execute("PRAGMA journal_mode=WAL")
            cur.close()

    return eng


class Base(DeclarativeBase):
    pass


def make_session_factory(engine):
    return sessionmaker(bind=engine, expire_on_commit=False, future=True)
