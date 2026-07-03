from __future__ import annotations

from datetime import datetime, timezone

import pandas as pd
import streamlit as st

from components.ui import empty_state, page_header
from models.config import RiskConfig
from services.database_service import DatabaseError
from services.auth_service import current_actor
from services.referral_service import generate_referral_package
from services.runtime import get_database


page_header(
    "Derivaciones a bienestar",
    "Seleccione estudiantes, verifique duplicados y genere formatos individuales más un informe consolidado para cada asesor asignado.",
)

df = st.session_state.get("analysis_df")
if df is None or df.empty:
    empty_state("No hay casos disponibles", "Ejecute un análisis semanal antes de preparar derivaciones.")
    st.stop()

eligible = df[df["overall_risk"].isin(["Moderado", "Alto"])].copy()
if eligible.empty:
    st.success("El corte actual no contiene estudiantes con riesgo moderado o alto.")
    st.stop()

risk_filter = st.multiselect("Nivel de riesgo", ["Moderado", "Alto"], default=["Moderado", "Alto"])
advisors = sorted(eligible["asesor_bienestar"].fillna("Sin asignar").unique().tolist())
advisor_filter = st.multiselect("Asesor de bienestar", advisors, default=advisors)
filtered = eligible[eligible["overall_risk"].isin(risk_filter)] if risk_filter else eligible.copy()
if advisor_filter:
    filtered = filtered[filtered["asesor_bienestar"].fillna("Sin asignar").isin(advisor_filter)]

preselected = set(str(value) for value in st.session_state.get("preselected_referral_students", []))
editor = filtered[
    [
        "canvas_user_id",
        "carne",
        "student_name",
        "course_name",
        "overall_risk",
        "intervention_priority",
        "completion_percentage",
        "average_grade",
        "pending_count",
        "asesor_bienestar",
    ]
].copy()
editor.insert(0, "Seleccionar", editor["canvas_user_id"].astype(str).isin(preselected))
editor = editor.rename(
    columns={
        "carne": "Carné",
        "student_name": "Estudiante",
        "course_name": "Curso",
        "overall_risk": "Riesgo",
        "intervention_priority": "Prioridad",
        "completion_percentage": "Avance (%)",
        "average_grade": "Promedio (%)",
        "pending_count": "Pendientes",
        "asesor_bienestar": "Asesor de bienestar",
    }
)

edited = st.data_editor(
    editor,
    width="stretch",
    hide_index=True,
    height=460,
    disabled=[column for column in editor.columns if column != "Seleccionar"],
    column_config={"Seleccionar": st.column_config.CheckboxColumn(required=True)},
)
selected_canvas_ids = edited.loc[edited["Seleccionar"], "canvas_user_id"].astype(str).tolist()
selected = filtered[filtered["canvas_user_id"].astype(str).isin(selected_canvas_ids)].copy()

c1, c2, c3 = st.columns([1.2, 1.4, 1.4])
with c1:
    st.metric("Seleccionados", len(selected))
with c2:
    st.metric("Prioridad alta", int(selected["overall_risk"].eq("Alto").sum()) if not selected.empty else 0)
with c3:
    st.metric("Asesores receptores", selected["asesor_bienestar"].nunique() if not selected.empty else 0)

academic_advisor = st.text_input("Asesor académico que firma", value=st.session_state.get("academic_advisor", "Ing. Christian Pocol"))
st.session_state.academic_advisor = academic_advisor
notes = st.text_area("Observaciones generales para el paquete", placeholder="Opcional: contexto adicional del corte o acciones previas.")

config = RiskConfig.from_dict(st.session_state.get("risk_config"))
db = get_database()
if not selected.empty and db.connected:
    recent = db.get_recent_referrals(selected["carne"].astype(str).tolist(), config.referral_cooldown_days)
    if not recent.empty:
        duplicated = recent["carne"].astype(str).nunique()
        st.warning(
            f"Se encontraron {duplicated} estudiante(s) con una derivación activa durante los últimos "
            f"{config.referral_cooldown_days} días. Revise antes de continuar."
        )
        with st.expander("Ver posibles duplicados"):
            st.dataframe(recent, width="stretch", hide_index=True)

confirm = st.checkbox("Confirmo que revisé los estudiantes y las posibles derivaciones previas.")
if st.button("Generar y registrar paquete de derivaciones", type="primary", width="stretch", disabled=selected.empty or not confirm):
    try:
        if notes:
            selected["referral_notes"] = notes
        package, records = generate_referral_package(selected, academic_advisor=academic_advisor)
        st.session_state.referral_package = package
        st.session_state.referral_records = records
        if db.connected:
            batch_id = db.save_referral_batch(
                {
                    "analysis_run_id": st.session_state.get("analysis_run_id"),
                    "created_by_name": academic_advisor,
                    "student_count": len(records),
                    "advisor_count": selected["asesor_bienestar"].nunique(),
                    "notes": notes or None,
                    "created_at": datetime.now(timezone.utc).isoformat(),
                }
            )
            saved_count = db.save_referrals(batch_id, records)
            db.log_audit(
                action="referral_package_generated",
                entity_type="referral_batch",
                entity_id=batch_id,
                actor=current_actor(),
                payload={
                    "student_count": saved_count,
                    "advisor_count": selected["asesor_bienestar"].nunique(),
                    "high_risk_count": int(selected["overall_risk"].eq("Alto").sum()),
                },
            )
        st.success("Paquete generado correctamente.")
    except (ValueError, DatabaseError) as exc:
        st.error(str(exc))

if st.session_state.get("referral_package"):
    st.download_button(
        "Descargar paquete ZIP",
        data=st.session_state.referral_package,
        file_name=f"Derivaciones_AVE_{datetime.now().strftime('%Y%m%d_%H%M')}.zip",
        mime="application/zip",
        type="primary",
        width="stretch",
    )
    st.caption("El ZIP contiene una carpeta por asesor, un informe general y un Excel individual por estudiante.")
