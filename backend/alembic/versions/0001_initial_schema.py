"""initial_schema

Revision ID: 0001
Revises:
Create Date: 2026-05-16
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = "0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    if not inspector.has_table("funding_rates"):
        op.create_table(
            "funding_rates",
            sa.Column("exchange", sa.String(), nullable=False),
            sa.Column("symbol", sa.String(), nullable=False),
            sa.Column("timestamp", sa.DateTime(), nullable=False),
            sa.Column("rate", sa.Float(), nullable=True),
            sa.Column("funding_interval", sa.Integer(), nullable=True, server_default="8"),
            sa.Column("settlement_time", sa.DateTime(), nullable=True),
            sa.PrimaryKeyConstraint("exchange", "symbol", "timestamp"),
        )
    indexes = [i["name"] for i in inspector.get_indexes("funding_rates")]
    if "idx_funding_lookup" not in indexes:
        op.create_index("idx_funding_lookup", "funding_rates", ["exchange", "symbol", sa.text("timestamp DESC")])


def downgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    indexes = [i["name"] for i in inspector.get_indexes("funding_rates")]
    if "idx_funding_lookup" in indexes:
        op.drop_index("idx_funding_lookup", table_name="funding_rates")
    if inspector.has_table("funding_rates"):
        op.drop_table("funding_rates")
