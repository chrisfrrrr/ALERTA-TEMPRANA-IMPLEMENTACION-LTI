from __future__ import annotations

import pandas as pd
import streamlit as st

from components.charts import risk_history, student_week_progress
from components.ui import empty_state, metric_card, page_header, risk_badge
from services.runtime import get_database
from utils.dates import format_hours


page_header(
    "Expediente individual",
    "Consulte la evidencia detrás del riesgo, las actividades pendientes y la evolución histórica de cada estudiante.",
)

df = st.session_state.get("analysis_df")
if df is None or df.empty:
    empty_state("Sin estudiantes analizados", "Ejecute un análisis semanal para abrir expedientes individuales.")
    st.stop()

options = {f"{row.student_name} · {row.carne}": str(row.canvas_user_id) for row in df.itertuples()}
current_id = str(st.session_state.get("selected_student_id") or next(iter(options.values())))
current_label = next((label for label, value in options.items() if value == current_id), next(iter(options)))
selected_label = st.selectbox("Estudiante", list(options.keys()), index=list(options.keys()).index(current_label))
student_id = options[selected_label]
st.session_state.selected_student_id = student_id
row = df[df["canvas_user_id"].astype(str) == student_id].iloc[0].to_dict()
detail = st.session_state.get("analysis_details", {}).get(student_id, {})

head1, head2 = st.columns([3.2, 1])
with head1:
    st.markdown(f"## {row['student_name']}")
    st.markdown(
        f"Carné **{row.get('carne') or 'Sin dato'}** · {row.get('email') or 'Correo no disponible'} · "
        f"{row.get('course_name')} · {row.get('section_name')}"
    )
    st.markdown(
        f"Riesgo actual: {risk_badge(row.get('overall_risk', 'Sin datos'))} &nbsp; "
        f"Prioridad: **{row.get('intervention_priority')}** &nbsp; Evolución: **{row.get('evolution')}**",
        unsafe_allow_html=True,
    )
with head2:
    st.markdown("**Asesor de bienestar**")
    st.write(row.get("asesor_bienestar") or "Sin asignar")
    st.caption(row.get("estado_bienestar") or "Estado no registrado")

m1, m2, m3, m4, m5 = st.columns(5)
with m1:
    metric_card("Avance", f"{row.get('completion_percentage', 0):.0f} %", f"{row.get('completed_activities')}/{row.get('expected_activities')} esperadas")
with m2:
    average = row.get("average_grade")
    metric_card("Promedio", f"{average:.1f} %" if pd.notna(average) else "Sin datos", row.get("grade_risk"))
with m3:
    metric_card("Pendientes", row.get("pending_count"), "Actividades esperadas")
with m4:
    sessions = row.get("weekly_sessions")
    metric_card("Ingresos", int(sessions) if pd.notna(sessions) else "Sin datos", "Sesiones estimadas")
with m5:
    metric_card("Inactividad", format_hours(row.get("inactivity_hours")), row.get("access_risk"))

summary_tab, activities_tab, history_tab, interventions_tab = st.tabs(
    ["Resumen de indicadores", "Actividades", "Historial", "Intervenciones"]
)

with summary_tab:
    st.subheader("Fundamento de la clasificación")
    indicators = detail.get("indicators", [])
    if indicators:
        cols = st.columns(min(5, len(indicators)))
        for col, indicator in zip(cols, indicators):
            with col:
                st.markdown(
                    f"<div class='ave-card'><strong>{indicator['name']}</strong><br>"
                    f"{risk_badge(indicator['risk'])}<p class='small-muted'>{indicator['detail']}</p></div>",
                    unsafe_allow_html=True,
                )
    st.markdown("#### Razones detectadas")
    for reason in row.get("reasons") or []:
        st.markdown(f"- {reason}")

with activities_tab:
    assignments = pd.DataFrame(detail.get("assignments", []))
    if assignments.empty:
        st.info("No se recuperó el detalle de actividades.")
    else:
        status_filter = st.multiselect(
            "Mostrar",
            ["Pendientes", "Completadas", "Tardías"],
            default=["Pendientes", "Completadas", "Tardías"],
        )
        mask = pd.Series(False, index=assignments.index)
        if "Pendientes" in status_filter:
            mask |= ~assignments["completada"]
        if "Completadas" in status_filter:
            mask |= assignments["completada"]
        if "Tardías" in status_filter:
            mask |= assignments["tardia"]
        display = assignments[mask].rename(
            columns={
                "actividad": "Actividad",
                "semana_asignada": "Semana",
                "esperada_a_la_fecha": "Esperada a la fecha",
                "completada": "Completada",
                "tardia": "Tardía",
                "fecha_limite": "Fecha límite",
                "fecha_entrega": "Fecha de entrega",
                "puntaje": "Puntaje",
                "puntos_posibles": "Puntos posibles",
            }
        )
        st.dataframe(display, width="stretch", hide_index=True, height=440)

with history_tab:
    db = get_database()
    history = db.get_snapshot_history(carne=str(row.get("carne")), course_id=row.get("course_id")) if db.connected else pd.DataFrame()
    chart_col1, chart_col2 = st.columns(2)
    with chart_col1:
        st.markdown("#### Avance por semana")
        st.plotly_chart(student_week_progress(history, row), width="stretch")
    with chart_col2:
        st.markdown("#### Evolución del riesgo")
        if not history.empty:
            st.plotly_chart(risk_history(history), width="stretch")
        else:
            st.info("El historial aparecerá después de registrar más de un corte en Supabase.")
    if not history.empty:
        columns = [
            col for col in ["created_at", "week_number", "overall_risk", "completion_percentage", "average_grade", "inactivity_hours"] if col in history.columns
        ]
        st.dataframe(history[columns], width="stretch", hide_index=True)

with interventions_tab:
    message_log = pd.DataFrame(st.session_state.get("message_log", []))
    if not message_log.empty:
        message_log = message_log[message_log["canvas_user_id"].astype(str) == student_id]
    st.markdown("#### Comunicaciones registradas en esta sesión")
    if message_log.empty:
        st.caption("No hay mensajes en la sesión actual.")
    else:
        st.dataframe(message_log, width="stretch", hide_index=True)

    a1, a2 = st.columns(2)
    with a1:
        if st.button("Preparar mensaje", type="primary", width="stretch"):
            st.session_state.preselected_message_students = [student_id]
            st.switch_page("pages/mensajeria.py")
    with a2:
        if row.get("overall_risk") in {"Moderado", "Alto"} and st.button("Preparar derivación", width="stretch"):
            st.session_state.preselected_referral_students = [student_id]
            st.switch_page("pages/derivaciones.py")
