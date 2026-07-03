from __future__ import annotations

from pathlib import Path

import streamlit as st

from components.ui import page_header
from models.config import RiskConfig
from services.database_service import DatabaseError
from services.auth_service import current_actor, load_oauth_config
from services.runtime import get_database
from utils.data_cleaning import load_wellbeing_csv


ROOT = Path(__file__).resolve().parents[1]
BASE_PATH = ROOT / "data" / "bienestar_base.csv"

page_header(
    "Configuración y administración",
    "Ajuste límites institucionales, valide conexiones y sincronice la asignación de estudiantes con asesores de bienestar.",
)

db_global = get_database()
if not st.session_state.get("risk_config_loaded", False):
    stored_config = db_global.load_risk_config() if db_global.connected else None
    if stored_config:
        st.session_state.risk_config = RiskConfig.from_dict(stored_config).as_dict()
    st.session_state.risk_config_loaded = True

config = RiskConfig.from_dict(st.session_state.get("risk_config"))

rules_tab, database_tab, auth_tab, audit_tab, diagnostics_tab = st.tabs(["Reglas de riesgo", "Supabase y bienestar", "Usuarios y OAuth2", "Auditoría", "Diagnóstico"])

with rules_tab:
    st.info("Los cursos se analizan en cinco semanas. Los límites pueden ajustarse sin modificar el código.")
    with st.form("risk_rules"):
        st.markdown("#### Cumplimiento de actividades")
        a1, a2 = st.columns(2)
        activity_low = a1.number_input("Bajo desde (%)", 0.0, 100.0, config.activity_low_min, 1.0)
        activity_moderate = a2.number_input("Moderado desde (%)", 0.0, 100.0, config.activity_moderate_min, 1.0)

        st.markdown("#### Calificaciones")
        g1, g2 = st.columns(2)
        grade_low = g1.number_input("Bajo desde (%) ", 0.0, 100.0, config.grade_low_min, 1.0)
        grade_moderate = g2.number_input("Moderado desde (%) ", 0.0, 100.0, config.grade_moderate_min, 1.0)

        st.markdown("#### Actividad en Canvas")
        c1, c2, c3, c4 = st.columns(4)
        access_low = c1.number_input("Ingresos para bajo", 1, 20, config.access_low_min)
        access_moderate = c2.number_input("Ingresos mínimos moderado", 0, 20, config.access_moderate_min)
        inactivity_moderate = c3.number_input("Inactividad moderada (h)", 1.0, 500.0, config.inactivity_moderate_hours)
        inactivity_high = c4.number_input("Inactividad alta (h)", 1.0, 500.0, config.inactivity_high_hours)

        st.markdown("#### Comunicación y derivaciones")
        r1, r2, r3, r4 = st.columns(4)
        response_low = r1.number_input("Respuesta baja (h)", 1.0, 500.0, config.response_low_hours)
        response_moderate = r2.number_input("Respuesta moderada (h)", 1.0, 500.0, config.response_moderate_hours)
        response_high = r3.number_input("Sin respuesta alta (h)", 1.0, 500.0, config.response_high_hours)
        cooldown = r4.number_input("Espera entre derivaciones (días)", 1, 120, config.referral_cooldown_days)

        submitted = st.form_submit_button("Guardar reglas", type="primary")
        if submitted:
            new_config = RiskConfig(
                course_weeks=5,
                activity_low_min=activity_low,
                activity_moderate_min=activity_moderate,
                grade_low_min=grade_low,
                grade_moderate_min=grade_moderate,
                access_low_min=access_low,
                access_moderate_min=access_moderate,
                inactivity_moderate_hours=inactivity_moderate,
                inactivity_high_hours=inactivity_high,
                response_low_hours=response_low,
                response_moderate_hours=response_moderate,
                response_high_hours=response_high,
                referral_cooldown_days=cooldown,
            )
            st.session_state.risk_config = new_config.as_dict()
            if db_global.connected:
                try:
                    db_global.save_risk_config(new_config.as_dict())
                except DatabaseError as exc:
                    st.warning(f"Las reglas se aplicaron en la sesión, pero no se guardaron en Supabase: {exc}")
            st.success("Reglas actualizadas para los próximos análisis.")

