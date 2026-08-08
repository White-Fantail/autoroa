"""Add ownership integrity, economy interval metadata, and media hashes.

Revision ID: 0002
Revises: 0001
"""
from typing import Sequence, Union
from decimal import Decimal

from alembic import op
import sqlalchemy as sa

revision: str = "0002"
down_revision: Union[str, None] = "0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    connection=op.get_bind()
    audits={
        "fill_up/vehicle": "SELECT COUNT(*) FROM fill_ups f JOIN vehicles v ON v.id=f.vehicle_id WHERE f.user_id<>v.user_id",
        "odometer/vehicle": "SELECT COUNT(*) FROM odometer_readings o JOIN vehicles v ON v.id=o.vehicle_id WHERE o.user_id<>v.user_id",
        "receipt/media": "SELECT COUNT(*) FROM receipts r JOIN media_assets m ON m.id=r.media_asset_id WHERE r.user_id<>m.user_id",
        "odometer/media": "SELECT COUNT(*) FROM odometer_readings o JOIN media_assets m ON m.id=o.media_asset_id WHERE o.user_id<>m.user_id",
        "fill_up/receipt": "SELECT COUNT(*) FROM fill_ups f JOIN receipts r ON r.id=f.receipt_id WHERE f.user_id<>r.user_id",
        "fill_up/odometer_media": "SELECT COUNT(*) FROM fill_ups f JOIN media_assets m ON m.id=f.odometer_image_id WHERE f.user_id<>m.user_id",
    }
    conflicts={name:connection.scalar(sa.text(query)) for name,query in audits.items()}
    conflicts={name:count for name,count in conflicts.items() if count}
    if conflicts:raise RuntimeError(f"Ownership conflicts must be resolved before migration 0002: {conflicts}")
    collisions=connection.execute(sa.text("SELECT vehicle_id,occurred_at,COUNT(*) AS count FROM fill_ups GROUP BY vehicle_id,occurred_at HAVING COUNT(*)>1")).mappings().all()
    if collisions:raise RuntimeError(f"Equal-time fill-up collisions must be resolved before migration 0002: {len(collisions)} groups")
    with op.batch_alter_table("vehicles") as batch:
        batch.create_unique_constraint("uq_vehicle_owner", ["id", "user_id"])
    with op.batch_alter_table("media_assets") as batch:
        batch.add_column(sa.Column("content_sha256", sa.String(64), nullable=True))
        batch.create_unique_constraint("uq_media_owner", ["id", "user_id"])
    op.create_index("uq_receipt_media_content", "media_assets", ["content_sha256"], unique=True, postgresql_where=sa.text("type = 'RECEIPT'"), sqlite_where=sa.text("type = 'RECEIPT'"))
    op.create_table("receipt_fingerprints",sa.Column("content_sha256",sa.String(64),primary_key=True),sa.Column("created_at",sa.DateTime(timezone=True),nullable=False))
    with op.batch_alter_table("receipts") as batch:
        batch.create_unique_constraint("uq_receipt_owner", ["id", "user_id"])
        batch.create_foreign_key("fk_receipt_media_owner", "media_assets", ["media_asset_id", "user_id"], ["id", "user_id"])
    with op.batch_alter_table("odometer_readings") as batch:
        batch.create_foreign_key("fk_odometer_vehicle_owner", "vehicles", ["vehicle_id", "user_id"], ["id", "user_id"])
        batch.create_foreign_key("fk_odometer_media_owner", "media_assets", ["media_asset_id", "user_id"], ["id", "user_id"])
    with op.batch_alter_table("fill_ups") as batch:
        batch.add_column(sa.Column("economy_fuel_litres", sa.Numeric(12, 3), nullable=True))
        batch.add_column(sa.Column("economy_cost_amount", sa.Numeric(12, 2), nullable=True))
        batch.add_column(sa.Column("economy_started_at",sa.DateTime(timezone=True),nullable=True))
        batch.add_column(sa.Column("economy_is_valid", sa.Boolean(), nullable=False, server_default=sa.false()))
        batch.add_column(sa.Column("economy_warning", sa.String(), nullable=True))
        batch.create_unique_constraint("uq_fill_vehicle_occurred",["vehicle_id","occurred_at"])
        batch.create_foreign_key("fk_fill_vehicle_owner", "vehicles", ["vehicle_id", "user_id"], ["id", "user_id"])
        batch.create_foreign_key("fk_fill_receipt_owner", "receipts", ["receipt_id", "user_id"], ["id", "user_id"])
        batch.create_foreign_key("fk_fill_odometer_media_owner", "media_assets", ["odometer_image_id", "user_id"], ["id", "user_id"])
    rows=connection.execute(sa.text("SELECT id,vehicle_id,occurred_at,odometer_km,litres,total_amount,full_tank,missed_previous_fill FROM fill_ups ORDER BY vehicle_id,occurred_at,id")).mappings().all()
    connection.execute(sa.text("UPDATE fill_ups SET distance_since_previous_km=NULL,fuel_economy_l_per_100km=NULL,cost_per_100km=NULL,economy_fuel_litres=NULL,economy_cost_amount=NULL,economy_started_at=NULL,economy_is_valid=false,economy_warning=NULL"))
    histories={}
    for row in rows:histories.setdefault(row["vehicle_id"],[]).append(row)
    for history in histories.values():
        for index,row in enumerate(history):
            if not row["full_tank"]:continue
            if row["missed_previous_fill"]:
                connection.execute(sa.text("UPDATE fill_ups SET economy_warning='MISSED_PREVIOUS_FILL' WHERE id=:id"),{"id":row["id"]});continue
            litres=Decimal(row["litres"]);cost=Decimal(row["total_amount"])
            for prior in reversed(history[:index]):
                if prior["missed_previous_fill"]:
                    connection.execute(sa.text("UPDATE fill_ups SET economy_warning='MISSED_FILL_CHAIN' WHERE id=:id"),{"id":row["id"]});break
                if prior["odometer_km"]>=row["odometer_km"]:
                    connection.execute(sa.text("UPDATE fill_ups SET economy_warning='NON_INCREASING_ODOMETER' WHERE id=:id"),{"id":row["id"]});break
                if prior["full_tank"]:
                    distance=row["odometer_km"]-prior["odometer_km"];economy=litres/Decimal(distance)*100
                    if distance>=10 and Decimal("0.5")<=economy<=Decimal("100"):
                        connection.execute(sa.text("UPDATE fill_ups SET distance_since_previous_km=:distance,fuel_economy_l_per_100km=:economy,cost_per_100km=:cost_rate,economy_fuel_litres=:litres,economy_cost_amount=:cost,economy_started_at=:started,economy_is_valid=true,economy_warning=NULL WHERE id=:id"),{"distance":distance,"economy":float(economy.quantize(Decimal(".001"))),"cost_rate":float((cost/Decimal(distance)*100).quantize(Decimal(".01"))),"litres":float(litres),"cost":float(cost),"started":prior["occurred_at"],"id":row["id"]})
                    else:
                        warning="DISTANCE_TOO_SHORT" if distance<10 else "ECONOMY_OUTLIER";connection.execute(sa.text("UPDATE fill_ups SET distance_since_previous_km=:distance,economy_fuel_litres=:litres,economy_cost_amount=:cost,economy_started_at=:started,economy_warning=:warning WHERE id=:id"),{"distance":distance,"litres":float(litres),"cost":float(cost),"started":prior["occurred_at"],"warning":warning,"id":row["id"]})
                    break
                litres+=Decimal(prior["litres"]);cost+=Decimal(prior["total_amount"])


