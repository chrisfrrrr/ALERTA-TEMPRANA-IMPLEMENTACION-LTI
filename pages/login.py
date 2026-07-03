from __future__ import annotations

import streamlit as st

from components.ui import page_header
from services.auth_service import (
    AuthError,
    build_authorization_url,
    complete_manual_token_login,
    complete_oauth_login,
    load_oauth_config,
    logout,
    new_oauth_state,
)
from services.runtime import get_database


page_header(
    "Acceso institucional",
    "Use Canvas OAuth2 cuando TI habilite la Developer Key. Para piloto, utilice el modo token manual seguro sin guardar credenciales.",
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
    method = st.session_state.get("auth_method") or "oauth2"
    method_label = "Canvas OAuth2" if method == "canvas_oauth" else "Token manual seguro" if method == "manual_token" else method
    st.info(f"Rol asignado: {role} · Método: {method_label}")
    if st.button("Cerrar sesión", type="secondary"):
        logout(db)
        st.rerun()
    st.stop()

left, right = st.columns([1.4, 1])
with left:
    tabs = st.tabs(["Canvas OAuth2", "Token manual seguro"])

    with tabs[0]:
        st.markdown("### Iniciar sesión con Canvas")
        st.write(
            "La aplicación utilizará la autenticación oficial de Canvas cuando TI habilite la Developer Key. "
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

    with tabs[1]:
        st.markdown("### Piloto con token manual seguro")
        if not config.allow_manual_token_mode:
            st.warning("El modo token manual está deshabilitado por configuración.")
        else:
            st.write(
                "Este modo permite probar la aplicación sin Developer Key de TI. "
                "El token se valida contra Canvas y solo queda en la sesión activa de Streamlit; no se guarda en Supabase."
            )
            manual_url = st.text_input("URL de Canvas", value=config.canvas_url, key="manual_canvas_url")
            manual_token = st.text_input("Token personal de Canvas", type="password", key="manual_canvas_token")
            if st.button("Conectar con token manual", type="primary", use_container_width=True):
                try:
                    with st.spinner("Validando token con Canvas..."):
                        complete_manual_token_login(manual_url, manual_token, db, config)
                    st.success("Token validado correctamente. Ya puede cargar cursos desde la pestaña Conexión y análisis.")
                    st.rerun()
                except AuthError as exc:
                    st.error(str(exc))
                    if db.connected:
                        db.log_audit(action="login_manual_token_denied", entity_type="session", payload={"reason": str(exc)})

with right:
    st.markdown("### Controles de seguridad")
    st.markdown(
        """
        - No se solicita contraseña de Canvas.
        - No se guarda token personal en Supabase.
        - El token manual se mantiene solo en la sesión activa.
        - Se valida el usuario autorizado, si esa opción está activada.
        - Se registra auditoría de acceso.
        - En producción se recomienda OAuth2 con Developer Key.
        """
    )
    if config.allow_demo_mode:
        st.divider()
        st.markdown("### Modo demostración")
        if st.button("Entrar en modo demostración", use_container_width=True):
            st.session_state.demo_mode = True
            st.session_state.authenticated = False
            st.session_state.auth_method = "demo"
            st.session_state.canvas_profile = {"id": "demo", "name": "Asesor de demostración"}
            if db.connected:
                db.log_audit(action="login_demo", entity_type="session", payload={"mode": "demo"})
            st.rerun()
