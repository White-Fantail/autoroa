import os

from sqlalchemy import create_engine
from sqlalchemy.engine import make_url
from sqlalchemy.orm import DeclarativeBase, sessionmaker
from sqlalchemy.pool import NullPool

from .config import get_settings


url = get_settings().database_url

if url.startswith("sqlite"):
    engine = create_engine(url, connect_args={"check_same_thread": False})
else:
    parsed = make_url(url)
    engine_options = {
        "pool_pre_ping": True,
    }

    # Supabase transaction pooler (port 6543) already pools connections for us.
    # Avoid stacking SQLAlchemy's QueuePool on top of Supavisor.
    if parsed.host and parsed.host.endswith(".pooler.supabase.com") and parsed.port == 6543:
        engine_options["poolclass"] = NullPool
        if parsed.drivername.endswith("+psycopg"):
            engine_options["connect_args"] = {"prepare_threshold": None}
    else:
        # SQLAlchemy defaults to pool_size=5 + max_overflow=10. That can consume
        # an entire small Supabase session pool (15 clients) from one API process.
        # Keep a conservative per-process budget and allow Railway overrides.
        engine_options.update(
            pool_size=max(1, int(os.getenv("DB_POOL_SIZE", "3"))),
            max_overflow=max(0, int(os.getenv("DB_MAX_OVERFLOW", "2"))),
            pool_timeout=max(1, int(os.getenv("DB_POOL_TIMEOUT_SECONDS", "10"))),
            pool_recycle=max(30, int(os.getenv("DB_POOL_RECYCLE_SECONDS", "300"))),
        )

    engine = create_engine(url, **engine_options)

SessionLocal = sessionmaker(engine, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


def get_db():
    with SessionLocal() as session:
        yield session
