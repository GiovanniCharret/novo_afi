import os
from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker


DEFAULT_DATABASE_URL = "postgresql+psycopg://novo_afi:novo_afi@db:5432/novo_afi"

_engine = None
_sessionmaker = None
_configured_url = None


class Base(DeclarativeBase):
    pass


def get_database_url() -> str:
    return os.getenv("DATABASE_URL", DEFAULT_DATABASE_URL)


def get_engine():
    global _engine, _configured_url

    database_url = get_database_url()
    if _engine is not None and _configured_url == database_url:
        return _engine

    engine_kwargs = {}
    if database_url.startswith("sqlite"):
        engine_kwargs["connect_args"] = {"check_same_thread": False}

    _engine = create_engine(database_url, future=True, **engine_kwargs)
    _configured_url = database_url
    return _engine


def get_sessionmaker():
    global _sessionmaker

    if _sessionmaker is None:
        _sessionmaker = sessionmaker(bind=get_engine(), autoflush=False, autocommit=False, future=True)
    return _sessionmaker


def get_db() -> Generator[Session, None, None]:
    session = get_sessionmaker()()
    try:
        yield session
    finally:
        session.close()


def init_db() -> None:
    from . import models  # noqa: F401

    Base.metadata.create_all(bind=get_engine())


def reset_db_state() -> None:
    global _engine, _sessionmaker, _configured_url

    if _engine is not None:
        _engine.dispose()

    _engine = None
    _sessionmaker = None
    _configured_url = None
