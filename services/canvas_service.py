from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Callable, Iterable, Sequence
from urllib.parse import urljoin

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry


class CanvasAPIError(RuntimeError):
    """Error legible para el usuario al consultar la API de Canvas."""


@dataclass(slots=True)
class CanvasConnectionResult:
    ok: bool
    message: str
    profile: dict[str, Any] | None = None


def _chunks(values: Sequence[str], size: int) -> list[list[str]]:
    if not values:
        return [[]]
    return [list(values[index : index + size]) for index in range(0, len(values), size)]


class CanvasService:
    """Cliente robusto para la API REST de Canvas.

    Las consultas de lectura se reintentan automáticamente y las entregas se
    solicitan en lotes pequeños para evitar respuestas demasiado pesadas.
    """

    def __init__(
        self,
        base_url: str,
        token: str,
        timeout: int | tuple[int, int] = (15, 120),
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.token = token.strip()
        self.timeout = timeout
        self.session = requests.Session()
        self.session.headers.update(
            {
                "Authorization": f"Bearer {self.token}",
                "Accept": "application/json",
                "User-Agent": "AVE-Alerta-Temprana/1.3",
            }
        )

        # Solo se reintentan operaciones idempotentes. Los mensajes POST no se
        # reintentan para evitar envíos duplicados.
        retry_policy = Retry(
            total=3,
            connect=3,
            read=3,
            status=3,
            backoff_factor=1.0,
            status_forcelist=(429, 500, 502, 503, 504),
            allowed_methods=frozenset({"GET", "HEAD", "OPTIONS"}),
            respect_retry_after_header=True,
            raise_on_status=False,
        )
        adapter = HTTPAdapter(max_retries=retry_policy, pool_connections=20, pool_maxsize=20)
        self.session.mount("https://", adapter)
        self.session.mount("http://", adapter)

    def _url(self, path: str) -> str:
        if path.startswith("http"):
            return path
        return urljoin(f"{self.base_url}/", path.lstrip("/"))

    def _request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | list[tuple[str, Any]] | None = None,
        data: dict[str, Any] | list[tuple[str, Any]] | None = None,
        json: dict[str, Any] | None = None,
        timeout: int | tuple[int, int] | None = None,
    ) -> requests.Response:
        if not self.token:
            raise CanvasAPIError("Debe ingresar un token de Canvas.")
        if not self.base_url.startswith(("https://", "http://")):
            raise CanvasAPIError("La URL de Canvas no es válida.")

        try:
            response = self.session.request(
                method,
                self._url(path),
                params=params,
                data=data,
                json=json,
                timeout=timeout or self.timeout,
            )
        except requests.exceptions.ReadTimeout as exc:
            raise CanvasAPIError(
                "Canvas tardó demasiado en responder. La aplicación ya amplió el tiempo de espera y "
                "reintenta automáticamente; vuelva a ejecutar el análisis o seleccione una sección específica."
            ) from exc
        except requests.exceptions.ConnectTimeout as exc:
            raise CanvasAPIError(
                "No fue posible establecer conexión con Canvas dentro del tiempo esperado. Intente nuevamente."
            ) from exc
        except requests.exceptions.ConnectionError as exc:
            raise CanvasAPIError(
                "No fue posible comunicarse con Canvas. Verifique la conexión a internet y vuelva a intentarlo."
            ) from exc
        except requests.RequestException as exc:
            raise CanvasAPIError("Canvas no pudo completar la solicitud en este momento.") from exc

        if response.status_code >= 400:
            detail = response.text[:400]
            try:
                payload = response.json()
                if isinstance(payload, dict):
                    detail = str(payload.get("errors") or payload.get("message") or payload)
            except ValueError:
                pass

            if response.status_code in {401, 403}:
                raise CanvasAPIError(
                    f"Canvas rechazó la solicitud ({response.status_code}). Revise el token y los permisos asignados."
                )
            if response.status_code == 429:
                raise CanvasAPIError(
                    "Canvas limitó temporalmente la cantidad de consultas. Espere un momento y vuelva a intentarlo."
                )
            if response.status_code >= 500:
                raise CanvasAPIError(
                    "Canvas presentó una interrupción temporal al procesar la consulta. Vuelva a intentarlo en unos minutos."
                )
            raise CanvasAPIError(f"Canvas no pudo completar la consulta ({response.status_code}): {detail}")
        return response

    def get(self, path: str, params: dict[str, Any] | list[tuple[str, Any]] | None = None) -> Any:
        return self._request("GET", path, params=params).json()

    def get_paginated(
        self,
        path: str,
        params: dict[str, Any] | list[tuple[str, Any]] | None = None,
        max_pages: int = 100,
    ) -> list[Any]:
        items: list[Any] = []
        url = self._url(path)
        current_params = params
        pages = 0
        visited: set[str] = set()

        while url and pages < max_pages:
            if url in visited:
                break
            visited.add(url)
            response = self._request("GET", url, params=current_params)
            payload = response.json()
            if isinstance(payload, list):
                items.extend(payload)
            elif isinstance(payload, dict):
                items.append(payload)
            else:
                break
            url = response.links.get("next", {}).get("url")
            current_params = None
            pages += 1
        return items

    def test_connection(self) -> CanvasConnectionResult:
        try:
            profile = self.get("/api/v1/users/self/profile")
            name = profile.get("name") or profile.get("short_name") or "usuario"
            return CanvasConnectionResult(True, f"Conexión correcta como {name}.", profile)
        except CanvasAPIError as exc:
            return CanvasConnectionResult(False, str(exc), None)

    def list_courses(self) -> list[dict[str, Any]]:
        params: list[tuple[str, Any]] = [
            ("per_page", 100),
            ("state[]", "available"),
            ("state[]", "completed"),
            ("include[]", "term"),
            ("include[]", "total_students"),
            ("include[]", "sections"),
        ]
        courses = self.get_paginated("/api/v1/courses", params=params)
        return [course for course in courses if isinstance(course, dict) and course.get("id")]

    def list_sections(self, course_id: int | str) -> list[dict[str, Any]]:
        params: list[tuple[str, Any]] = [("per_page", 100), ("include[]", "total_students")]
        return self.get_paginated(f"/api/v1/courses/{course_id}/sections", params=params)

    def list_enrollments(
        self,
        course_id: int | str,
        section_id: int | str | None = None,
    ) -> list[dict[str, Any]]:
        if section_id:
            path = f"/api/v1/sections/{section_id}/enrollments"
        else:
            path = f"/api/v1/courses/{course_id}/enrollments"
        params: list[tuple[str, Any]] = [
            ("per_page", 100),
            ("type[]", "StudentEnrollment"),
            ("state[]", "active"),
            ("include[]", "total_scores"),
            ("include[]", "avatar_url"),
        ]
        return self.get_paginated(path, params=params)

    def list_course_students(self, course_id: int | str) -> list[dict[str, Any]]:
        """Obtiene el directorio de estudiantes con identificadores institucionales.

        El endpoint de inscripciones no siempre coloca ``sis_user_id`` o
        ``login_id`` dentro del objeto ``user``. Esta consulta complementaria
        permite vincular correctamente el carné con la base de bienestar.
        """
        params: list[tuple[str, Any]] = [
            ("per_page", 100),
            ("enrollment_type[]", "student"),
            ("enrollment_state[]", "active"),
            ("include[]", "email"),
            ("include[]", "enrollments"),
            ("include[]", "avatar_url"),
        ]
        return self.get_paginated(f"/api/v1/courses/{course_id}/users", params=params)

    def list_assignments(self, course_id: int | str) -> list[dict[str, Any]]:
        params: list[tuple[str, Any]] = [
            ("per_page", 100),
            ("include[]", "all_dates"),
            ("order_by", "due_at"),
        ]
        return self.get_paginated(f"/api/v1/courses/{course_id}/assignments", params=params)

    def _submission_batch(
        self,
        path: str,
        student_ids: Sequence[str],
        assignment_ids: Sequence[str],
    ) -> list[dict[str, Any]]:
        params: list[tuple[str, Any]] = [
            ("per_page", 50),
            ("grouped", "true"),
            ("enrollment_state", "active"),
        ]
        for student_id in student_ids:
            params.append(("student_ids[]", student_id))
        for assignment_id in assignment_ids:
            params.append(("assignment_ids[]", assignment_id))
        return self.get_paginated(path, params=params, max_pages=25)

    def list_submissions(
        self,
        course_id: int | str,
        section_id: int | str | None = None,
        *,
        student_ids: Iterable[int | str] | None = None,
        assignment_ids: Iterable[int | str] | None = None,
        progress_callback: Callable[[int, int], None] | None = None,
    ) -> list[dict[str, Any]]:
        """Obtiene entregas en lotes pequeños para reducir tiempos de espera.

        No solicita objetos de usuario ni de actividad dentro de cada entrega,
        porque ya fueron consultados por separado durante el análisis.
        """
        if section_id:
            path = f"/api/v1/sections/{section_id}/students/submissions"
        else:
            path = f"/api/v1/courses/{course_id}/students/submissions"

        students = [str(value) for value in (student_ids or []) if str(value)]
        assignments = [str(value) for value in (assignment_ids or []) if str(value)]
        if not students:
            students = ["all"]

        # Lotes conservadores: evitan una sola respuesta con miles de entregas.
        student_batches = _chunks(students, 25) if students != ["all"] else [["all"]]
        assignment_batches = _chunks(assignments, 40) if assignments else [[]]
        total_batches = len(student_batches) * len(assignment_batches)
        completed_batches = 0
        results: list[dict[str, Any]] = []

        for student_batch in student_batches:
            for assignment_batch in assignment_batches:
                results.extend(self._submission_batch(path, student_batch, assignment_batch))
                completed_batches += 1
                if progress_callback:
                    progress_callback(completed_batches, total_batches)
        return results

    def list_page_views(
        self,
        user_id: int | str,
        start_time: datetime,
        end_time: datetime,
    ) -> list[dict[str, Any]]:
        params = {
            "per_page": 100,
            "start_time": start_time.isoformat(),
            "end_time": end_time.isoformat(),
        }
        return self.get_paginated(f"/api/v1/users/{user_id}/page_views", params=params, max_pages=25)

    def send_message(
        self,
        recipient_ids: list[int | str],
        subject: str,
        body: str,
        *,
        force_new: bool = True,
    ) -> list[dict[str, Any]]:
        if not recipient_ids:
            raise CanvasAPIError("No se seleccionaron destinatarios.")
        data: list[tuple[str, Any]] = [("subject", subject), ("body", body)]
        data.append(("force_new", str(force_new).lower()))
        data.append(("group_conversation", "false"))
        for recipient in recipient_ids:
            data.append(("recipients[]", str(recipient)))
        payload = self._request("POST", "/api/v1/conversations", data=data).json()
        if isinstance(payload, list):
            return payload
        return [payload]

    def get_conversation(self, conversation_id: int | str) -> dict[str, Any]:
        return self.get(f"/api/v1/conversations/{conversation_id}", params={"include_all_conversation_ids": "true"})

    def count_sessions(
        self,
        page_views: list[dict[str, Any]],
        *,
        inactivity_gap_minutes: int = 30,
        course_id: int | str | None = None,
    ) -> int:
        timestamps: list[datetime] = []
        course_token = f"/courses/{course_id}/" if course_id else None
        for view in page_views:
            url = str(view.get("url") or "")
            if course_token and course_token not in url:
                context_id = str(view.get("context_id") or "")
                if context_id != str(course_id):
                    continue
            value = view.get("created_at")
            if not value:
                continue
            try:
                timestamps.append(datetime.fromisoformat(str(value).replace("Z", "+00:00")))
            except ValueError:
                continue
        if not timestamps:
            return 0
        timestamps.sort()
        sessions = 1
        for previous, current in zip(timestamps, timestamps[1:]):
            if (current - previous).total_seconds() > inactivity_gap_minutes * 60:
                sessions += 1
        return sessions

    def fetch_page_view_sessions(
        self,
        user_ids: list[int | str],
        start_time: datetime,
        end_time: datetime,
        course_id: int | str,
        progress_callback: Callable[[int, int], None] | None = None,
    ) -> tuple[dict[str, int | None], dict[str, str]]:
        """Consulta sesiones una a una; conserva errores de permiso por estudiante."""
        sessions: dict[str, int | None] = {}
        errors: dict[str, str] = {}
        total = len(user_ids)
        for index, user_id in enumerate(user_ids, start=1):
            try:
                views = self.list_page_views(user_id, start_time, end_time)
                sessions[str(user_id)] = self.count_sessions(views, course_id=course_id)
            except CanvasAPIError as exc:
                sessions[str(user_id)] = None
                errors[str(user_id)] = str(exc)
            if progress_callback:
                progress_callback(index, total)
        return sessions, errors
