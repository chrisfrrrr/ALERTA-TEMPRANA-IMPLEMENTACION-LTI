from __future__ import annotations

import secrets
import time
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlencode

import requests
import streamlit as st

from services.canvas_service import CanvasAPIError, CanvasService
from services.database_service import DatabaseService


class AuthError(RuntimeError):
    """Error legible para autenticación institucional."""


@dataclass(slots=True)
class OAuthConfig:
    canvas_url: str
    client_id: str
    client_secret: str
    redirect_uri: str
    scopes: list[str]
    require_authorized_user: bool = False
    allow_demo_mode: bool = True
    allow_manual_token_mode: bool = True

    @property
    def enabled(self) -> bool:
        return bool(self.canvas_url and self.client_id and self.client_secret and self.redirect_uri)


def _secret_bool(name: str, default: bool) -> bool:
    try:
        value = st.secrets.get(name, default)
    except Exception:
        return default
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes", "sí", "si", "on"}


def _secret_list(name: str, default: list[str] | None = None) -> list[str]:
    default = default or []
    try:
        value = st.secrets.get(name, default)
    except Exception:
        return default
    if isinstance(value, str):
        return [part.strip() for part in value.replace(",", " ").split() if part.strip()]
    if isinstance(value, (list, tuple)):
        return [str(part).strip() for part in value if str(part).strip()]
    return default


def load_oauth_config() -> OAuthConfig:
    try:
        canvas_url = str(st.secrets.get("CANVAS_URL", "https://uvg.instructure.com")).rstrip("/")
        client_id = str(st.secrets.get("CANVAS_OAUTH_CLIENT_ID", "")).strip()
        client_secret = str(st.secrets.get("CANVAS_OAUTH_CLIENT_SECRET", "")).strip()
        redirect_uri = str(st.secrets.get("CANVAS_OAUTH_REDIRECT_URI", "")).strip()
    except Exception:
        canvas_url, client_id, client_secret, redirect_uri = "https://uvg.instructure.com", "", "", ""

    return OAuthConfig(
        canvas_url=canvas_url,
        client_id=client_id,
        client_secret=client_secret,
        redirect_uri=redirect_uri,
        scopes=_secret_list("CANVAS_OAUTH_SCOPES", []),
        require_authorized_user=_secret_bool("REQUIRE_AUTHORIZED_USER", False),
        allow_demo_mode=_secret_bool("ALLOW_DEMO_MODE", True),
        allow_manual_token_mode=_secret_bool("ALLOW_MANUAL_TOKEN_MODE", True),
    )


def new_oauth_state() -> str:
    state = secrets.token_urlsafe(32)
    st.session_state.oauth_state = state
    return state


def build_authorization_url(config: OAuthConfig, state: str) -> str:
    if not config.enabled:
        raise AuthError("OAuth2 de Canvas no está configurado en los secretos de Streamlit.")
    params: dict[str, Any] = {
        "client_id": config.client_id,
        "response_type": "code",
        "redirect_uri": config.redirect_uri,
        "state": state,
    }
    if config.scopes:
        # Canvas acepta los scopes separados por espacio.
        params["scope"] = " ".join(config.scopes)
    return f"{config.canvas_url}/login/oauth2/auth?{urlencode(params)}"


def exchange_code_for_token(config: OAuthConfig, code: str) -> dict[str, Any]:
    if not config.enabled:
        raise AuthError("OAuth2 de Canvas no está configurado.")
    payload = {
        "grant_type": "authorization_code",
        "client_id": config.client_id,
        "client_secret": config.client_secret,
        "redirect_uri": config.redirect_uri,
        "code": code,
    }
    try:
        response = requests.post(
            f"{config.canvas_url}/login/oauth2/token",
            data=payload,
            timeout=(15, 60),
            headers={"Accept": "application/json", "User-Agent": "AVE-Alerta-Temprana/1.3"},
        )
    except requests.RequestException as exc:
        raise AuthError("No fue posible completar la autenticación con Canvas.") from exc
    if response.status_code >= 400:
        raise AuthError("Canvas rechazó la autenticación. Revise la Developer Key, redirect URI y permisos.")
    data = response.json()
    if not data.get("access_token"):
        raise AuthError("Canvas no devolvió un token de acceso válido.")
    expires_in = int(data.get("expires_in") or 3600)
    data["expires_at"] = int(time.time()) + max(expires_in - 60, 60)
    return data


def refresh_access_token(config: OAuthConfig, refresh_token: str) -> dict[str, Any]:
    payload = {
        "grant_type": "refresh_token",
        "client_id": config.client_id,
        "client_secret": config.client_secret,
        "refresh_token": refresh_token,
    }
    try:
        response = requests.post(
            f"{config.canvas_url}/login/oauth2/token",
            data=payload,
            timeout=(15, 60),
            headers={"Accept": "application/json", "User-Agent": "AVE-Alerta-Temprana/1.3"},
        )
    except requests.RequestException as exc:
        raise AuthError("No fue posible renovar la sesión con Canvas.") from exc
    if response.status_code >= 400:
        raise AuthError("La sesión de Canvas expiró o fue revocada. Inicie sesión nuevamente.")
    data = response.json()
    expires_in = int(data.get("expires_in") or 3600)
    data["expires_at"] = int(time.time()) + max(expires_in - 60, 60)
    return data


