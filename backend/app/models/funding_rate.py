from sqlalchemy import Column, Integer, String, Float, DateTime, Index, text
from sqlalchemy.orm import DeclarativeBase
from datetime import datetime

class Base(DeclarativeBase):
    pass

class FundingRate(Base):
    __tablename__ = "funding_rates"

    exchange = Column(String, primary_key=True)
    symbol = Column(String, primary_key=True)
    timestamp = Column(DateTime, primary_key=True, default=datetime.utcnow)

    rate = Column(Float)
    funding_interval = Column(Integer, default=8)
    settlement_time = Column(DateTime)

    __table_args__ = (
        Index("idx_funding_lookup", "exchange", "symbol", text("timestamp DESC")),
    )
