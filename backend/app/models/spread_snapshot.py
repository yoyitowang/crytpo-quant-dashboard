from sqlalchemy import Column, Integer, String, Float, DateTime, Index, text
from datetime import datetime, timezone
from backend.app.models.funding_rate import Base


class SpreadSnapshot(Base):
    __tablename__ = "spread_snapshots"

    symbol = Column(String, primary_key=True)
    timestamp = Column(DateTime(timezone=True), primary_key=True, default=lambda: datetime.now(timezone.utc))
    spread = Column(Float)
    num_exchanges = Column(Integer)

    __table_args__ = (
        Index("idx_spread_snapshot_lookup", "symbol", text("timestamp DESC")),
    )
