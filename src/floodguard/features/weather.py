"""Weather and forecast feature engineering for FloodGuard Penang.

Point-in-time extraction of data.gov.my weather forecast signals.
Covers:
- Phase 4 Task 5: Weather/forecast features (min/max/range temperature, rain indicators)

Point-in-Time Availability and Safety Rules:
- Forecasts must have been retrieved at or before prediction origin t (retrieved_at <= t).
- Matched by station district / location mapping.
- If no forecast is available for origin t, features return None (never synthetic defaults).
- Acknowledges that data.gov.my forecast is daily-resolution text/temperatures rather than
  5-minute rainfall rates.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any, Final

from floodguard.features.registry import (
    REGISTRY,
    FeatureDefinition,
    FeatureFamily,
    LeakageClassification,
)

DECIMALS = 6
RAIN_KEYWORDS: Final[tuple[str, ...]] = (
    "hujan",
    "ribut",
    "petir",
    "rain",
    "thunderstorm",
    "showers",
)
THUNDERSTORM_KEYWORDS: Final[tuple[str, ...]] = ("ribut petir", "thunderstorm", "petir")


@dataclass(frozen=True)
class WeatherForecastRecord:
    """A point-in-time verified forecast record."""

    location_id: str
    location_name: str
    forecast_date: date
    retrieved_at: datetime
    min_temp_c: float | None
    max_temp_c: float | None
    summary_forecast: str | None


def _r(x: float | None) -> float | None:
    if x is None:
        return None
    return round(float(x), DECIMALS) + 0.0


def register_weather_features() -> list[FeatureDefinition]:
    """Register weather/forecast features into the global registry."""
    defs: list[FeatureDefinition] = [
        FeatureDefinition(
            name="fc_temp_min_c",
            family=FeatureFamily.WEATHER_FORECAST,
            description="Forecast minimum temperature for the day in °C",
            measurement_type="FORECAST_TEMPERATURE",
            unit="deg_c",
            lookback_minutes=0,
            min_coverage_ratio=1.0,
            null_semantics="Null if no forecast available at origin t",
            point_in_time_semantics="Latest forecast retrieved at or before t for origin date",
            leakage_classification=LeakageClassification.STRICT_POINT_IN_TIME,
        ),
        FeatureDefinition(
            name="fc_temp_max_c",
            family=FeatureFamily.WEATHER_FORECAST,
            description="Forecast maximum temperature for the day in °C",
            measurement_type="FORECAST_TEMPERATURE",
            unit="deg_c",
            lookback_minutes=0,
            min_coverage_ratio=1.0,
            null_semantics="Null if no forecast available at origin t",
            point_in_time_semantics="Latest forecast retrieved at or before t for origin date",
            leakage_classification=LeakageClassification.STRICT_POINT_IN_TIME,
        ),
        FeatureDefinition(
            name="fc_temp_range_c",
            family=FeatureFamily.WEATHER_FORECAST,
            description="Forecast temperature diurnal range (max - min) in °C",
            measurement_type="FORECAST_TEMPERATURE",
            unit="deg_c",
            lookback_minutes=0,
            min_coverage_ratio=1.0,
            null_semantics="Null if min or max temperature is unavailable",
            point_in_time_semantics="Latest forecast retrieved at or before t for origin date",
            leakage_classification=LeakageClassification.STRICT_POINT_IN_TIME,
        ),
        FeatureDefinition(
            name="fc_is_rain_forecast",
            family=FeatureFamily.WEATHER_FORECAST,
            description="Binary indicator whether daily forecast predicts rain (1/0)",
            measurement_type="FORECAST_CATEGORY",
            unit="unitless",
            lookback_minutes=0,
            min_coverage_ratio=1.0,
            null_semantics="Null if summary forecast text is unavailable",
            point_in_time_semantics="Latest forecast retrieved at or before t for origin date",
            leakage_classification=LeakageClassification.STRICT_POINT_IN_TIME,
        ),
        FeatureDefinition(
            name="fc_is_thunderstorm_forecast",
            family=FeatureFamily.WEATHER_FORECAST,
            description="Binary indicator whether daily forecast predicts thunderstorms (1/0)",
            measurement_type="FORECAST_CATEGORY",
            unit="unitless",
            lookback_minutes=0,
            min_coverage_ratio=1.0,
            null_semantics="Null if summary forecast text is unavailable",
            point_in_time_semantics="Latest forecast retrieved at or before t for origin date",
            leakage_classification=LeakageClassification.STRICT_POINT_IN_TIME,
        ),
    ]

    for d in defs:
        if not REGISTRY.contains(d.name):
            REGISTRY.register(d)
    return defs


# Register default definitions
register_weather_features()


def compute_weather_features_for_origin(
    origin_time: datetime,
    origin_district: str | None,
    forecast_records: Sequence[WeatherForecastRecord],
) -> dict[str, Any]:
    """Extract forecast features available at or before origin_time for origin's date and district.

    LEAKAGE GUARD: Only forecast records with retrieved_at <= origin_time are eligible.
    """
    origin_date = origin_time.date()
    eligible = [
        fc
        for fc in forecast_records
        if fc.retrieved_at <= origin_time
        and fc.forecast_date == origin_date
        and (
            origin_district is None
            or fc.location_name.lower() in origin_district.lower()
            or origin_district.lower() in fc.location_name.lower()
        )
    ]

    if not eligible:
        # Fallback: any Penang location forecast retrieved at or before origin_time for origin_date
        eligible = [
            fc
            for fc in forecast_records
            if fc.retrieved_at <= origin_time and fc.forecast_date == origin_date
        ]

    if not eligible:
        return {
            "fc_temp_min_c": None,
            "fc_temp_max_c": None,
            "fc_temp_range_c": None,
            "fc_is_rain_forecast": None,
            "fc_is_thunderstorm_forecast": None,
        }

    latest_fc = max(eligible, key=lambda f: f.retrieved_at)

    min_t = latest_fc.min_temp_c
    max_t = latest_fc.max_temp_c
    rng_t = (max_t - min_t) if (min_t is not None and max_t is not None) else None

    summary = (latest_fc.summary_forecast or "").lower()
    is_rain = 1 if any(k in summary for k in RAIN_KEYWORDS) else (0 if summary else None)
    is_ts = 1 if any(k in summary for k in THUNDERSTORM_KEYWORDS) else (0 if summary else None)

    return {
        "fc_temp_min_c": _r(min_t),
        "fc_temp_max_c": _r(max_t),
        "fc_temp_range_c": _r(rng_t),
        "fc_is_rain_forecast": is_rain,
        "fc_is_thunderstorm_forecast": is_ts,
    }