with database_tab:
    db = get_database()
    wellbeing = load_wellbeing_csv(BASE_PATH)
    st.markdown("#### Base de asignación de bienestar")
    m1, m2, m3 = st.columns(3)
    m1.metric("Estudiantes válidos", len(wellbeing))
    m2.metric("Asesores", wellbeing["asesor_bienestar"].nunique())
    m3.metric("Sin asignar", int((wellbeing["asesor_bienestar"] == "Sin asignar").sum()))
    st.dataframe(
        wellbeing.groupby("asesor_bienestar").size().reset_index(name="Estudiantes"),
        width="stretch",
        hide_index=True,
    )

    uploaded = st.file_uploader("Actualizar base de bienestar (CSV)", type=["csv"])
    if uploaded is not None:
        try:
            uploaded_df = load_wellbeing_csv(uploaded)
            st.success(f"Archivo válido: {len(uploaded_df)} estudiantes.")
            st.dataframe(uploaded_df.head(20), width="stretch", hide_index=True)
            if st.button("Guardar como nueva base local"):
                uploaded_df.to_csv(BASE_PATH, index=False, encoding="utf-8-sig")
                st.success("Base local actualizada.")
        except ValueError as exc:
            st.error(str(exc))


    analysis_df = st.session_state.get("analysis_df")
    if analysis_df is not None and not analysis_df.empty and "wellbeing_match_method" in analysis_df.columns:
        st.markdown("#### Coincidencia con el último análisis")
        matched = int(analysis_df["wellbeing_record_found"].fillna(False).sum())
        assigned = int((analysis_df["asesor_bienestar"].fillna("Sin asignar") != "Sin asignar").sum())
        d1, d2, d3 = st.columns(3)
        d1.metric("Coincidencias encontradas", matched)
        d2.metric("Con asesor asignado", assigned)
        d3.metric("Sin coincidencia", len(analysis_df) - matched)
        st.dataframe(
            analysis_df["wellbeing_match_method"].value_counts().rename_axis("Método").reset_index(name="Estudiantes"),
            width="stretch",
            hide_index=True,
        )
        unmatched = analysis_df[~analysis_df["wellbeing_record_found"].fillna(False)].copy()
        if not unmatched.empty:
            columns = [column for column in ["student_name", "carne_canvas_original", "email", "course_name", "section_name"] if column in unmatched.columns]
            with st.expander("Ver estudiantes sin coincidencia"):
                st.dataframe(unmatched[columns], width="stretch", hide_index=True)
                st.download_button(
                    "Descargar pendientes de vinculación",
                    unmatched[columns].to_csv(index=False).encode("utf-8-sig"),
                    file_name="estudiantes_sin_asesor_bienestar.csv",
                    mime="text/csv",
                )

    st.markdown("#### Sincronización con Supabase")
    if not db.connected:
        st.warning("Agregue SUPABASE_URL y SUPABASE_SERVICE_ROLE_KEY en los secretos de Streamlit.")
    else:
        ok, _message = db.test_connection()
        if ok:
            st.success("Conexión histórica disponible")
        else:
            st.warning("La conexión histórica no está disponible en este momento.")
        if st.button("Sincronizar estudiantes y asignaciones", type="primary"):
            try:
                students = db.upsert_students(wellbeing)
                advisors = db.upsert_wellbeing_advisors(wellbeing)
                assignments = db.sync_wellbeing_assignments(wellbeing)
                st.success(f"Sincronizados: {students} estudiantes, {advisors} asesores y {assignments} asignaciones.")
            except DatabaseError as exc:
                st.error(str(exc))


