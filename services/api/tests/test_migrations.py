from datetime import datetime, timedelta, timezone
import importlib.util
from pathlib import Path
import os
import uuid

from alembic import command
from alembic.config import Config
import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.dialects.postgresql import ENUM

from app.config import get_settings


def migrate(database, revision, monkeypatch):
    monkeypatch.setenv("DATABASE_URL",f"sqlite:///{database}");get_settings.cache_clear();config=Config(str(Path(__file__).parents[1]/"alembic.ini"));command.upgrade(config,revision);get_settings.cache_clear()


def populate_0001(database, conflicting=False, collision=False):
    engine=create_engine(f"sqlite:///{database}");owner=str(uuid.uuid4());other=str(uuid.uuid4());vehicle=str(uuid.uuid4());now=datetime.now(timezone.utc)
    with engine.begin() as connection:
        for profile,auth in [(owner,"migration-owner"),(other,"migration-other")]:connection.execute(text("INSERT INTO profiles(id,auth_user_id,country_code,preferred_currency,preferred_distance_unit,preferred_efficiency_unit,created_at,updated_at) VALUES(:id,:auth,'NZ','NZD','km','L_PER_100KM',:now,:now)"),{"id":profile,"auth":auth,"now":now})
        connection.execute(text("INSERT INTO vehicles(id,user_id,nickname,make,model,fuel_type,is_primary,is_archived,created_at,updated_at) VALUES(:id,:owner,'Car','Test','Car','DIESEL',false,false,:now,:now)"),{"id":vehicle,"owner":owner,"now":now})
        for index,(days,odo,litres,full,missed) in enumerate([(2,1000,20,True,False),(1,1100,10,False,False),(0,1500,40,True,False)]):
            occurred=now-timedelta(days=days) if not (collision and index==1) else now-timedelta(days=2);connection.execute(text("INSERT INTO fill_ups(id,user_id,vehicle_id,occurred_at,fuel_type,litres,total_amount,currency,odometer_km,full_tank,missed_previous_fill,created_at,updated_at) VALUES(:id,:owner,:vehicle,:occurred,'DIESEL',:litres,:total,'NZD',:odo,:full,:missed,:now,:now)"),{"id":str(uuid.uuid4()),"owner":other if conflicting and index==0 else owner,"vehicle":vehicle,"occurred":occurred,"litres":litres,"total":litres*2,"odo":odo,"full":full,"missed":missed,"now":now})
    engine.dispose()


def test_populated_0001_backfills_authoritative_interval(tmp_path,monkeypatch):
    database=tmp_path/"populated.db";migrate(database,"0001",monkeypatch);populate_0001(database);migrate(database,"head",monkeypatch)
    with create_engine(f"sqlite:///{database}").connect() as connection:
        row=connection.execute(text("SELECT distance_since_previous_km,economy_fuel_litres,economy_cost_amount,fuel_economy_l_per_100km,economy_is_valid,economy_warning FROM fill_ups ORDER BY occurred_at DESC LIMIT 1")).mappings().one()
    assert row["distance_since_previous_km"]==500;assert float(row["economy_fuel_litres"])==50;assert float(row["economy_cost_amount"])==100;assert float(row["fuel_economy_l_per_100km"])==10;assert row["economy_is_valid"]==1;assert row["economy_warning"] is None


@pytest.mark.parametrize("mode",["conflict","collision"])
def test_populated_0001_diagnostics_preserve_data(tmp_path,monkeypatch,mode):
    database=tmp_path/f"{mode}.db";migrate(database,"0001",monkeypatch);populate_0001(database,conflicting=mode=="conflict",collision=mode=="collision")
    with pytest.raises(RuntimeError,match="Ownership conflicts|Equal-time fill-up collisions"):migrate(database,"head",monkeypatch)
    with create_engine(f"sqlite:///{database}").connect() as connection:assert connection.scalar(text("SELECT COUNT(*) FROM fill_ups"))==3


def test_clean_zero_to_head_and_constraint_metadata(tmp_path,monkeypatch):
    database=tmp_path/"clean.db";migrate(database,"head",monkeypatch)
    with create_engine(f"sqlite:///{database}").connect() as connection:
        indexes={row[1] for row in connection.execute(text("PRAGMA index_list('media_assets')"))}
        def mappings(table):
            rows=connection.execute(text(f"PRAGMA foreign_key_list('{table}')")).mappings().all();grouped={}
            for row in rows:grouped.setdefault(row["id"],[]).append((row["seq"],row["from"],row["table"],row["to"]))
            return {tuple((source,target) for _,source,_,target in sorted(group)):group[0][2] for group in grouped.values()}
        fill,receipt,odometer=mappings("fill_ups"),mappings("receipts"),mappings("odometer_readings")
    assert "uq_receipt_media_content" in indexes;assert fill[(("vehicle_id","id"),("user_id","user_id"))]=="vehicles";assert fill[(("receipt_id","id"),("user_id","user_id"))]=="receipts";assert fill[(("odometer_image_id","id"),("user_id","user_id"))]=="media_assets";assert receipt[(("media_asset_id","id"),("user_id","user_id"))]=="media_assets";assert odometer[(("vehicle_id","id"),("user_id","user_id"))]=="vehicles";assert odometer[(("media_asset_id","id"),("user_id","user_id"))]=="media_assets"


