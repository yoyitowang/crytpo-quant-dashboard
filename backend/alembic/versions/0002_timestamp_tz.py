"""make timestamp and settlement_time timezone-aware

Revision ID: 0002
Revises: 0001
Create Date: 2026-05-16
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = "0002"
down_revision: Union[str, None] = "0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    if inspector.has_table("funding_rates"):
        cols = {c["name"]: c for c in inspector.get_columns("funding_rates")}
        ts_col = cols.get("timestamp")
        if ts_col:
            t = ts_col["type"]
            has_tz = hasattr(t, "timezone") and t.timezone
            if not has_tz:
                op.alter_column("funding_rates", "timestamp", type_=sa.DateTime(timezone=True), postgresql_using="timestamp AT TIME ZONE 'UTC'")
        st_col = cols.get("settlement_time")
        if st_col and st_col.get("type") is not None:
            t = st_col["type"]
            has_tz = hasattr(t, "timezone") and t.timezone
            if not has_tz:
                op.alter_column("funding_rates", "settlement_time", type_=sa.DateTime(timezone=True), postgresql_using="settlement_time AT TIME ZONE 'UTC'")


def downgrade() -> None:
    op.alter_column("funding_rates", "timestamp", type_=sa.DateTime(), postgresql_using="timestamp AT TIME ZONE 'UTC'")
    op.alter_column("funding_rates", "settlement_time", type_=sa.DateTime(), postgresql_using="settlement_time AT TIME ZONE 'UTC'")