def get_valid_canvas_token(config: OAuthConfig) -> str:
    tokens = st.session_state.get("oauth_tokens") or {}
    token = str(tokens.get("access_token") or st.session_state.get("canvas_token") or "")
    expires_at = int(tokens.get("expires_at") or 0)
    refresh_token = str(tokens.get("refresh_token") or "")
    if token and (not expires_at or expires_at > int(time.time())):
        return token
    if refresh_token:
        refreshed = refresh_access_token(config, refresh_token)
        # Si Canvas no devuelve refresh_token en cada renovación, se conserva el anterior.
        if not refreshed.get("refresh_token"):
            refreshed["refresh_token"] = refresh_token
        st.session_state.oauth_tokens = refreshed
        st.session_state.canvas_token = refreshed["access_token"]
        return str(refreshed["access_token"])
    return token


def current_actor() -> dict[str, Any]:
    profile = st.session_state.get("canvas_profile") or {}
    auth_user = st.session_state.get("auth_user") or {}
    return {
        "canvas_user_id": str(profile.get("id") or auth_user.get("canvas_user_id") or ""),
        "email": profile.get("primary_email") or auth_user.get("email"),
        "name": profile.get("name") or auth_user.get("full_name") or st.session_state.get("academic_advisor"),
        "role": st.session_state.get("user_role") or auth_user.get("role") or "sin_rol",
        "auth_method": st.session_state.get("auth_method") or "desconocido",
    }


def ensure_authorized(db: DatabaseService, profile: dict[str, Any], config: OAuthConfig) -> dict[str, Any]:
    canvas_user_id = str(profile.get("id") or "")
    email = profile.get("primary_email") or profile.get("login_id") or profile.get("email")
    name = profile.get("name") or profile.get("short_name") or "Usuario Canvas"

    record = db.get_authorized_user(canvas_user_id=canvas_user_id, email=email) if db.connected else None
    if record and not bool(record.get("is_active", True)):
        raise AuthError("Su usuario existe, pero está inactivo para esta aplicación.")
    if record:
        return record

    if config.require_authorized_user:
        raise AuthError("Su usuario de Canvas no está autorizado para utilizar esta aplicación. Solicite acceso al administrador.")

    # En modo piloto se permite entrar como asesor académico sin guardar credenciales sensibles.
    fallback = {
        "canvas_user_id": canvas_user_id,
        "email": email,
        "full_name": name,
        "role": "asesor_academico",
        "is_active": True,
        "temporary_access": True,
    }
    return fallback


def complete_oauth_login(config: OAuthConfig, db: DatabaseService) -> bool:
    params = st.query_params
    code = params.get("code")
    state = params.get("state")
    if not code:
        return False
    expected_state = st.session_state.get("oauth_state")
    if expected_state and state != expected_state:
        raise AuthError("La validación de seguridad del inicio de sesión falló. Intente nuevamente.")

    token_data = exchange_code_for_token(config, code)
    canvas = CanvasService(config.canvas_url, token_data["access_token"])
    result = canvas.test_connection()
    if not result.ok or not result.profile:
        raise AuthError(result.message)

    authorized = ensure_authorized(db, result.profile, config)
    st.session_state.demo_mode = False
    st.session_state.canvas_url = config.canvas_url
    st.session_state.canvas_token = token_data["access_token"]
    st.session_state.oauth_tokens = token_data
    st.session_state.canvas_profile = result.profile
    st.session_state.auth_user = authorized
    st.session_state.user_role = authorized.get("role") or "asesor_academico"
    st.session_state.authenticated = True

    if db.connected:
        db.upsert_user_login(result.profile, authorized)
        db.log_audit(
            action="login_canvas_oauth",
            entity_type="session",
            actor=current_actor(),
            payload={"auth_method": "canvas_oauth", "role": st.session_state.user_role},
        )
    st.query_params.clear()
    return True


def complete_manual_token_login(canvas_url: str, token: str, db: DatabaseService, config: OAuthConfig) -> bool:
    """Valida un token personal de Canvas sin almacenarlo fuera de la sesión activa."""
    if not config.allow_manual_token_mode:
        raise AuthError("El modo token manual está deshabilitado para esta aplicación.")
    canvas_url = (canvas_url or config.canvas_url or "https://uvg.instructure.com").strip().rstrip("/")
    token = (token or "").strip()
    if not token:
        raise AuthError("Ingrese un token de Canvas para continuar.")
    try:
        canvas = CanvasService(canvas_url, token)
        result = canvas.test_connection()
    except CanvasAPIError as exc:
        raise AuthError(str(exc)) from exc
    if not result.ok or not result.profile:
        raise AuthError(result.message or "No fue posible validar el token de Canvas.")

    authorized = ensure_authorized(db, result.profile, config)
    st.session_state.demo_mode = False
    st.session_state.canvas_url = canvas_url
    st.session_state.canvas_token = token
    st.session_state.oauth_tokens = {}
    st.session_state.canvas_profile = result.profile
    st.session_state.auth_user = authorized
    st.session_state.user_role = authorized.get("role") or "asesor_academico"
    st.session_state.authenticated = True
    st.session_state.auth_method = "manual_token"

    if db.connected:
        db.upsert_user_login(result.profile, authorized)
        db.log_audit(
            action="login_canvas_manual_token",
            entity_type="session",
            actor=current_actor(),
            payload={"auth_method": "manual_token", "role": st.session_state.user_role},
        )
    return True


def logout(db: DatabaseService | None = None) -> None:
    if db and db.connected:
        try:
            db.log_audit(action="logout", entity_type="session", actor=current_actor(), payload={})
        except Exception:
            pass
    for key in [
        "canvas_token",
        "oauth_tokens",
        "canvas_profile",
        "auth_user",
        "user_role",
        "authenticated",
        "auth_method",
        "courses",
        "sections",
        "analysis_df",
        "analysis_details",
        "analysis_diagnostics",
        "analysis_run_id",
    ]:
        st.session_state.pop(key, None)
    st.session_state.demo_mode = False
    st.query_params.clear()
