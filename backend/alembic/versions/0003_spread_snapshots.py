"""spread_snapshots

Revision ID: 0003
Revises: 0002
Create Date: 2026-05-20
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = "0003"
down_revision: Union[str, None] = "0002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    if not inspector.has_table("spread_snapshots"):
        op.create_table(
            "spread_snapshots",
            sa.Column("symbol", sa.String(), nullable=False),
            sa.Column("timestamp", sa.DateTime(timezone=True), nullable=False),
            sa.Column("spread", sa.Float(), nullable=True),
            sa.Column("num_exchanges", sa.Integer(), nullable=True),
            sa.PrimaryKeyConstraint("symbol", "timestamp"),
        )
    indexes = [i["name"] for i in inspector.get_indexes("spread_snapshots")]
    if "idx_spread_snapshot_lookup" not in indexes:
        op.create_index("idx_spread_snapshot_lookup", "spread_snapshots", ["symbol", sa.text("timestamp DESC")])


def downgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    indexes = [i["name"] for i in inspector.get_indexes("spread_snapshots")]
    if "idx_spread_snapshot_lookup" in indexes:
        op.drop_index("idx_spread_snapshot_lookup", table_name="spread_snapshots")
    if inspector.has_table("spread_snapshots"):
        op.drop_table("spread_snapshots")
