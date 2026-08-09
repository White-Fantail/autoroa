"""Reconcile legacy databases and apply all Alembic migrations."""
from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import inspect

from .db import engine

BASELINE_TABLES = {
    "account_deletions",
    "fill_ups",
    "fuel_price_observations",
    "fuel_station_brands",
    "fuel_station_current_prices",
    "fuel_stations",
    "media_assets",
    "odometer_readings",
    "profiles",
    "receipts",
    "upload_intents",
    "vehicles",
}


def alembic_config() -> Config:
    service_root = Path(__file__).resolve().parents[1]
    config = Config(str(service_root / "alembic.ini"))
    config.set_main_option("script_location", str(service_root / "alembic"))
    return config


def upgrade_database() -> None:
    inspector = inspect(engine)
    tables = set(inspector.get_table_names())
    if "alembic_version" not in tables and tables:
        application_tables = tables - {"rate_limits"}
        if application_tables != BASELINE_TABLES:
            missing = sorted(BASELINE_TABLES - application_tables)
            unexpected = sorted(application_tables - BASELINE_TABLES)
            raise RuntimeError(
                "Cannot reconcile untracked database schema: "
                f"missing tables={missing}, unexpected tables={unexpected}"
            )
        command.stamp(alembic_config(), "0001")
    command.upgrade(alembic_config(), "head")


if __name__ == "__main__":
    upgrade_database()
