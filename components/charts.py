from __future__ import annotations

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go


RISK_COLOR_MAP = {"Bajo": "#00AB0D", "Moderado": "#FFB500", "Alto": "#C62828", "Sin datos": "#98A2B3"}


def risk_distribution(df: pd.DataFrame) -> go.Figure:
    counts = df["overall_risk"].value_counts().reindex(["Bajo", "Moderado", "Alto", "Sin datos"], fill_value=0)
    chart_df = counts.rename_axis("Riesgo").reset_index(name="Estudiantes")
    chart_df = chart_df[chart_df["Estudiantes"] > 0]
    figure = px.pie(
        chart_df,
        names="Riesgo",
        values="Estudiantes",
        color="Riesgo",
        color_discrete_map=RISK_COLOR_MAP,
        hole=0.58,
    )
    figure.update_traces(textposition="inside", textinfo="percent+label")
    figure.update_layout(margin=dict(l=10, r=10, t=30, b=10), legend_title_text="")
    return figure


def top_risk_causes(df: pd.DataFrame) -> go.Figure:
    risk_columns = {
        "activity_risk": "Actividades",
        "grade_risk": "Calificaciones",
        "punctuality_risk": "Puntualidad",
        "access_risk": "Actividad Canvas",
        "communication_risk": "Comunicación",
    }
    rows = []
    for column, label in risk_columns.items():
        if column not in df.columns:
            continue
        rows.append(
            {
                "Indicador": label,
                "Alertas": int(df[column].isin(["Moderado", "Alto"]).sum()),
                "Altas": int((df[column] == "Alto").sum()),
            }
        )
    chart_df = pd.DataFrame(rows).sort_values("Alertas", ascending=True)
    figure = px.bar(chart_df, x="Alertas", y="Indicador", orientation="h", text="Alertas")
    figure.update_traces(marker_color="#1C73F5", textposition="outside")
    figure.update_layout(margin=dict(l=10, r=30, t=30, b=10), xaxis_title="Estudiantes con alerta", yaxis_title="")
    return figure


def progress_by_student(df: pd.DataFrame, limit: int = 15) -> go.Figure:
    chart_df = df.nsmallest(limit, "completion_percentage").copy()
    figure = px.bar(
        chart_df,
        x="completion_percentage",
        y="student_name",
        orientation="h",
        color="overall_risk",
        color_discrete_map=RISK_COLOR_MAP,
        text="completion_percentage",
    )
    figure.update_traces(texttemplate="%{text:.0f}%", textposition="outside")
    figure.update_layout(
        margin=dict(l=10, r=35, t=30, b=10),
        xaxis_title="Cumplimiento de la meta semanal (%)",
        yaxis_title="",
        xaxis_range=[0, 110],
        legend_title_text="Riesgo",
    )
    return figure


def advisor_workload(df: pd.DataFrame) -> go.Figure:
    chart_df = (
        df[df["overall_risk"].isin(["Moderado", "Alto"])]
        .groupby(["asesor_bienestar", "overall_risk"], dropna=False)
        .size()
        .reset_index(name="Estudiantes")
    )
    figure = px.bar(
        chart_df,
        x="asesor_bienestar",
        y="Estudiantes",
        color="overall_risk",
        color_discrete_map=RISK_COLOR_MAP,
        barmode="stack",
    )
    figure.update_layout(
        margin=dict(l=10, r=10, t=30, b=10),
        xaxis_title="Asesor de bienestar",
        yaxis_title="Casos con seguimiento",
        legend_title_text="Riesgo",
    )
    return figure


def student_week_progress(history: pd.DataFrame, current_row: dict) -> go.Figure:
    if history.empty:
        chart_df = pd.DataFrame(
            {
                "Semana": [current_row.get("week_number")],
                "Esperadas": [current_row.get("expected_activities")],
                "Completadas": [current_row.get("completed_activities")],
            }
        )
    else:
        chart_df = history.rename(
            columns={"week_number": "Semana", "expected_activities": "Esperadas", "completed_activities": "Completadas"}
        )[["Semana", "Esperadas", "Completadas"]].drop_duplicates("Semana", keep="last").sort_values("Semana")
    figure = go.Figure()
    figure.add_trace(go.Scatter(x=chart_df["Semana"], y=chart_df["Esperadas"], mode="lines+markers", name="Meta acumulada", line=dict(color="#0F1C75")))
    figure.add_trace(go.Scatter(x=chart_df["Semana"], y=chart_df["Completadas"], mode="lines+markers", name="Completadas", line=dict(color="#1C73F5")))
    figure.update_layout(margin=dict(l=10, r=10, t=30, b=10), xaxis=dict(dtick=1), yaxis_title="Actividades", legend_title_text="")
    return figure


def risk_history(history: pd.DataFrame) -> go.Figure:
    mapping = {"Bajo": 1, "Moderado": 2, "Alto": 3, "Sin datos": 0}
    chart_df = history.copy()
    if "created_at" in chart_df.columns:
        chart_df["Fecha"] = pd.to_datetime(chart_df["created_at"], errors="coerce")
    else:
        chart_df["Fecha"] = pd.to_datetime(chart_df.get("analysis_cutoff"), errors="coerce")
    chart_df["Nivel"] = chart_df["overall_risk"].map(mapping)
    figure = px.line(chart_df, x="Fecha", y="Nivel", markers=True, hover_data=["overall_risk", "average_grade", "completion_percentage"])
    figure.update_traces(line_color="#1C73F5")
    figure.update_yaxes(tickvals=[1, 2, 3], ticktext=["Bajo", "Moderado", "Alto"], range=[0.7, 3.3])
    figure.update_layout(margin=dict(l=10, r=10, t=30, b=10), yaxis_title="Riesgo")
    return figure
