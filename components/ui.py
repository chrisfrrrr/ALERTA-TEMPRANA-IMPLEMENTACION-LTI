from __future__ import annotations

import html
from typing import Any

import streamlit as st


RISK_COLORS = {
    "Bajo": ("#E8F7EA", "#087A16"),
    "Moderado": ("#FFF3D1", "#9A5B00"),
    "Alto": ("#FDE8EA", "#B4232F"),
    "Sin datos": ("#EEF1F5", "#5C667A"),
}


def inject_global_css() -> None:
    st.markdown(
        """
        <style>
        :root {
            --ave-navy: #0F1C75;
            --ave-blue: #1C73F5;
            --ave-green: #00AB0D;
            --ave-amber: #FFB500;
            --ave-red: #C62828;
            --ave-bg: #F5F7FB;
            --ave-text: #172033;
        }
        .stApp { background: var(--ave-bg); }
        [data-testid="stSidebar"] {
            background: linear-gradient(180deg, #0F1C75 0%, #14278F 65%, #1C73F5 150%);
        }
        [data-testid="stSidebar"] * { color: white; }
        [data-testid="stSidebar"] div[role="radiogroup"] label {
            border-radius: 10px;
            padding: 0.25rem 0.5rem;
        }
        [data-testid="stSidebar"] div[role="radiogroup"] label:hover {
            background: rgba(255,255,255,.10);
        }
        .block-container { max-width: 1450px; padding-top: 1.5rem; padding-bottom: 3rem; }
        .ave-header {
            background: linear-gradient(120deg, #0F1C75 0%, #1C73F5 100%);
            color: white; border-radius: 18px; padding: 1.25rem 1.5rem; margin-bottom: 1.15rem;
            box-shadow: 0 10px 28px rgba(15,28,117,.14);
        }
        .ave-header h1 { margin: 0; font-size: 1.65rem; color: white; }
        .ave-header p { margin: .35rem 0 0; opacity: .9; }
        .ave-card {
            background: white; border: 1px solid #E3E7EF; border-radius: 15px;
            padding: 1rem 1.1rem; box-shadow: 0 5px 18px rgba(23,32,51,.05);
        }
        .ave-metric {
            background: white; border: 1px solid #E3E7EF; border-radius: 15px;
            padding: 1rem; min-height: 118px; box-shadow: 0 5px 18px rgba(23,32,51,.05);
        }
        .ave-metric .label { color: #667085; font-size: .83rem; font-weight: 650; }
        .ave-metric .value { color: #0F1C75; font-size: 1.7rem; font-weight: 780; margin-top: .2rem; }
        .ave-metric .delta { color: #667085; font-size: .76rem; margin-top: .15rem; }
        .risk-badge { display:inline-block; padding:.25rem .62rem; border-radius:999px; font-weight:700; font-size:.78rem; }
        .priority-strip { border-left: 5px solid #1C73F5; padding: .55rem .8rem; background: #F0F5FF; border-radius: 8px; }
        .small-muted { color:#667085; font-size:.82rem; }
        div[data-testid="stDataFrame"] { border:1px solid #E3E7EF; border-radius:13px; overflow:hidden; }
        div[data-testid="stMetric"] {
            background:white; border:1px solid #E3E7EF; padding: .75rem 1rem; border-radius:14px;
            box-shadow:0 5px 18px rgba(23,32,51,.04);
        }
        .stButton > button, .stDownloadButton > button { border-radius: 10px; font-weight: 650; }
        .stTabs [data-baseweb="tab-list"] { gap: .5rem; }
        .stTabs [data-baseweb="tab"] { border-radius: 9px; padding-left: 1rem; padding-right: 1rem; }
        </style>
        """,
        unsafe_allow_html=True,
    )


def render_sidebar_brand() -> None:
    with st.sidebar:
        st.markdown(
            """
            <div style="padding:.4rem .2rem 1.2rem;">
              <div style="font-size:2rem;font-weight:850;letter-spacing:.04em;">AVE</div>
              <div style="font-size:.78rem;opacity:.82;line-height:1.35;">Sistema de alerta temprana<br>y seguimiento académico</div>
            </div>
            """,
            unsafe_allow_html=True,
        )
        mode = "Demostración" if st.session_state.get("demo_mode", True) else "Canvas OAuth2"
        st.caption(f"Modo actual: {mode}")
        if st.session_state.get("canvas_profile"):
            profile = st.session_state["canvas_profile"]
            st.caption(f"Usuario: {profile.get('name') or profile.get('short_name')}")
        if st.session_state.get("user_role"):
            st.caption(f"Rol: {st.session_state.get('user_role')}")
        if st.session_state.get("analysis_df") is not None:
            df = st.session_state.get("analysis_df")
            if hasattr(df, "empty") and not df.empty:
                st.caption(f"Último análisis: {len(df)} estudiantes")


def page_header(title: str, subtitle: str) -> None:
    st.markdown(
        f"<div class='ave-header'><h1>{html.escape(title)}</h1><p>{html.escape(subtitle)}</p></div>",
        unsafe_allow_html=True,
    )


def metric_card(label: str, value: Any, delta: str = "") -> None:
    st.markdown(
        f"""
        <div class="ave-metric">
          <div class="label">{html.escape(str(label))}</div>
          <div class="value">{html.escape(str(value))}</div>
          <div class="delta">{html.escape(str(delta))}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def risk_badge(risk: str) -> str:
    bg, fg = RISK_COLORS.get(risk, RISK_COLORS["Sin datos"])
    return f"<span class='risk-badge' style='background:{bg};color:{fg};'>{html.escape(risk)}</span>"


def empty_state(title: str, message: str) -> None:
    st.markdown(
        f"""
        <div class="ave-card" style="text-align:center;padding:2.2rem;">
          <div style="font-size:1.1rem;font-weight:750;color:#0F1C75;">{html.escape(title)}</div>
          <div class="small-muted" style="margin-top:.45rem;">{html.escape(message)}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def dataframe_for_display(df):
    display = df.copy()
    rename = {
        "student_name": "Estudiante",
        "carne": "Carné",
        "course_name": "Curso",
        "section_name": "Sección",
        "overall_risk": "Riesgo",
        "intervention_priority": "Prioridad",
        "completion_percentage": "Avance esperado (%)",
        "average_grade": "Promedio (%)",
        "completed_activities": "Completadas",
        "expected_activities": "Esperadas",
        "pending_count": "Pendientes",
        "late_count": "Tardías",
        "weekly_sessions": "Ingresos estimados",
        "inactivity_hours": "Inactividad (h)",
        "asesor_bienestar": "Asesor de bienestar",
        "evolution": "Evolución",
    }
    columns = [column for column in rename if column in display.columns]
    return display[columns].rename(columns=rename)
