from __future__ import annotations

import pandas as pd
import streamlit as st

from components.charts import risk_history, student_week_progress
from components.ui import empty_state, page_header
from services.runtime import get_database


page_header(
    "Historial y evolución",
    "Compare cortes semanales para identificar recuperación, estancamiento, deterioro y reincidencia antes de volver a derivar.",
)

db = get_database()
current = st.session_state.get("analysis_df")

if db.connected:
    history = db.get_snapshot_history(limit=10000)
else:
    history = pd.DataFrame()

if history.empty and (current is None or current.empty):
    empty_state("Sin historial", "Configure Supabase o ejecute al menos un análisis durante esta sesión.")
    st.stop()

if history.empty:
    st.warning("Supabase no está disponible; se muestra únicamente el corte actual de la sesión.")
    history = current.copy()
    history["created_at"] = history.get("analysis_cutoff")

student_pairs = history[["carne", "student_name"]].drop_duplicates().dropna()
option_map = {f"{row.student_name} · {row.carne}": str(row.carne) for row in student_pairs.itertuples()}
selected_label = st.selectbox("Estudiante", list(option_map.keys()))
carne = option_map[selected_label]
student_history = history[history["carne"].astype(str) == carne].copy()

courses = student_history[["course_id", "course_name"]].drop_duplicates()
course_map = {f"{row.course_name}": str(row.course_id) for row in courses.itertuples()}
selected_course_label = st.selectbox("Curso", list(course_map.keys()))
course_id = course_map[selected_course_label]
student_history = student_history[student_history["course_id"].astype(str) == course_id].copy()

latest = student_history.iloc[-1].to_dict()
c1, c2 = st.columns(2)
with c1:
    st.subheader("Avance acumulado")
    st.plotly_chart(student_week_progress(student_history, latest), width="stretch")
with c2:
    st.subheader("Evolución del riesgo")
    st.plotly_chart(risk_history(student_history), width="stretch")

columns = [
    col
    for col in [
        "created_at",
        "week_number",
        "overall_risk",
        "intervention_priority",
        "expected_activities",
        "completed_activities",
        "completion_percentage",
        "average_grade",
        "weekly_sessions",
        "inactivity_hours",
    ]
    if col in student_history.columns
]
st.dataframe(student_history[columns], width="stretch", hide_index=True)

if db.connected:
    st.divider()
    st.subheader("Derivaciones registradas")
    referrals = db.get_referrals()
    if referrals.empty:
        st.caption("No existen derivaciones registradas.")
    else:
        referrals = referrals[referrals["carne"].astype(str) == carne]
        st.dataframe(referrals, width="stretch", hide_index=True)
