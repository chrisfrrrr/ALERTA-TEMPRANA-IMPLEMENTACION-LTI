from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

from models.config import RiskConfig


RISK_ORDER = {"Sin datos": -1, "Bajo": 0, "Moderado": 1, "Alto": 2}


@dataclass(slots=True)
class IndicatorResult:
    name: str
    risk: str
    value: Any
    detail: str
    available: bool = True

    def as_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "risk": self.risk,
            "value": self.value,
            "detail": self.detail,
            "available": self.available,
        }


def expected_activities(total_activities: int, week: int, total_weeks: int = 5) -> int:
    """Meta acumulada al cierre de la semana, usando redondeo hacia arriba."""
    if total_activities <= 0:
        return 0
    safe_weeks = max(1, int(total_weeks))
    safe_week = min(max(1, int(week)), safe_weeks)
    return min(total_activities, math.ceil(total_activities * safe_week / safe_weeks))


def weekly_distribution(total_activities: int, total_weeks: int = 5) -> list[int]:
    """Cantidad incremental esperada por semana; siempre suma el total."""
    cumulative = [expected_activities(total_activities, week, total_weeks) for week in range(1, total_weeks + 1)]
    previous = 0
    distribution: list[int] = []
    for value in cumulative:
        distribution.append(value - previous)
        previous = value
    return distribution


def evaluate_activity(
    completed: int,
    expected: int,
    config: RiskConfig,
) -> IndicatorResult:
    if expected <= 0:
        return IndicatorResult(
            "Actividades",
            "Sin datos",
            None,
            "El curso no tiene actividades válidas para analizar.",
            available=False,
        )
    percent = max(0.0, completed / expected * 100.0)
    displayed = min(percent, 100.0)
    gap = completed - expected
    if percent >= config.activity_low_min:
        risk = "Bajo"
    elif percent >= config.activity_moderate_min:
        risk = "Moderado"
    else:
        risk = "Alto"

    if gap >= 0:
        extra = f"Cumple la meta acumulada; avance de {completed}/{expected}."
    else:
        extra = f"Presenta una brecha de {abs(gap)} actividad(es); avance de {completed}/{expected}."
    return IndicatorResult("Actividades", risk, round(displayed, 2), extra)


def evaluate_grade(average: float | None, config: RiskConfig, trend_delta: float | None = None) -> IndicatorResult:
    if average is None:
        return IndicatorResult(
            "Calificaciones",
            "Sin datos",
            None,
            "No hay una calificación disponible en Canvas.",
            available=False,
        )
    if average >= config.grade_low_min:
        risk = "Bajo"
    elif average >= config.grade_moderate_min:
        risk = "Moderado"
    else:
        risk = "Alto"

    trend = ""
    if trend_delta is not None:
        if trend_delta <= -5:
            trend = f" Tendencia descendente de {abs(trend_delta):.1f} puntos."
            risk = "Alto" if average < config.grade_low_min else max_risk(risk, "Moderado")
        elif trend_delta >= 5:
            trend = f" Mejora de {trend_delta:.1f} puntos."
    return IndicatorResult("Calificaciones", risk, round(float(average), 2), f"Promedio actual: {average:.2f} %.{trend}")


def evaluate_punctuality(
    late_count: int,
    completed_expected: int,
    consecutive_weeks_without_submissions: int,
    config: RiskConfig,
) -> IndicatorResult:
    if consecutive_weeks_without_submissions >= config.no_submission_high_weeks:
        return IndicatorResult(
            "Puntualidad",
            "Alto",
            late_count,
            f"No registra entregas durante {consecutive_weeks_without_submissions} semanas consecutivas.",
        )
    if completed_expected <= 0:
        return IndicatorResult(
            "Puntualidad",
            "Alto",
            late_count,
            "No registra entregas dentro del avance esperado.",
        )
    if late_count <= 0:
        risk = "Bajo"
        detail = "Las actividades completadas fueron entregadas a tiempo o con anticipación."
    elif late_count >= config.late_high_min:
        risk = "Alto"
        detail = f"Registra {late_count} entregas tardías."
    else:
        risk = "Moderado"
        detail = f"Registra {late_count} entrega(s) tardía(s)."
    return IndicatorResult("Puntualidad", risk, late_count, detail)