with auth_tab:
    st.markdown("#### Autenticación Canvas OAuth2")
    oauth_config = load_oauth_config()
    c1, c2, c3 = st.columns(3)
    c1.metric("OAuth2", "Configurado" if oauth_config.enabled else "Pendiente")
    c2.metric("Demo", "Permitido" if oauth_config.allow_demo_mode else "Bloqueado")
    c3.metric("Lista autorizada", "Obligatoria" if oauth_config.require_authorized_user else "Modo piloto")
    st.caption("El client secret no se muestra. Debe vivir únicamente en Streamlit Secrets o variables de entorno.")

    st.markdown("#### Usuarios autorizados")
    db = get_database()
    if not db.connected:
        st.warning("Conecte Supabase para administrar roles internos.")
    else:
        users = db.list_authorized_users()
        if users.empty:
            st.info("Aún no hay usuarios autorizados registrados. Puede crear el primero con el formulario inferior.")
        else:
            display_cols = [col for col in ["full_name", "email", "canvas_user_id", "role", "is_active", "last_login_at"] if col in users.columns]
            st.dataframe(users[display_cols], width="stretch", hide_index=True)

        with st.form("authorized_user_form"):
            st.markdown("##### Agregar o actualizar usuario")
            full_name = st.text_input("Nombre completo")
            email = st.text_input("Correo institucional")
            canvas_user_id = st.text_input("Canvas user ID", help="Puede dejarse vacío si todavía no se conoce; el correo servirá como coincidencia inicial.")
            role = st.selectbox("Rol", ["admin", "asesor_academico", "asesor_bienestar", "consulta"])
            is_active = st.checkbox("Usuario activo", value=True)
            submitted_user = st.form_submit_button("Guardar usuario", type="primary")
            if submitted_user:
                if not full_name or not (email or canvas_user_id):
                    st.error("Ingrese nombre y al menos correo o Canvas user ID.")
                else:
                    try:
                        db.save_authorized_user(
                            {
                                "full_name": full_name,
                                "email": email or None,
                                "canvas_user_id": canvas_user_id or None,
                                "role": role,
                                "is_active": is_active,
                            }
                        )
                        db.log_audit(
                            action="authorized_user_saved",
                            entity_type="authorized_user",
                            actor=current_actor(),
                            payload={"email": email, "canvas_user_id": canvas_user_id, "role": role, "is_active": is_active},
                        )
                        st.success("Usuario guardado correctamente.")
                    except DatabaseError as exc:
                        st.error(str(exc))

with audit_tab:
    st.markdown("#### Bitácora de auditoría")
    db = get_database()
    if not db.connected:
        st.warning("Conecte Supabase para consultar auditoría.")
    else:
        audit = db.get_audit_log(limit=500)
        if audit.empty:
            st.info("Aún no hay eventos de auditoría registrados.")
        else:
            cols = [col for col in ["created_at", "action", "entity_type", "entity_id", "actor_name", "actor_email", "actor_role", "payload"] if col in audit.columns]
            st.dataframe(audit[cols], width="stretch", hide_index=True, height=460)
            st.download_button(
                "Descargar auditoría CSV",
                audit[cols].to_csv(index=False).encode("utf-8-sig"),
                file_name="auditoria_ave.csv",
                mime="text/csv",
            )

with diagnostics_tab:
    st.markdown("#### Estado de la sesión")
    st.json(
        {
            "modo": "demostración" if st.session_state.get("demo_mode") else "Canvas",
            "canvas_url": st.session_state.get("canvas_url"),
            "canvas_conectado": bool(st.session_state.get("canvas_profile")),
            "supabase_conectado": get_database().connected,
            "autenticado": bool(st.session_state.get("authenticated")),
            "rol": st.session_state.get("user_role"),
            "estudiantes_en_ultimo_analisis": len(st.session_state.get("analysis_df")) if st.session_state.get("analysis_df") is not None else 0,
            "reglas": st.session_state.get("risk_config"),
        }
    )
    st.caption(
        "La consulta de Page Views puede no estar disponible para todos los tokens. Cuando no existe permiso, "
        "la aplicación utiliza la última actividad del enrollment y marca la cantidad de sesiones como no disponible."
    )
