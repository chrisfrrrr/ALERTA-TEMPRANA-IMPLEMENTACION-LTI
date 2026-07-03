from __future__ import annotations

import streamlit as st

from components.ui import page_header
from services.auth_service import (
    AuthError,
    build_authorization_url,
    complete_oauth_login,
    load_oauth_config,
    logout,
    new_oauth_state,
)
from services.runtime import get_database


page_header(
    "Acceso institucional",
    "Inicie sesión mediante Canvas OAuth2 para utilizar la aplicación sin pegar tokens personales.",
)

config = load_oauth_config()
db = get_database()

try:
    if complete_oauth_login(config, db):
        st.success("Inicio de sesión completado correctamente. Ya puede utilizar la aplicación.")
        st.rerun()
except AuthError as exc:
    st.error(str(exc))
    if db.connected:
        db.log_audit(action="login_denied", entity_type="session", payload={"reason": str(exc)})

profile = st.session_state.get("canvas_profile")
if st.session_state.get("authenticated") and profile:
    st.success(f"Sesión activa como {profile.get('name') or profile.get('short_name')}")
    role = st.session_state.get("user_role", "asesor_academico")
    st.info(f"Rol asignado: {role}")
    if st.button("Cerrar sesión", type="secondary"):
        logout(db)
        st.rerun()
    st.stop()

left, right = st.columns([1.4, 1])
with left:
    st.markdown("### Iniciar sesión con Canvas")
    st.write(
        "La aplicación utilizará la autenticación oficial de Canvas. "
        "El token de acceso se mantiene únicamente en la sesión activa y no se almacena en Supabase."
    )
    if config.enabled:
        state = new_oauth_state()
        auth_url = build_authorization_url(config, state)
        st.link_button("Iniciar sesión con Canvas", auth_url, type="primary", use_container_width=True)
        st.caption("Canvas solicitará autorización y luego regresará automáticamente a esta aplicación.")
    else:
        st.warning(
            "OAuth2 todavía no está configurado. Complete CANVAS_OAUTH_CLIENT_ID, "
            "CANVAS_OAUTH_CLIENT_SECRET y CANVAS_OAUTH_REDIRECT_URI en los secretos de Streamlit."
        )

with right:
    st.markdown("### Controles de seguridad")
    st.markdown(
        """
        - No se solicita contraseña de Canvas.
        - No se guarda token personal en Supabase.
        - Se valida el usuario autorizado.
        - Se registra auditoría de acceso.
        - Se puede limitar el alcance con Developer Key.
        """
    )
    if config.allow_demo_mode:
        st.divider()
        st.markdown("### Modo demostración")
        if st.button("Entrar en modo demostración", use_container_width=True):
            st.session_state.demo_mode = True
            st.session_state.authenticated = False
            st.session_state.canvas_profile = {"id": "demo", "name": "Asesor de demostración"}
            if db.connected:
                db.log_audit(action="login_demo", entity_type="session", payload={"mode": "demo"})
            st.rerun()
