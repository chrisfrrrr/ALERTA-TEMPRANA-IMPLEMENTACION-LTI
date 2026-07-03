from __future__ import annotations

import pandas as pd
import streamlit as st

from components.charts import advisor_workload, progress_by_student, risk_distribution, top_risk_causes
from components.ui import dataframe_for_display, empty_state, metric_card, page_header


page_header(
    "Dashboard general",
    "Vista ejecutiva del riesgo académico, causas principales, evolución y carga de seguimiento por asesor de bienestar.",
)

df = st.session_state.get("analysis_df")
if df is None or df.empty:
    empty_state("Aún no existe un análisis", "Ejecute primero un corte semanal desde la página Conexión y análisis.")
    st.stop()

filter1, filter2, filter3, filter4 = st.columns([1.2, 1.6, 1.6, 2.1])
with filter1:
    risks = st.multiselect("Riesgo", ["Bajo", "Moderado", "Alto", "Sin datos"], default=["Bajo", "Moderado", "Alto"])
with filter2:
    advisors = sorted(df.get("asesor_bienestar", pd.Series(dtype=str)).fillna("Sin asignar").unique().tolist())
    selected_advisors = st.multiselect("Asesor de bienestar", advisors, default=advisors)
with filter3:
    evolutions = sorted(df["evolution"].fillna("Sin dato").unique().tolist())
    selected_evolutions = st.multiselect("Evolución", evolutions, default=evolutions)
with filter4:
    search = st.text_input("Buscar por nombre, carné o correo", placeholder="Ejemplo: 262597 o Alicia")

filtered = df.copy()
if risks:
    filtered = filtered[filtered["overall_risk"].isin(risks)]
if "asesor_bienestar" in filtered.columns and selected_advisors:
    filtered = filtered[filtered["asesor_bienestar"].fillna("Sin asignar").isin(selected_advisors)]
if selected_evolutions:
    filtered = filtered[filtered["evolution"].isin(selected_evolutions)]
if search:
    needle = search.lower().strip()
    mask = (
        filtered["student_name"].astype(str).str.lower().str.contains(needle, na=False)
        | filtered["carne"].astype(str).str.lower().str.contains(needle, na=False)
        | filtered["email"].astype(str).str.lower().str.contains(needle, na=False)
    )
    filtered = filtered[mask]

if filtered.empty:
    empty_state("No hay resultados", "Ajuste los filtros para volver a mostrar estudiantes.")
    st.stop()

m1, m2, m3, m4, m5 = st.columns(5)
with m1:
    metric_card("Analizados", len(filtered), f"de {len(df)} en el corte")
with m2:
    metric_card("Riesgo bajo", int((filtered["overall_risk"] == "Bajo").sum()), "Seguimiento preventivo")
with m3:
    metric_card("Riesgo moderado", int((filtered["overall_risk"] == "Moderado").sum()), "Contacto y posible derivación")
with m4:
    metric_card("Riesgo alto", int((filtered["overall_risk"] == "Alto").sum()), "Atención prioritaria")
with m5:
    metric_card("Mejorando", int((filtered["evolution"] == "Mejorando").sum()), "Respecto del corte anterior")

chart1, chart2 = st.columns([1, 1.35])
with chart1:
    st.subheader("Distribución del riesgo")
    st.plotly_chart(risk_distribution(filtered), width="stretch")
with chart2:
    st.subheader("Indicadores que generan más alertas")
    st.plotly_chart(top_risk_causes(filtered), width="stretch")

chart3, chart4 = st.columns([1.25, 1])
with chart3:
    st.subheader("Estudiantes con mayor brecha de avance")
    st.plotly_chart(progress_by_student(filtered), width="stretch")
with chart4:
    st.subheader("Casos por asesor de bienestar")
    if filtered["overall_risk"].isin(["Moderado", "Alto"]).any():
        st.plotly_chart(advisor_workload(filtered), width="stretch")
    else:
        st.info("No existen casos moderados o altos en el filtro actual.")

st.subheader("Listado operativo")
show = dataframe_for_display(filtered)
st.dataframe(show, width="stretch", hide_index=True, height=430)

csv = filtered.to_csv(index=False).encode("utf-8-sig")
action1, action2, action3 = st.columns([1.1, 1.3, 2.2])
with action1:
    st.download_button("Descargar CSV", data=csv, file_name="analisis_semanal_ave.csv", mime="text/csv", width="stretch")
with action2:
    student_options = {
        f"{row.student_name} · {row.carne}": row.canvas_user_id for row in filtered.itertuples()
    }
    selected_label = st.selectbox("Abrir expediente", list(student_options.keys()), label_visibility="collapsed") if student_options else None
with action3:
    if selected_label and st.button("Ver dashboard individual", type="primary", width="stretch"):
        st.session_state.selected_student_id = str(student_options[selected_label])
        st.switch_page("pages/estudiante.py")
