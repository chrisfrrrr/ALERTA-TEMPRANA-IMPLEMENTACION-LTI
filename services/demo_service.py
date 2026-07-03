from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from models.config import RiskConfig
from services.risk_engine import (
    build_reasons,
    evaluate_access,
    evaluate_activity,
    evaluate_communication,
    evaluate_grade,
    evaluate_punctuality,
    expected_activities,
    intervention_priority,
    overall_risk,
    weekly_distribution,
)
from utils.data_cleaning import load_wellbeing_csv


def demo_courses() -> list[dict[str, Any]]:
    return [
        {
            "id": 91001,
            "name": "Administración I — Demostración",
            "course_code": "AVE-ADM-I",
            "start_at": datetime.now(timezone.utc).date().replace(day=1).isoformat(),
            "end_at": None,
            "total_students": 40,
        },
        {
            "id": 91002,
            "name": "Propósito Personal y Profesional — Demostración",
            "course_code": "AVE-PPP",
            "start_at": datetime.now(timezone.utc).date().replace(day=1).isoformat(),
            "end_at": None,
            "total_students": 40,
        },
    ]


def demo_sections(course_id: int | str) -> list[dict[str, Any]]:
    return [
        {"id": int(course_id) * 10 + 1, "name": "Sección A", "total_students": 20},
        {"id": int(course_id) * 10 + 2, "name": "Sección B", "total_students": 20},
    ]


