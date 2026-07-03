from __future__ import annotations

from datetime import date, datetime, timezone
import math
from typing import Any

from dateutil import parser


def parse_datetime(value: Any) -> datetime | None:
    if value in (None, "", "null"):
        return None
    if isinstance(value, datetime):
        dt = value
    elif isinstance(value, date):
        dt = datetime.combine(value, datetime.min.time())
    else:
        try:
            dt = parser.isoparse(str(value))
        except (TypeError, ValueError, OverflowError):
            return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def iso_or_none(value: Any) -> str | None:
    dt = parse_datetime(value)
    return dt.isoformat() if dt else None


def hours_between(start: Any, end: Any | None = None) -> float | None:
    start_dt = parse_datetime(start)
    end_dt = parse_datetime(end) or datetime.now(timezone.utc)
    if not start_dt:
        return None
    return max(0.0, (end_dt - start_dt).total_seconds() / 3600.0)


def format_hours(hours: float | None) -> str:
    if hours is None or (isinstance(hours, float) and math.isnan(hours)):
        return "Sin datos"
    if hours < 24:
        return f"{hours:.0f} h"
    return f"{hours / 24:.1f} días"
