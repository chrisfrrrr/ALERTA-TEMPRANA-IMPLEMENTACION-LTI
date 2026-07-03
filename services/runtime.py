from __future__ import annotations

import streamlit as st

from services.database_service import DatabaseService


@st.cache_resource(show_spinner=False)
def _create_database(url: str, key: str, enabled: bool) -> DatabaseService:
    return DatabaseService(url, key, enabled)


def get_database() -> DatabaseService:
    try:
        url = str(st.secrets.get("SUPABASE_URL", ""))
        key = str(st.secrets.get("SUPABASE_SERVICE_ROLE_KEY", st.secrets.get("SUPABASE_KEY", "")))
        enabled = bool(st.secrets.get("USE_SUPABASE", True))
    except Exception:
        url, key, enabled = "", "", False
    return _create_database(url, key, enabled)
