from __future__ import annotations

from datetime import date, datetime, time

import pandas as pd
import streamlit as st

from components.ui import empty_state, page_header
from services.canvas_service import CanvasAPIError, CanvasService
from services.database_service import DatabaseError
from services.auth_service import current_actor, get_valid_canvas_token, load_oauth_config
from services.messaging_service import (
    extract_conversation_response,
    generate_message,
    send_personalized_message,
)
from services.runtime import get_database


page_header(
    "Mensajería desde Canvas",
    "Prepare mensajes cálidos y profesionales según el nivel de riesgo, envíelos por la bandeja de Canvas y registre el seguimiento.",
)

df = st.session_state.get("analysis_df")
if df is None or df.empty:
    empty_state("No hay destinatarios", "Ejecute un análisis antes de utilizar la mensajería.")
    st.stop()

academic_advisor = st.text_input("Firma del asesor", value=st.session_state.get("academic_advisor", "Ing. Christian Pocol"))
st.session_state.academic_advisor = academic_advisor

risk_filter = st.multiselect("Filtrar por riesgo", ["Bajo", "Moderado", "Alto"], default=["Moderado", "Alto"])
eligible = df[df["overall_risk"].isin(risk_filter)].copy() if risk_filter else df.copy()
option_map = {f"{row.student_name} · {row.carne} · {row.overall_risk}": str(row.canvas_user_id) for row in eligible.itertuples()}
preselected_ids = set(str(value) for value in st.session_state.get("preselected_message_students", []))
default_labels = [label for label, value in option_map.items() if value in preselected_ids]
selected_labels = st.multiselect("Estudiantes destinatarios", list(option_map.keys()), default=default_labels)
selected_ids = [option_map[label] for label in selected_labels]

has_high = not eligible[eligible["canvas_user_id"].astype(str).isin(selected_ids) & (eligible["overall_risk"] == "Alto")].empty
appointment_date = None
appointment_time = None
if has_high:
    st.markdown("#### Espacio de atención para casos de riesgo alto")
    c1, c2 = st.columns(2)
    with c1:
        appointment_date = st.date_input("Día de atención", value=date.today())
    with c2:
        appointment_time = st.time_input("Horario", value=time(15, 0))

if not selected_ids:
    st.info("Seleccione al menos un estudiante para generar la vista previa.")
