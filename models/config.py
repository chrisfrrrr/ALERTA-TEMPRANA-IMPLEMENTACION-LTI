from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any


@dataclass(slots=True)
class RiskConfig:
    """Reglas institucionales configurables para el motor de riesgo."""

    course_weeks: int = 5

    activity_low_min: float = 80.0
    activity_moderate_min: float = 50.0

    grade_low_min: float = 70.0
    grade_moderate_min: float = 60.0

    access_low_min: int = 3
    access_moderate_min: int = 1
    inactivity_moderate_hours: float = 48.0
    inactivity_high_hours: float = 96.0

    response_low_hours: float = 48.0
    response_moderate_hours: float = 72.0
    response_high_hours: float = 120.0

    late_moderate_min: int = 1
    late_high_min: int = 4
    no_submission_high_weeks: int = 2

    referral_cooldown_days: int = 14

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> "RiskConfig":
        if not data:
            return cls()
        allowed = cls.__dataclass_fields__.keys()
        clean = {key: value for key, value in data.items() if key in allowed and value is not None}
        return cls(**clean)