def downgrade() -> None:
    op.drop_table("receipt_fingerprints")
    with op.batch_alter_table("fill_ups") as batch:
        batch.drop_constraint("uq_fill_vehicle_occurred",type_="unique")
        batch.drop_constraint("fk_fill_odometer_media_owner", type_="foreignkey")
        batch.drop_constraint("fk_fill_receipt_owner", type_="foreignkey")
        batch.drop_constraint("fk_fill_vehicle_owner", type_="foreignkey")
        batch.drop_column("economy_warning")
        batch.drop_column("economy_is_valid")
        batch.drop_column("economy_cost_amount")
        batch.drop_column("economy_started_at")
        batch.drop_column("economy_fuel_litres")
    with op.batch_alter_table("odometer_readings") as batch:
        batch.drop_constraint("fk_odometer_media_owner", type_="foreignkey")
        batch.drop_constraint("fk_odometer_vehicle_owner", type_="foreignkey")
    with op.batch_alter_table("receipts") as batch:
        batch.drop_constraint("fk_receipt_media_owner", type_="foreignkey")
        batch.drop_constraint("uq_receipt_owner", type_="unique")
    op.drop_index("uq_receipt_media_content", table_name="media_assets")
    with op.batch_alter_table("media_assets") as batch:
        batch.drop_constraint("uq_media_owner", type_="unique")
        batch.drop_column("content_sha256")
    with op.batch_alter_table("vehicles") as batch:
        batch.drop_constraint("uq_vehicle_owner", type_="unique")