else:
    first_row = eligible[eligible["canvas_user_id"].astype(str) == selected_ids[0]].iloc[0].to_dict()
    default_subject, default_body = generate_message(
        first_row,
        academic_advisor=academic_advisor,
        appointment_date=appointment_date,
        appointment_time=appointment_time,
    )
    st.markdown("#### Vista previa")
    subject = st.text_input("Asunto", value=default_subject)
    automatic = st.toggle("Personalizar automáticamente cada mensaje con los datos del estudiante", value=True)
    if automatic:
        st.text_area("Mensaje del primer destinatario", value=default_body, height=330, disabled=True)
        st.caption("Cada destinatario recibirá un texto equivalente con su nombre, curso, avance, pendientes y horario aplicable.")
    else:
        custom_body = st.text_area(
            "Mensaje personalizado",
            value=default_body,
            height=330,
            help="Este mismo texto se enviará a todos los destinatarios seleccionados.",
        )

    mode_text = "simular" if st.session_state.get("demo_mode", True) else "enviar"
    confirmation = st.checkbox(f"Confirmo que revisé el contenido y deseo {mode_text} {len(selected_ids)} mensaje(s).")
    if st.button("Enviar y registrar mensajes", type="primary", width="stretch", disabled=not confirmation):
        db = get_database()
        results = []
        failures = []
        canvas = None
        if not st.session_state.get("demo_mode", True):
            oauth_config = load_oauth_config()
            token = get_valid_canvas_token(oauth_config)
            canvas = CanvasService(st.session_state.get("canvas_url", oauth_config.canvas_url), token)

        progress = st.progress(0, text="Enviando mensajes...")
        for index, user_id in enumerate(selected_ids, start=1):
            row = eligible[eligible["canvas_user_id"].astype(str) == user_id].iloc[0].to_dict()
            auto_subject, auto_body = generate_message(
                row,
                academic_advisor=academic_advisor,
                appointment_date=appointment_date,
                appointment_time=appointment_time,
            )
            final_subject = subject if len(selected_ids) == 1 else auto_subject
            final_body = auto_body if automatic else custom_body
            try:
                if st.session_state.get("demo_mode", True):
                    payload = {
                        "canvas_user_id": user_id,
                        "carne": str(row.get("carne")),
                        "student_name": row.get("student_name"),
                        "advisor_name": row.get("asesor_bienestar") or row.get("advisor_name"),
                        "course_id": str(row.get("course_id")),
                        "course_name": row.get("course_name"),
                        "risk_level": row.get("overall_risk"),
                        "subject": final_subject,
                        "body": final_body,
                        "sent_at": datetime.now().astimezone().isoformat(),
                        "status": "sent-demo",
                        "canvas_conversation_id": f"demo-{user_id}-{index}",
                    }
                else:
                    payload = send_personalized_message(canvas, row, final_subject, final_body)
                if db.connected:
                    message_id = db.save_message(payload)
                    db.log_audit(
                        action="message_sent",
                        entity_type="message",
                        entity_id=message_id,
                        actor=current_actor(),
                        payload={
                            "canvas_user_id": str(user_id),
                            "student_name": row.get("student_name"),
                            "course_id": str(row.get("course_id")),
                            "risk_level": row.get("overall_risk"),
                            "status": payload.get("status"),
                        },
                    )
                st.session_state.message_log.append(payload)
                results.append(row.get("student_name"))
            except (CanvasAPIError, DatabaseError) as exc:
                failures.append(f"{row.get('student_name')}: {exc}")
            progress.progress(index / len(selected_ids), text=f"Procesando {index} de {len(selected_ids)}")
        progress.empty()
        if results:
            st.success(f"Se procesaron correctamente {len(results)} mensaje(s).")
        if failures:
            st.error("\n".join(failures))

st.divider()
st.subheader("Sincronizar respuestas")
db = get_database()
if st.session_state.get("demo_mode", True):
    st.caption("La sincronización real de respuestas se habilita al conectarse con Canvas y Supabase.")
elif not db.connected:
    st.warning("Configure Supabase para conservar el identificador de la conversación y sincronizar respuestas.")
else:
    if st.button("Buscar respuestas nuevas en Canvas"):
        pending = db.get_pending_messages()
        if pending.empty:
            st.info("No hay mensajes pendientes de sincronización.")
        else:
            oauth_config = load_oauth_config()
            token = get_valid_canvas_token(oauth_config)
            canvas = CanvasService(st.session_state.get("canvas_url", oauth_config.canvas_url), token)
            profile = st.session_state.get("canvas_profile") or {}
            sender_id = str(profile.get("id") or "")
            updated = 0
            errors = []
            for message in pending.to_dict(orient="records"):
                try:
                    conversation = canvas.get_conversation(message["canvas_conversation_id"])
                    response = extract_conversation_response(
                        conversation,
                        sender_canvas_user_id=sender_id,
                        sent_at=message["sent_at"],
                    )
                    if response:
                        db.update_message_response(message["id"], **response)
                        db.log_audit(
                            action="message_response_synced",
                            entity_type="message",
                            entity_id=str(message.get("id")),
                            actor=current_actor(),
                            payload={"canvas_conversation_id": message.get("canvas_conversation_id")},
                        )
                        updated += 1
                except (CanvasAPIError, DatabaseError) as exc:
                    errors.append(str(exc))
            st.success(f"Se identificaron {updated} respuesta(s) nueva(s).")
            if errors:
                st.warning(f"{len(errors)} conversación(es) no pudieron consultarse.")
