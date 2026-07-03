from __future__ import annotations

from datetime import date, datetime, time, timezone
import math
from typing import Any

from services.canvas_service import CanvasService
from utils.dates import hours_between, parse_datetime




def _available_number(value: Any) -> bool:
    if value is None:
        return False
    try:
        return not math.isnan(float(value))
    except (TypeError, ValueError):
        return False


DEFAULT_SUBJECTS = {
    "Bajo": "Seguimiento a tu progreso académico",
    "Moderado": "Acompañamiento y seguimiento de tu avance",
    "Alto": "Seguimiento académico prioritario",
}


def _pending_text(row: dict[str, Any]) -> str:
    pending = row.get("pending_assignments") or []
    if not pending:
        return ""
    if isinstance(pending, str):
        return pending
    quoted = ", ".join(f'“{item}”' for item in pending[:6])
    suffix = "" if len(pending) <= 6 else f" y {len(pending) - 6} actividad(es) adicional(es)"
    return quoted + suffix


def generate_message(
    row: dict[str, Any],
    *,
    academic_advisor: str,
    appointment_date: date | None = None,
    appointment_time: time | None = None,
) -> tuple[str, str]:
    risk = str(row.get("overall_risk") or "Moderado")
    name = str(row.get("student_name") or "estudiante").split()[0]
    course = row.get("course_name") or "el curso"
    week = row.get("week_number") or ""
    expected = row.get("expected_activities") or 0
    completed = row.get("completed_activities") or 0
    pending = _pending_text(row)
    average = row.get("average_grade")
    inactivity = row.get("inactivity_hours")

    subject = DEFAULT_SUBJECTS.get(risk, DEFAULT_SUBJECTS["Moderado"])
    if risk == "Bajo":
        body = (
            f"Estimado(a) {name}:\n\n"
            f"Espero que te encuentres muy bien. Al revisar tu avance al cierre de la semana {week} "
            f"del curso {course}, observé que mantienes un progreso favorable. Actualmente registras "
            f"{completed} actividades completadas frente a una meta acumulada de {expected}.\n\n"
            "Quiero felicitarte por la constancia que has demostrado y animarte a continuar con este ritmo. "
            "Recuerda que cuentas con mi acompañamiento ante cualquier duda o dificultad académica.\n\n"
            f"Saludos cordiales,\n{academic_advisor}\nAsesor AVE"
        )
    elif risk == "Alto":
        appointment = ""
        if appointment_date and appointment_time:
            appointment = (
                f"\n\nHe reservado un espacio de atención para el día "
                f"{appointment_date.strftime('%d/%m/%Y')} a las {appointment_time.strftime('%H:%M')} horas. "
                "Por favor, confirma tu disponibilidad o indícame un horario alternativo."
            )
        findings = [
            f"registras {completed} de las {expected} actividades esperadas al cierre de la semana {week}"
        ]
        if pending:
            findings.append(f"se encuentran pendientes {pending}")
        if _available_number(average):
            findings.append(f"tu promedio actual es de {float(average):.2f} %")
        if _available_number(inactivity) and float(inactivity) >= 48:
            findings.append(f"tu última actividad en Canvas fue hace aproximadamente {float(inactivity):.0f} horas")
        detail = "; ".join(findings)
        body = (
            f"Estimado(a) {name}:\n\n"
            f"Espero que te encuentres bien. Al revisar tu avance en el curso {course}, identifiqué señales "
            f"que requieren atención prioritaria: {detail}.\n\n"
            "Mi intención es acompañarte para evitar que esta situación continúe afectando tu proceso académico. "
            "Agradeceré que respondas este mensaje para que podamos establecer juntos un plan de recuperación."
            f"{appointment}\n\n"
            f"Saludos cordiales,\n{academic_advisor}\nAsesor AVE"
        )
    else:
        findings = [
            f"has completado {completed} de las {expected} actividades esperadas al cierre de la semana {week}"
        ]
        if pending:
            findings.append(f"se encuentran pendientes {pending}")
        if _available_number(average):
            findings.append(f"tu promedio actual es de {float(average):.2f} %")
        detail = "; ".join(findings)
        body = (
            f"Estimado(a) {name}:\n\n"
            f"Espero que te encuentres bien. Al revisar tu avance en el curso {course}, observé algunos aspectos "
            f"que podrían afectar tu desempeño: {detail}.\n\n"
            "Quisiera conocer si existe alguna dificultad académica o personal que esté influyendo en tu progreso. "
            "Por favor, responde este mensaje para que podamos identificar una alternativa de apoyo y seguimiento.\n\n"
            f"Saludos cordiales,\n{academic_advisor}\nAsesor AVE"
        )
    return subject, body


def extract_conversation_response(
    conversation: dict[str, Any],
    *,
    sender_canvas_user_id: str,
    sent_at: str,
) -> dict[str, Any] | None:
    """Identifica la primera respuesta posterior al envío que no sea del asesor."""
    sent_dt = parse_datetime(sent_at)
    if not sent_dt:
        return None
    messages = conversation.get("messages") or []
    candidates = []
    for message in messages:
        author_id = str(message.get("author_id") or "")
        created_at = parse_datetime(message.get("created_at"))
        if not created_at or created_at <= sent_dt:
            continue
        if author_id == str(sender_canvas_user_id):
            continue
        candidates.append((created_at, message))
    if not candidates:
        return None
    created_at, message = min(candidates, key=lambda item: item[0])
    return {
        "responded_at": created_at.isoformat(),
        "response_hours": hours_between(sent_dt, created_at),
        "response_excerpt": str(message.get("body") or "")[:500],
    }


def send_personalized_message(
    canvas: CanvasService,
    row: dict[str, Any],
    subject: str,
    body: str,
) -> dict[str, Any]:
    conversations = canvas.send_message([row["canvas_user_id"]], subject, body)
    conversation = conversations[0] if conversations else {}
    now = datetime.now(timezone.utc).isoformat()
    return {
        "canvas_user_id": str(row.get("canvas_user_id") or ""),
        "carne": str(row.get("carne") or ""),
        "student_name": row.get("student_name"),
        "advisor_name": row.get("asesor_bienestar") or row.get("advisor_name"),
        "course_id": str(row.get("course_id") or ""),
        "course_name": row.get("course_name"),
        "risk_level": row.get("overall_risk"),
        "subject": subject,
        "body": body,
        "sent_at": now,
        "status": "sent",
        "canvas_conversation_id": str(conversation.get("id") or "") or None,
    }
