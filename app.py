from __future__ import annotations

import streamlit as st

from components.ui import inject_global_css, render_sidebar_brand
from models.config import RiskConfig
from services.auth_service import get_valid_canvas_token, load_oauth_config


st.set_page_config(
    page_title="AVE | Alerta temprana",
    page_icon="🎓",
    layout="wide",
    initial_sidebar_state="expanded",
)


def _default_demo_mode() -> bool:
    try:
        return bool(st.secrets.get("ALLOW_DEMO_MODE", True)) and not bool(st.secrets.get("REQUIRE_AUTHORIZED_USER", False))
    except Exception:
        return True


def initialize_state() -> None:
    defaults = {
        "demo_mode": _default_demo_mode(),
        "authenticated": False,
        "auth_user": None,
        "user_role": None,
        "oauth_tokens": {},
        "canvas_url": "https://uvg.instructure.com",
        "canvas_token": "",
        "canvas_profile": None,
        "courses": [],
        "sections": [],
        "analysis_df": None,
        "analysis_details": {},
        "analysis_diagnostics": {},
        "analysis_run_id": None,
        "selected_student_id": None,
        "preselected_message_students": [],
        "preselected_referral_students": [],
        "message_log": [],
        "referral_package": None,
        "referral_records": [],
        "academic_advisor": "Ing. Christian Pocol",
        "risk_config": RiskConfig().as_dict(),
        "risk_config_loaded": False,
    }
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value


initialize_state()

config = load_oauth_config()
if st.session_state.get("authenticated") and not st.session_state.get("demo_mode", False):
    try:
        st.session_state.canvas_token = get_valid_canvas_token(config)
        st.session_state.canvas_url = config.canvas_url
    except Exception:
        st.session_state.authenticated = False
        st.session_state.canvas_token = ""

inject_global_css()
render_sidebar_brand()

is_demo = bool(st.session_state.get("demo_mode", False))
is_authenticated = bool(st.session_state.get("authenticated") and st.session_state.get("canvas_token"))
role = st.session_state.get("user_role") or "sin_rol"

if not is_demo and not is_authenticated:
    pages = {
        "Seguridad": [
            st.Page("pages/login.py", title="Acceso institucional", icon="🔐"),
        ]
    }
elif role == "asesor_bienestar":
    # Vista reducida para bienestar. La restricción fuerte debe reforzarse con RLS/roles en Supabase.
    pages = {
        "Seguridad": [st.Page("pages/login.py", title="Acceso institucional", icon="🔐")],
        "Seguimiento": [
            st.Page("pages/dashboard_general.py", title="Dashboard general", icon="📊"),
            st.Page("pages/estudiante.py", title="Expediente individual", icon="👤"),
            st.Page("pages/historial.py", title="Historial y evolución", icon="📈"),
        ],
    }
else:
    admin_pages = []
    if is_demo or role in {"admin", "administrador"}:
        admin_pages.append(st.Page("pages/configuracion.py", title="Configuración", icon="⚙️"))
    pages = {
        "Seguridad": [
            st.Page("pages/login.py", title="Acceso institucional", icon="🔐"),
        ],
        "Operación": [
            st.Page("pages/inicio.py", title="Conexión y análisis", icon="🔄"),
            st.Page("pages/dashboard_general.py", title="Dashboard general", icon="📊"),
            st.Page("pages/estudiante.py", title="Expediente individual", icon="👤"),
        ],
        "Intervenciones": [
            st.Page("pages/mensajeria.py", title="Mensajería Canvas", icon="✉️"),
            st.Page("pages/derivaciones.py", title="Derivaciones", icon="📁"),
            st.Page("pages/historial.py", title="Historial y evolución", icon="📈"),
        ],
    }
    if admin_pages:
        pages["Administración"] = admin_pages

navigation = st.navigation(pages)
navigation.run()