def generate_demo_analysis(
    *,
    course: dict[str, Any],
    section_id: int | str | None,
    section_name: str,
    week: int,
    analysis_date: date,
    config: RiskConfig | None = None,
    wellbeing_path: str | Path | None = None,
) -> tuple[pd.DataFrame, dict[str, Any], dict[str, Any]]:
    config = config or RiskConfig()
    path = wellbeing_path or Path(__file__).resolve().parents[1] / "data" / "bienestar_base.csv"
    wellbeing = load_wellbeing_csv(path).head(40).copy()
    if section_name == "Sección B":
        wellbeing = wellbeing.iloc[20:40].copy()
    elif section_name == "Sección A":
        wellbeing = wellbeing.iloc[:20].copy()

    rng = np.random.default_rng(seed=20260615 + int(week) + int(course["id"]))
    total_activities = 15
    expected_count = expected_activities(total_activities, week, config.course_weeks)
    activity_names = [f"Actividad {index:02d}" for index in range(1, total_activities + 1)]
    expected_names = activity_names[:expected_count]

    rows: list[dict[str, Any]] = []
    details: dict[str, Any] = {}
    for index, student in wellbeing.reset_index(drop=True).iterrows():
        profile = index % 10
        if profile in {0, 1, 2, 3}:
            completed = max(expected_count, int(round(expected_count * rng.uniform(0.85, 1.25))))
            average = rng.uniform(72, 96)
            sessions = int(rng.integers(3, 7))
            inactivity = rng.uniform(2, 30)
            late = int(rng.integers(0, 2))
            response_hours = rng.uniform(4, 42)
        elif profile in {4, 5, 6}:
            completed = int(round(expected_count * rng.uniform(0.52, 0.78)))
            average = rng.uniform(60, 69.8)
            sessions = int(rng.integers(1, 3))
            inactivity = rng.uniform(48, 88)
            late = int(rng.integers(1, 4))
            response_hours = rng.uniform(49, 82)
        else:
            completed = int(round(expected_count * rng.uniform(0.0, 0.45)))
            average = rng.uniform(35, 59)
            sessions = int(rng.integers(0, 2))
            inactivity = rng.uniform(98, 190)
            late = int(rng.integers(2, 6))
            response_hours = None

        completed = max(0, min(total_activities, completed))
        completed_expected = min(completed, expected_count)
        pending_count = max(0, expected_count - completed_expected)
        pending_names = expected_names[completed_expected:]

        activity_indicator = evaluate_activity(completed, expected_count, config)
        grade_indicator = evaluate_grade(float(average), config)
        punctuality_indicator = evaluate_punctuality(late, completed_expected, 0, config)
        access_indicator = evaluate_access(sessions, inactivity, config)
        if profile >= 7:
            communication_indicator = evaluate_communication(None, inactivity, True, config)
        else:
            communication_indicator = evaluate_communication(float(response_hours), None, True, config)
        indicators = [
            activity_indicator,
            grade_indicator,
            punctuality_indicator,
            access_indicator,
            communication_indicator,
        ]
        overall = overall_risk(indicators)
        priority = intervention_priority(indicators, overall)
        reasons = build_reasons(indicators, pending_names)

        canvas_user_id = str(600000 + int(student["carne"]))
        row = {
            "canvas_user_id": canvas_user_id,
            "carne": str(student["carne"]),
            "student_name": student["nombre_completo"],
            "email": f"cas{student['carne']}@uvg.edu.gt",
            "career": "Licenciatura AVE",
            "avatar_url": None,
            "course_id": str(course["id"]),
            "course_name": course["name"],
            "section_id": str(section_id or ""),
            "section_name": section_name or "Todas las secciones",
            "week_number": week,
            "total_weeks": config.course_weeks,
            "total_activities": total_activities,
            "expected_activities": expected_count,
            "completed_activities": completed,
            "completed_expected": completed_expected,
            "pending_count": pending_count,
            "late_count": late,
            "early_count": max(0, completed_expected - late - 1),
            "completion_percentage": round(min(100.0, completed / expected_count * 100.0), 2),
            "average_grade": round(float(average), 2),
            "weekly_sessions": sessions,
            "inactivity_hours": round(float(inactivity), 1),
            "last_activity_at": (datetime.now(timezone.utc) - timedelta(hours=float(inactivity))).isoformat(),
            "activity_risk": activity_indicator.risk,
            "grade_risk": grade_indicator.risk,
            "punctuality_risk": punctuality_indicator.risk,
            "access_risk": access_indicator.risk,
            "communication_risk": communication_indicator.risk,
            "overall_risk": overall,
            "intervention_priority": priority,
            "pending_assignments": pending_names,
            "reasons": reasons,
            "evolution": ["Primera medición", "Mejorando", "Sin cambio", "Empeorando"][index % 4],
            "analysis_cutoff": datetime.combine(analysis_date, datetime.max.time()).replace(tzinfo=timezone.utc).isoformat(),
            "advisor_name": student["asesor_bienestar"],
            "asesor_bienestar": student["asesor_bienestar"],
            "estado_bienestar": student["estado_bienestar"],
            "etapa_bienestar": student["etapa_bienestar"],
            "solicitudes_particulares": student["solicitudes_particulares"],
            "riesgo_ciclo_regular": student["riesgo_ciclo_regular"],
            "canvas_page_views_available": True,
        }
        rows.append(row)

        assignments = []
        for activity_index, activity_name in enumerate(activity_names, start=1):
            completed_activity = activity_index <= completed
            assignments.append(
                {
                    "id": str(1000 + activity_index),
                    "actividad": activity_name,
                    "semana_asignada": next(
                        week_number
                        for week_number in range(1, config.course_weeks + 1)
                        if activity_index <= expected_activities(total_activities, week_number, config.course_weeks)
                    ),
                    "esperada_a_la_fecha": activity_index <= expected_count,
                    "completada": completed_activity,
                    "tardia": completed_activity and activity_index <= late,
                    "fecha_limite": (analysis_date + timedelta(days=(activity_index // 3) * 2)).isoformat(),
                    "fecha_entrega": analysis_date.isoformat() if completed_activity else None,
                    "puntaje": round(float(rng.uniform(6, 10)), 1) if completed_activity else None,
                    "puntos_posibles": 10,
                }
            )
        details[canvas_user_id] = {
            "student": row,
            "indicators": [indicator.as_dict() for indicator in indicators],
            "assignments": assignments,
            "latest_message": None,
        }

    dataframe = pd.DataFrame(rows)
    risk_sort = pd.Categorical(dataframe["overall_risk"], categories=["Alto", "Moderado", "Bajo"], ordered=True)
    dataframe = dataframe.assign(_risk_sort=risk_sort).sort_values(
        ["_risk_sort", "completion_percentage", "student_name"]
    ).drop(columns="_risk_sort").reset_index(drop=True)
    diagnostics = {
        "course_id": str(course["id"]),
        "course_name": course["name"],
        "students": len(dataframe),
        "assignments_raw": total_activities,
        "assignments_analyzed": total_activities,
        "expected_activities": expected_count,
        "weekly_distribution": weekly_distribution(total_activities, config.course_weeks),
        "analysis_week": week,
        "window_start": (analysis_date - timedelta(days=7)).isoformat(),
        "window_end": analysis_date.isoformat(),
        "page_view_errors": {},
        "demo": True,
    }
    return dataframe, details, diagnostics