def test_untracked_legacy_baseline_is_reconciled_and_rate_limits_created(tmp_path,monkeypatch):
    database=tmp_path/"legacy.db";migrate(database,"0001",monkeypatch);engine=create_engine(f"sqlite:///{database}")
    with engine.begin() as connection:
        connection.execute(text("DROP TABLE rate_limits"));connection.execute(text("DROP TABLE alembic_version"))
    engine.dispose()
    from app import migrate as startup_migration
    monkeypatch.setattr(startup_migration,"engine",create_engine(f"sqlite:///{database}"));startup_migration.upgrade_database()
    with startup_migration.engine.connect() as connection:
        assert connection.scalar(text("SELECT version_num FROM alembic_version"))=="0003"
        assert connection.scalar(text("SELECT COUNT(*) FROM rate_limits"))==0
    startup_migration.engine.dispose()


@pytest.mark.parametrize("case,warning",[("missed_previous","MISSED_PREVIOUS_FILL"),("missed_chain","MISSED_FILL_CHAIN"),("nonincrease","NON_INCREASING_ODOMETER"),("short","DISTANCE_TOO_SHORT"),("outlier","ECONOMY_OUTLIER")])
def test_populated_0001_invalid_chain_warnings_clear_stale_fields(tmp_path,monkeypatch,case,warning):
    database=tmp_path/f"{case}.db";migrate(database,"0001",monkeypatch);populate_0001(database);engine=create_engine(f"sqlite:///{database}")
    with engine.begin() as connection:
        final=connection.scalar(text("SELECT id FROM fill_ups ORDER BY occurred_at DESC LIMIT 1"));partial=connection.scalar(text("SELECT id FROM fill_ups ORDER BY occurred_at DESC LIMIT 1 OFFSET 1"));connection.execute(text("UPDATE fill_ups SET distance_since_previous_km=999,fuel_economy_l_per_100km=9,cost_per_100km=9 WHERE id=:id"),{"id":final})
        if case=="missed_previous":connection.execute(text("UPDATE fill_ups SET missed_previous_fill=true WHERE id=:id"),{"id":final})
        elif case=="missed_chain":connection.execute(text("UPDATE fill_ups SET missed_previous_fill=true WHERE id=:id"),{"id":partial})
        elif case=="nonincrease":connection.execute(text("UPDATE fill_ups SET odometer_km=900 WHERE id=:id"),{"id":final})
        elif case=="short":connection.execute(text("UPDATE fill_ups SET odometer_km=1002 WHERE id=:partial"),{"partial":partial});connection.execute(text("UPDATE fill_ups SET odometer_km=1005 WHERE id=:final"),{"final":final})
        else:connection.execute(text("UPDATE fill_ups SET litres=600 WHERE id=:id"),{"id":final})
    engine.dispose();migrate(database,"head",monkeypatch)
    with create_engine(f"sqlite:///{database}").connect() as connection:row=connection.execute(text("SELECT distance_since_previous_km,fuel_economy_l_per_100km,cost_per_100km,economy_is_valid,economy_warning FROM fill_ups ORDER BY occurred_at DESC LIMIT 1")).mappings().one()
    assert row["fuel_economy_l_per_100km"] is None;assert row["cost_per_100km"] is None;assert row["economy_is_valid"]==0;assert row["economy_warning"]==warning


@pytest.mark.skipif(not os.getenv("AUTOROA_TEST_POSTGRES_URL"),reason="AUTOROA_TEST_POSTGRES_URL is not configured")
def test_postgresql_zero_and_incremental_migrations(monkeypatch):
    url=os.environ["AUTOROA_TEST_POSTGRES_URL"];monkeypatch.setenv("DATABASE_URL",url);get_settings.cache_clear();config=Config(str(Path(__file__).parents[1]/"alembic.ini"));command.downgrade(config,"base");command.upgrade(config,"head");command.downgrade(config,"base");command.upgrade(config,"0001");command.upgrade(config,"head");get_settings.cache_clear()


def test_ocr_jobs_reuses_existing_postgresql_status_enum(monkeypatch):
    migration_path=Path(__file__).parents[1]/"alembic"/"versions"/"0004_ocr_jobs.py"
    spec=importlib.util.spec_from_file_location("ocr_jobs_migration",migration_path);assert spec and spec.loader
    migration=importlib.util.module_from_spec(spec);spec.loader.exec_module(migration)
    created_columns={}
    def capture_table(_name,*items):created_columns.update({item.name:item for item in items if getattr(item,"name",None)})
    monkeypatch.setattr(migration.op,"create_table",capture_table);monkeypatch.setattr(migration.op,"create_index",lambda *args,**kwargs:None);monkeypatch.setattr(migration.op,"add_column",lambda *args,**kwargs:None)
    migration.upgrade();status_type=created_columns["status"].type
    assert isinstance(status_type,ENUM);assert status_type.name=="status";assert status_type.create_type is False
