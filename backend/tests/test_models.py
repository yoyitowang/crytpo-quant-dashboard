"""Tests for FundingRate model."""
from datetime import datetime, timezone
from backend.app.models.funding_rate import FundingRate, Base


def test_model_table_name():
    assert FundingRate.__tablename__ == "funding_rates"


def test_model_primary_key():
    pk = FundingRate.__table__.primary_key
    cols = [c.name for c in pk.columns]
    assert "exchange" in cols
    assert "symbol" in cols
    assert "timestamp" in cols


def test_model_has_required_columns():
    cols = [c.name for c in FundingRate.__table__.columns]
    assert "rate" in cols
    assert "funding_interval" in cols
    assert "settlement_time" in cols


def test_model_timestamp_has_timezone():
    ts_col = FundingRate.__table__.columns["timestamp"]
    assert ts_col.type.timezone is True


def test_model_settlement_time_has_timezone():
    st_col = FundingRate.__table__.columns["settlement_time"]
    assert st_col.type.timezone is True


def test_model_default_funding_interval():
    fi_col = FundingRate.__table__.columns["funding_interval"]
    assert fi_col.default.arg == 8


def test_model_has_index():
    indexes = [i.name for i in FundingRate.__table__.indexes]
    assert "idx_funding_lookup" in indexes
