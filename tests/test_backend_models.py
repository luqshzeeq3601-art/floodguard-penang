"""Backend schema/model tests: identity, constraints, types, SRID (offline)."""

from __future__ import annotations

from typing import Any

import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.schema import CreateTable

from floodguard.backend import models
from floodguard.backend.models import Base
from floodguard.station_master import SensorType, ThresholdType
from tests.backend_helpers import (
    make_engine,
    make_observation,
    make_sensor,
    make_site,
    make_threshold,
)

pytestmark = pytest.mark.usefixtures("no_network")


def test_all_tables_created_in_order() -> None:
    assert list(Base.metadata.tables) == list(models.TABLES_IN_ORDER)


def test_check_constraints_derive_from_python_enums() -> None:
    from floodguard.backend import models as m

    assert SensorType.RAINFALL.value in m.CK_SENSORS_TYPE_MEASUREMENT_UNIT
    assert SensorType.WATER_LEVEL.value in m.CK_SENSORS_TYPE_MEASUREMENT_UNIT
    assert ThresholdType.NORMAL.value in m.CK_THRESHOLDS_NORMAL
    for threshold in (
        ThresholdType.WASPADA.value,
        ThresholdType.AMARAN.value,
        ThresholdType.BAHAYA.value,
    ):
        assert threshold in m.CK_THRESHOLDS_NORMAL
    for measurement in ("RAINFALL_INTERVAL", "RAINFALL_1H_TOTAL", "WATER_LEVEL"):
        assert measurement in m.CK_OBSERVATIONS_MEASUREMENT


def _pg_dialect() -> Any:
    # PGDialect() is untyped in SQLAlchemy stubs; isolate the ignore here.
    from sqlalchemy.dialects.postgresql.base import PGDialect

    return PGDialect()  # type: ignore[no-untyped-call]


def test_postgres_ddl_uses_postgis_geometry_and_gist() -> None:
    dialect = _pg_dialect()
    ddl = str(CreateTable(Base.metadata.tables["sites"]).compile(dialect=dialect))
    assert "geometry(POINT,4326)" in ddl
    from sqlalchemy.schema import CreateIndex

    index_ddl = " ".join(
        str(CreateIndex(index).compile(dialect=_pg_dialect()))
        for index in Base.metadata.tables["sites"].indexes
    )
    assert "USING gist" in index_ddl


def test_observation_pk_and_timestamp_columns_are_tz_aware() -> None:
    table = Base.metadata.tables["observations"]
    assert [c.name for c in table.primary_key.columns] == [
        "source",
        "fg_sensor_id",
        "measurement_type",
        "observation_time_utc",
    ]
    assert getattr(table.c.observation_time_utc.type, "timezone", False) is True


def test_station_name_is_not_unique() -> None:
    engine = make_engine()
    from sqlalchemy.orm import Session, sessionmaker

    session = sessionmaker(bind=engine, class_=Session)()
    session.add(make_site("site-a", site_name="Same Name"))
    session.add(make_site("site-b", site_name="Same Name"))
    session.commit()
    assert session.query(models.Site).count() == 2


def test_sensor_unit_mismatch_rejected() -> None:
    engine = make_engine()
    from sqlalchemy.orm import Session, sessionmaker

    session = sessionmaker(bind=engine, class_=Session)()
    session.add(make_site())
    session.add(make_sensor(sensor_type="WATER_LEVEL", measurement_type="WATER_LEVEL", unit="mm"))
    with pytest.raises(IntegrityError):
        session.commit()


def test_normal_threshold_never_label_eligible() -> None:
    engine = make_engine()
    from sqlalchemy.orm import Session, sessionmaker

    session = sessionmaker(bind=engine, class_=Session)()
    session.add(make_site())
    session.add(make_sensor())
    session.commit()
    session.add(make_threshold(threshold_type="NORMAL", fg_label_eligible=True))
    with pytest.raises(IntegrityError):
        session.commit()
    session.rollback()
    session.add(make_threshold("thr-ok", threshold_type="NORMAL", fg_label_eligible=False))
    session.commit()


def test_missing_observation_stored_with_null_value() -> None:
    engine = make_engine()
    from sqlalchemy.orm import Session, sessionmaker

    session = sessionmaker(bind=engine, class_=Session)()
    session.add(make_site())
    session.add(make_sensor())
    session.add(make_observation(value=None))
    session.commit()
    row = session.query(models.Observation).one()
    assert row.value is None
    assert row.usable is False
    assert "VALUE_MISSING_SENTINEL" in row.quality_flags


def test_foreign_keys_present() -> None:
    assert set(Base.metadata.tables) >= set(models.TABLES_IN_ORDER)
    sensors = Base.metadata.tables["sensors"]
    fk_targets = {fk.target_fullname for fk in sensors.foreign_keys}
    assert "sites.fg_site_id" in fk_targets
    obs = Base.metadata.tables["observations"]
    assert "sensors.fg_sensor_id" in {fk.target_fullname for fk in obs.foreign_keys}


def test_ineligible_reference_threshold_rejected() -> None:
    engine = make_engine()
    from sqlalchemy.orm import Session, sessionmaker

    session = sessionmaker(bind=engine, class_=Session)()
    session.add(make_site())
    session.add(make_sensor())
    session.commit()
    session.add(make_threshold("thr-bad", threshold_type="WASPADA", fg_label_eligible=False))
    with pytest.raises(IntegrityError):
        session.commit()


def test_predicted_label_domain_and_coordinate_ranges() -> None:
    from floodguard.backend.models import Prediction

    engine = make_engine()
    from sqlalchemy.orm import Session, sessionmaker

    session = sessionmaker(bind=engine, class_=Session)()
    session.add(make_site())
    session.add(make_sensor())
    session.commit()
    bad_label = Prediction(
        prediction_id="p-bad",
        fg_sensor_id="sensor-wl-001",
        fg_site_id="site-001",
        horizon_minutes=30,
        prediction_origin_utc=make_observation().observation_time_utc,
        target_time_utc=make_observation().observation_time_utc,
        predicted_value=1.0,
        predicted_label=5,
        predicted_probability=None,
        model_family="persistence",
        run_id="persistence",
        evidence_level="SYNTHETIC_SOFTWARE_VALIDATION",
        created_at=make_observation().observation_time_utc,
        lineage={},
    )
    session.add(bad_label)
    with pytest.raises(IntegrityError):
        session.commit()
    session.rollback()
    session.add(make_site(site_id="bad-geo", latitude=91.0))
    with pytest.raises(IntegrityError):
        session.commit()
