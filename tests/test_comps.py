"""Tests for comps service: manual comps, no fake data."""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("DRY_RUN", "true")
os.environ.setdefault("ENVIRONMENT", "test")

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from core.db import Base
from core.models import Parcel, ManualComp
from services.comps import CompsService, CompSale, CompsResult


@pytest.fixture(scope="module")
def test_engine():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    @event.listens_for(engine, "connect")
    def set_sqlite_pragma(dbapi_connection, connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    Base.metadata.create_all(bind=engine)
    yield engine
    Base.metadata.drop_all(bind=engine)


@pytest.fixture
def db_session(test_engine):
    connection = test_engine.connect()
    transaction = connection.begin()
    Session = sessionmaker(autocommit=False, autoflush=False, bind=connection)
    session = Session()
    yield session
    session.close()
    transaction.rollback()
    connection.close()


@pytest.fixture
def sample_parcel(db_session) -> Parcel:
    parcel = Parcel(
        canonical_parcel_id="COMP_TEST_001",
        parish="East Baton Rouge",
        situs_address="100 Test St",
        city="Baton Rouge",
        state="LA",
        postal_code="70808",
        land_assessed_value=10000.0,
        lot_size_acres=2.0,
        market_code="LA",
    )
    db_session.add(parcel)
    db_session.flush()
    return parcel


class TestCompsServiceNoData:
    """When no comps exist, the service should return empty results, not mock data."""

    def test_returns_empty_when_no_comps(self, db_session, sample_parcel):
        service = CompsService(session=db_session)
        result = service.get_comps_for_parcel(sample_parcel)

        assert result.total_comps_found == 0
        assert result.is_mock_data is False
        assert result.source == "none"
        assert result.comps == []
        assert result.message is not None
        assert "No verified comps found" in result.message

    def test_no_session_returns_empty(self, sample_parcel):
        service = CompsService(session=None)
        result = service.get_comps_for_parcel(sample_parcel)
        assert result.total_comps_found == 0
        assert result.is_mock_data is False


class TestCompsServiceManualComps:
    """When manual comps are in the DB, they should be returned."""

    def test_manual_comps_by_parcel_id(self, db_session, sample_parcel):
        comp = ManualComp(
            parcel_id=sample_parcel.id,
            address="200 Oak St, Baton Rouge, LA",
            sale_date="2025-06-15",
            sale_price=15000.0,
            lot_size_acres=1.5,
            parish="East Baton Rouge",
            market_code="LA",
        )
        db_session.add(comp)
        db_session.flush()

        service = CompsService(session=db_session)
        result = service.get_comps_for_parcel(sample_parcel)

        assert result.total_comps_found == 1
        assert result.is_mock_data is False
        assert result.source == "manual"
        assert result.comps[0].address == "200 Oak St, Baton Rouge, LA"
        assert result.comps[0].sale_price == 15000.0
        assert result.comps[0].price_per_acre == 10000.0  # 15000 / 1.5

    def test_manual_comps_by_parish_fallback(self, db_session):
        """When parcel has no direct comps, fall back to parish match."""
        parcel = Parcel(
            canonical_parcel_id="COMP_TEST_002",
            parish="Caddo",
            city="Shreveport",
            state="LA",
            lot_size_acres=5.0,
            market_code="LA",
        )
        db_session.add(parcel)
        db_session.flush()

        comp = ManualComp(
            address="500 Market St, Shreveport, LA",
            sale_date="2025-03-01",
            sale_price=25000.0,
            lot_size_acres=5.0,
            parish="Caddo",
            market_code="LA",
        )
        db_session.add(comp)
        db_session.flush()

        service = CompsService(session=db_session)
        result = service.get_comps_for_parcel(parcel)

        assert result.total_comps_found == 1
        assert result.source == "manual"

    def test_statistics_calculation(self, db_session, sample_parcel):
        for i, price in enumerate([10000, 20000, 30000]):
            comp = ManualComp(
                parcel_id=sample_parcel.id,
                address=f"{i} Stat St, BR, LA",
                sale_date="2025-01-01",
                sale_price=price,
                lot_size_acres=1.0,
                parish="East Baton Rouge",
                market_code="LA",
            )
            db_session.add(comp)
        db_session.flush()

        service = CompsService(session=db_session)
        result = service.get_comps_for_parcel(sample_parcel)

        assert result.total_comps_found >= 3
        assert result.min_price_per_acre == 10000.0
        assert result.max_price_per_acre == 30000.0
        assert result.avg_price_per_acre == 20000.0
        assert result.median_price_per_acre == 20000.0


class TestCompsResultSerialization:
    def test_to_dict(self):
        result = CompsResult(
            comps=[
                CompSale(
                    address="123 Main",
                    sale_date="2025-01-01",
                    sale_price=50000,
                    lot_size_acres=2.0,
                    price_per_acre=25000,
                    source="manual",
                ),
            ],
            avg_price_per_acre=25000,
            min_price_per_acre=25000,
            max_price_per_acre=25000,
            median_price_per_acre=25000,
            total_comps_found=1,
            is_mock_data=False,
            source="manual",
        )
        d = result.to_dict()
        assert d["total_comps_found"] == 1
        assert d["is_mock_data"] is False
        assert d["source"] == "manual"
        assert len(d["comps"]) == 1
        assert d["comps"][0]["price_per_acre"] == 25000.0
