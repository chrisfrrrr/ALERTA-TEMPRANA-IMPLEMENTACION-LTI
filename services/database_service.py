from __future__ import annotations

import math
from datetime import datetime, timedelta, timezone
from typing import Any, Iterable

import pandas as pd


class DatabaseError(RuntimeError):
    pass


def _json_safe(value: Any) -> Any:
    if value is None or value is pd.NA:
        return None
    if isinstance(value, float) and (math.isnan(value) or math.isinf(value)):
        return None
    if isinstance(value, (pd.Timestamp, datetime)):
        dt = value.to_pydatetime() if isinstance(value, pd.Timestamp) else value
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.isoformat()
    if hasattr(value, "item"):
        try:
            return value.item()
        except Exception:
            pass
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_json_safe(item) for item in value]
    return value


def _records(df_or_records: pd.DataFrame | Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    if isinstance(df_or_records, pd.DataFrame):
        values = df_or_records.to_dict(orient="records")
    else:
        values = list(df_or_records)
    return [_json_safe(record) for record in values]


class DatabaseService:
    """Capa de persistencia Supabase. No expone la clave al navegador."""

    def __init__(self, url: str | None = None, service_role_key: str | None = None, enabled: bool = True) -> None:
        self.url = (url or "").strip()
        self.service_role_key = (service_role_key or "").strip()
        self.enabled = bool(enabled and self.url and self.service_role_key)
        self.client = None
        self.last_error: str | None = None
        if self.enabled:
            try:
                from supabase import create_client

                self.client = create_client(self.url, self.service_role_key)
            except Exception as exc:  # pragma: no cover - depende del entorno
                self.enabled = False
                self.last_error = str(exc)

    @property
    def connected(self) -> bool:
        return bool(self.enabled and self.client is not None)

    def test_connection(self) -> tuple[bool, str]:
        if not self.connected:
            return False, self.last_error or "Supabase no está configurado."
        try:
            self.client.table("risk_configuration").select("id").limit(1).execute()
            return True, "Conexión con Supabase correcta."
        except Exception as exc:
            self.last_error = str(exc)
            return False, f"No fue posible consultar Supabase: {exc}"

    def upsert_students(self, students: pd.DataFrame) -> int:
        if not self.connected or students.empty:
            return 0
        records = []
        for row in students.to_dict(orient="records"):
            records.append(
                {
                    "carne": str(row.get("carne") or "").replace(".0", ""),
                    "full_name": row.get("nombre_completo") or row.get("nombre") or "",
                    "email": row.get("correo") or None,
                    "career": row.get("carrera") or None,
                    "canvas_user_id": row.get("canvas_user_id") or None,
                    "wellbeing_status": row.get("estado_bienestar") or None,
                    "wellbeing_stage": row.get("etapa_bienestar") or None,
                    "special_requests": row.get("solicitudes_particulares") or None,
                    "regular_cycle_risk": row.get("riesgo_ciclo_regular") or None,
                    "updated_at": datetime.now(timezone.utc).isoformat(),
                }
            )
        try:
            self.client.table("students").upsert(_json_safe(records), on_conflict="carne").execute()
            return len(records)
        except Exception as exc:
            raise DatabaseError(f"No se pudieron registrar los estudiantes: {exc}") from exc

    def upsert_wellbeing_advisors(self, students: pd.DataFrame) -> int:
        if not self.connected or students.empty or "asesor_bienestar" not in students.columns:
            return 0
        names = sorted(
            {
                str(value).strip()
                for value in students["asesor_bienestar"].dropna().tolist()
                if str(value).strip() and str(value).strip() != "Sin asignar"
            }
        )
        if not names:
            return 0
        try:
            records = [{"name": name, "active": True} for name in names]
            self.client.table("wellbeing_advisors").upsert(records, on_conflict="name").execute()
            return len(records)
        except Exception as exc:
            raise DatabaseError(f"No se pudieron registrar los asesores: {exc}") from exc

    def sync_wellbeing_assignments(self, students: pd.DataFrame) -> int:
        if not self.connected or students.empty:
            return 0
        try:
            student_rows = self.client.table("students").select("id,carne").execute().data or []
            advisor_rows = self.client.table("wellbeing_advisors").select("id,name").execute().data or []
            student_map = {str(row["carne"]): row["id"] for row in student_rows}
            advisor_map = {str(row["name"]): row["id"] for row in advisor_rows}
            records = []
            for row in students.to_dict(orient="records"):
                carne = str(row.get("carne") or "").replace(".0", "")
                advisor_name = str(row.get("asesor_bienestar") or "").strip()
                if carne in student_map and advisor_name in advisor_map:
                    records.append(
                        {
                            "student_id": student_map[carne],
                            "advisor_id": advisor_map[advisor_name],
                            "active": True,
                            "assigned_at": datetime.now(timezone.utc).date().isoformat(),
                        }
                    )
            if records:
                self.client.table("student_wellbeing_assignments").upsert(
                    records, on_conflict="student_id,advisor_id"
                ).execute()
            return len(records)
        except Exception as exc:
            raise DatabaseError(f"No se pudieron sincronizar las asignaciones: {exc}") from exc

    def create_analysis_run(self, payload: dict[str, Any]) -> str | None:
        if not self.connected:
            return None
        try:
            result = self.client.table("analysis_runs").insert(_json_safe(payload)).execute()
            data = result.data or []
            return str(data[0]["id"]) if data else None
        except Exception as exc:
            raise DatabaseError(f"No se pudo crear la ejecución de análisis: {exc}") from exc

    def save_snapshots(self, run_id: str | None, dataframe: pd.DataFrame) -> int:
        if not self.connected or not run_id or dataframe.empty:
            return 0
        snapshot_fields = {
            "student_id",
            "canvas_user_id",
            "carne",
            "student_name",
            "email",
            "career",
            "course_id",
            "course_name",
            "section_id",
            "section_name",
            "week_number",
            "total_weeks",
            "total_activities",
            "expected_activities",
            "completed_activities",
            "completed_expected",
            "pending_count",
            "late_count",
            "early_count",
            "completion_percentage",
            "average_grade",
            "weekly_sessions",
            "inactivity_hours",
            "activity_risk",
            "grade_risk",
            "punctuality_risk",
            "access_risk",
            "communication_risk",
            "overall_risk",
            "intervention_priority",
            "pending_assignments",
            "reasons",
            "advisor_name",
            "analysis_cutoff",
        }
        records = []
        for row in dataframe.to_dict(orient="records"):
            record = {key: row.get(key) for key in snapshot_fields}
            record["analysis_run_id"] = run_id
            record["carne"] = str(record.get("carne") or "")
            records.append(_json_safe(record))
        try:
            for start in range(0, len(records), 250):
                self.client.table("student_snapshots").insert(records[start : start + 250]).execute()
            return len(records)
        except Exception as exc:
            raise DatabaseError(f"No se pudieron registrar los resultados del análisis: {exc}") from exc

    def save_message(self, payload: dict[str, Any]) -> str | None:
        if not self.connected:
            return None
        try:
            result = self.client.table("messages").insert(_json_safe(payload)).execute()
            data = result.data or []
            return str(data[0]["id"]) if data else None
        except Exception as exc:
            raise DatabaseError(f"No se pudo registrar el mensaje: {exc}") from exc

    def update_message_response(
        self,
        message_id: str,
        responded_at: str,
        response_hours: float,
        response_excerpt: str | None = None,
    ) -> None:
        if not self.connected:
            return
        try:
            self.client.table("messages").update(
                {
                    "status": "responded",
                    "responded_at": responded_at,
                    "response_hours": response_hours,
                    "response_excerpt": response_excerpt,
                }
            ).eq("id", message_id).execute()
        except Exception as exc:
            raise DatabaseError(f"No se pudo actualizar la respuesta: {exc}") from exc

    def get_latest_messages(self, canvas_user_ids: list[str] | None = None) -> pd.DataFrame:
        if not self.connected:
            return pd.DataFrame()
        try:
            query = self.client.table("messages").select("*").order("sent_at", desc=True).limit(2000)
            if canvas_user_ids:
                query = query.in_("canvas_user_id", [str(value) for value in canvas_user_ids])
            data = query.execute().data or []
            if not data:
                return pd.DataFrame()
            df = pd.DataFrame(data)
            if "canvas_user_id" in df.columns:
                df["canvas_user_id"] = df["canvas_user_id"].astype(str)
                df = df.drop_duplicates(["canvas_user_id", "course_id"], keep="first")
            return df
        except Exception as exc:
            self.last_error = str(exc)
            return pd.DataFrame()

    def get_pending_messages(self) -> pd.DataFrame:
        if not self.connected:
            return pd.DataFrame()
        try:
            data = (
                self.client.table("messages")
                .select("*")
                .eq("status", "sent")
                .order("sent_at", desc=True)
                .limit(500)
                .execute()
                .data
                or []
            )
            df = pd.DataFrame(data)
            if not df.empty and "canvas_conversation_id" in df.columns:
                df = df[df["canvas_conversation_id"].notna() & (df["canvas_conversation_id"].astype(str) != "")]
            return df
        except Exception as exc:
            self.last_error = str(exc)
            return pd.DataFrame()

    def save_referral_batch(self, payload: dict[str, Any]) -> str | None:
        if not self.connected:
            return None
        try:
            result = self.client.table("referral_batches").insert(_json_safe(payload)).execute()
            data = result.data or []
            return str(data[0]["id"]) if data else None
        except Exception as exc:
            raise DatabaseError(f"No se pudo registrar el paquete de derivación: {exc}") from exc

    def save_referrals(self, batch_id: str | None, records: list[dict[str, Any]]) -> int:
        if not self.connected or not records:
            return 0
        payload = []
        for record in records:
            item = dict(record)
            item["batch_id"] = batch_id
            payload.append(_json_safe(item))
        try:
            self.client.table("referrals").insert(payload).execute()
            return len(payload)
        except Exception as exc:
            raise DatabaseError(f"No se pudieron registrar las derivaciones: {exc}") from exc

    def get_recent_referrals(self, carnes: list[str], cooldown_days: int = 14) -> pd.DataFrame:
        if not self.connected or not carnes:
            return pd.DataFrame()
        since = (datetime.now(timezone.utc) - timedelta(days=cooldown_days)).isoformat()
        try:
            data = (
                self.client.table("referrals")
                .select("*")
                .in_("carne", [str(value) for value in carnes])
                .gte("created_at", since)
                .neq("status", "closed")
                .execute()
                .data
                or []
            )
            return pd.DataFrame(data)
        except Exception as exc:
            self.last_error = str(exc)
            return pd.DataFrame()

    def get_snapshot_history(
        self,
        *,
        carne: str | None = None,
        course_id: str | int | None = None,
        limit: int = 5000,
    ) -> pd.DataFrame:
        if not self.connected:
            return pd.DataFrame()
        try:
            query = self.client.table("student_snapshots").select("*").order("created_at", desc=False).limit(limit)
            if carne:
                query = query.eq("carne", str(carne))
            if course_id:
                query = query.eq("course_id", str(course_id))
            return pd.DataFrame(query.execute().data or [])
        except Exception as exc:
            self.last_error = str(exc)
            return pd.DataFrame()



    def get_authorized_user(self, *, canvas_user_id: str | None = None, email: str | None = None) -> dict[str, Any] | None:
        """Devuelve el rol interno autorizado para un usuario de Canvas.

        Si la tabla todavía no existe, no bloquea la aplicación en modo piloto; el
        control estricto se activa con REQUIRE_AUTHORIZED_USER=true.
        """
        if not self.connected:
            return None
        try:
            if canvas_user_id:
                data = (
                    self.client.table("authorized_users")
                    .select("*")
                    .eq("canvas_user_id", str(canvas_user_id))
                    .limit(1)
                    .execute()
                    .data
                    or []
                )
                if data:
                    return data[0]
            if email:
                data = (
                    self.client.table("authorized_users")
                    .select("*")
                    .ilike("email", str(email))
                    .limit(1)
                    .execute()
                    .data
                    or []
                )
                if data:
                    return data[0]
            return None
        except Exception as exc:
            self.last_error = str(exc)
            return None

    def upsert_user_login(self, profile: dict[str, Any], authorized: dict[str, Any]) -> None:
        if not self.connected:
            return
        canvas_user_id = str(profile.get("id") or authorized.get("canvas_user_id") or "")
        email = profile.get("primary_email") or profile.get("login_id") or authorized.get("email")
        full_name = profile.get("name") or profile.get("short_name") or authorized.get("full_name") or "Usuario Canvas"
        if not canvas_user_id and not email:
            return
        try:
            payload = {
                "canvas_user_id": canvas_user_id or None,
                "email": email or None,
                "full_name": full_name,
                "role": authorized.get("role") or "asesor_academico",
                "is_active": bool(authorized.get("is_active", True)),
                "last_login_at": datetime.now(timezone.utc).isoformat(),
            }
            # Solo crea/actualiza cuando la tabla existe; si falla por políticas o estructura, no cancela el login.
            self.client.table("authorized_users").upsert(payload, on_conflict="canvas_user_id").execute()
        except Exception as exc:
            self.last_error = str(exc)

    def list_authorized_users(self, limit: int = 1000) -> pd.DataFrame:
        if not self.connected:
            return pd.DataFrame()
        try:
            data = (
                self.client.table("authorized_users")
                .select("*")
                .order("full_name", desc=False)
                .limit(limit)
                .execute()
                .data
                or []
            )
            return pd.DataFrame(data)
        except Exception as exc:
            self.last_error = str(exc)
            return pd.DataFrame()

    def save_authorized_user(self, payload: dict[str, Any]) -> None:
        if not self.connected:
            return
        record = dict(payload)
        record["updated_at"] = datetime.now(timezone.utc).isoformat()
        try:
            conflict_field = "canvas_user_id" if record.get("canvas_user_id") else "email"
            self.client.table("authorized_users").upsert(_json_safe(record), on_conflict=conflict_field).execute()
        except Exception as exc:
            raise DatabaseError(f"No se pudo guardar el usuario autorizado: {exc}") from exc

    def log_audit(
        self,
        *,
        action: str,
        entity_type: str | None = None,
        entity_id: str | None = None,
        actor: dict[str, Any] | None = None,
        payload: dict[str, Any] | None = None,
    ) -> None:
        if not self.connected:
            return
        actor = actor or {}
        record = {
            "action": action,
            "entity_type": entity_type,
            "entity_id": entity_id,
            "actor_canvas_user_id": actor.get("canvas_user_id"),
            "actor_email": actor.get("email"),
            "actor_name": actor.get("name"),
            "actor_role": actor.get("role"),
            "payload": _json_safe(payload or {}),
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        try:
            self.client.table("audit_log").insert(_json_safe(record)).execute()
        except Exception as exc:
            self.last_error = str(exc)


    def get_audit_log(self, limit: int = 500) -> pd.DataFrame:
        if not self.connected:
            return pd.DataFrame()
        try:
            data = (
                self.client.table("audit_log")
                .select("*")
                .order("created_at", desc=True)
                .limit(limit)
                .execute()
                .data
                or []
            )
            return pd.DataFrame(data)
        except Exception as exc:
            self.last_error = str(exc)
            return pd.DataFrame()

    def load_risk_config(self, config_name: str = "default") -> dict[str, Any] | None:
        if not self.connected:
            return None
        try:
            data = (
                self.client.table("risk_configuration")
                .select("*")
                .eq("config_name", config_name)
                .limit(1)
                .execute()
                .data
                or []
            )
            return data[0] if data else None
        except Exception as exc:
            self.last_error = str(exc)
            return None

    def save_risk_config(self, config: dict[str, Any], config_name: str = "default") -> None:
        if not self.connected:
            return
        payload = {key: _json_safe(value) for key, value in config.items()}
        payload["config_name"] = config_name
        payload["updated_at"] = datetime.now(timezone.utc).isoformat()
        try:
            self.client.table("risk_configuration").upsert(payload, on_conflict="config_name").execute()
        except Exception as exc:
            raise DatabaseError(f"No se pudo guardar la configuración de riesgo: {exc}") from exc

    def get_referrals(self, limit: int = 1000) -> pd.DataFrame:
        if not self.connected:
            return pd.DataFrame()
        try:
            data = self.client.table("referrals").select("*").order("created_at", desc=True).limit(limit).execute().data or []
            return pd.DataFrame(data)
        except Exception as exc:
            self.last_error = str(exc)
            return pd.DataFrame()