def evaluate_access(
    weekly_sessions: int | None,
    inactivity_hours: float | None,
    config: RiskConfig,
) -> IndicatorResult:
    if weekly_sessions is not None:
        if weekly_sessions >= config.access_low_min:
            risk = "Bajo"
        elif weekly_sessions >= config.access_moderate_min:
            risk = "Moderado"
        elif inactivity_hours is not None and inactivity_hours >= config.inactivity_high_hours:
            risk = "Alto"
        else:
            risk = "Moderado"
        inactivity_text = ""
        if inactivity_hours is not None:
            inactivity_text = f" Última actividad hace {inactivity_hours:.0f} horas."
        return IndicatorResult(
            "Actividad en Canvas",
            risk,
            weekly_sessions,
            f"Se estimaron {weekly_sessions} sesión(es) durante la semana.{inactivity_text}",
        )

    if inactivity_hours is None:
        return IndicatorResult(
            "Actividad en Canvas",
            "Sin datos",
            None,
            "El token no permitió consultar sesiones ni última actividad.",
            available=False,
        )
    if inactivity_hours >= config.inactivity_high_hours:
        risk = "Alto"
    elif inactivity_hours >= config.inactivity_moderate_hours:
        risk = "Moderado"
    else:
        risk = "Bajo"
    return IndicatorResult(
        "Actividad en Canvas",
        risk,
        round(inactivity_hours, 1),
        f"No fue posible contar sesiones; la última actividad fue hace {inactivity_hours:.0f} horas.",
    )


def evaluate_communication(
    response_hours: float | None,
    pending_hours: float | None,
    has_message: bool,
    config: RiskConfig,
) -> IndicatorResult:
    if not has_message:
        return IndicatorResult(
            "Comunicación",
            "Sin datos",
            None,
            "Aún no existe un mensaje de seguimiento registrado.",
            available=False,
        )
    if response_hours is not None:
        if response_hours <= config.response_low_hours:
            risk = "Bajo"
        elif response_hours <= config.response_moderate_hours:
            risk = "Moderado"
        else:
            risk = "Alto" if response_hours >= config.response_high_hours else "Moderado"
        return IndicatorResult(
            "Comunicación",
            risk,
            round(response_hours, 1),
            f"El estudiante respondió en {response_hours:.1f} horas.",
        )

    if pending_hours is None:
        return IndicatorResult(
            "Comunicación",
            "Moderado",
            None,
            "El mensaje está pendiente de respuesta.",
        )
    risk = "Alto" if pending_hours >= config.response_high_hours else "Moderado"
    return IndicatorResult(
        "Comunicación",
        risk,
        round(pending_hours, 1),
        f"El mensaje lleva {pending_hours:.1f} horas sin respuesta.",
    )


def max_risk(*risks: str) -> str:
    valid = [risk for risk in risks if risk in RISK_ORDER]
    if not valid:
        return "Sin datos"
    return max(valid, key=lambda risk: RISK_ORDER[risk])


def overall_risk(indicators: list[IndicatorResult]) -> str:
    available = [indicator.risk for indicator in indicators if indicator.available]
    if not available:
        return "Sin datos"
    return max_risk(*available)


def intervention_priority(indicators: list[IndicatorResult], overall: str) -> str:
    high_count = sum(1 for indicator in indicators if indicator.available and indicator.risk == "Alto")
    moderate_count = sum(1 for indicator in indicators if indicator.available and indicator.risk == "Moderado")
    if overall == "Alto" and high_count >= 2:
        return "Urgente"
    if overall == "Alto":
        return "Prioritaria"
    if overall == "Moderado" or moderate_count >= 1:
        return "Seguimiento"
    if overall == "Bajo":
        return "Preventiva"
    return "Sin clasificar"


def build_reasons(
    indicators: list[IndicatorResult],
    pending_assignments: list[str] | None = None,
) -> list[str]:
    reasons: list[str] = []
    for indicator in indicators:
        if indicator.available and indicator.risk in {"Moderado", "Alto"}:
            reasons.append(indicator.detail)
    if pending_assignments:
        names = ", ".join(f'“{name}”' for name in pending_assignments[:8])
        suffix = "" if len(pending_assignments) <= 8 else f" y {len(pending_assignments) - 8} más"
        reasons.append(f"Actividades esperadas pendientes: {names}{suffix}.")
    return reasons or ["Mantiene los indicadores dentro de los parámetros esperados."]
