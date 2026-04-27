from sqlalchemy import Column, Integer, String, Float, DateTime, Index
from sqlalchemy.orm import DeclarativeBase
from datetime import datetime

class Base(DeclarativeBase):
    pass

class FundingRate(Base):
    __tablename__ = "funding_rates"
    __table_args__ = {
        'postgresql_partition_by': 'RANGE (timestamp)',
    }

    # 在分區表中，主鍵必須包含分區鍵
    exchange = Column(String, primary_key=True)
    symbol = Column(String, primary_key=True)
    timestamp = Column(DateTime, primary_key=True, default=datetime.utcnow)
    
    rate = Column(Float)
    settlement_time = Column(DateTime)

# 建立複合索引以加速查詢
Index('idx_funding_lookup', FundingRate.exchange, FundingRate.symbol, FundingRate.timestamp.desc())
