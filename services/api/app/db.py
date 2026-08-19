import os

from sqlalchemy import create_engine
from sqlalchemy.engine import make_url
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from .config import get_settings


url = get_settings().database_url

if url.startswith("sqlite"):
    engine = create_engine(url, connect_args={"check_same_thread": False})
else:
    parsed = make_url(url)
    engine_options = {
        "pool_pre_ping": True,
        # Keep a small client-side pool even when connecting through Supabase's
        # transaction pooler. Supavisor pools database sessions, but opening a new
        # TCP/TLS client connection to Supavisor for every HTTP request is still
        # expensive and was adding seconds of latency in production.
        "pool_size": max(1, int(os.getenv("DB_POOL_SIZE", "3"))),
        "max_overflow": max(0, int(os.getenv("DB_MAX_OVERFLOW", "2"))),
        "pool_timeout": max(1, int(os.getenv("DB_POOL_TIMEOUT_SECONDS", "10"))),
        "pool_recycle": max(30, int(os.getenv("DB_POOL_RECYCLE_SECONDS", "300"))),
    }

    # Supabase transaction pooling does not support prepared statements reliably
    # across backend connections, so disable psycopg's automatic preparation while
    # still reusing the client connection itself.
    if parsed.host and parsed.host.endswith(".pooler.supabase.com") and parsed.port == 6543:
        if parsed.drivername.endswith("+psycopg"):
            engine_options["connect_args"] = {"prepare_threshold": None}

    engine = create_engine(url, **engine_options)

SessionLocal = sessionmaker(engine, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


def get_db():
    with SessionLocal() as session:
        yield session
