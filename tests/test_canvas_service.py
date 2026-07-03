import requests
import pytest

from services.canvas_service import CanvasAPIError, CanvasService


def test_submissions_are_requested_in_small_batches(monkeypatch):
    service = CanvasService("https://example.instructure.com", "token")
    calls = []
    progress = []

    def fake_get_paginated(path, params=None, max_pages=100):
        calls.append((path, list(params or []), max_pages))
        return []

    monkeypatch.setattr(service, "get_paginated", fake_get_paginated)
    service.list_submissions(
        99,
        student_ids=[str(value) for value in range(60)],
        assignment_ids=[str(value) for value in range(41)],
        progress_callback=lambda done, total: progress.append((done, total)),
    )

    assert len(calls) == 6  # 3 lotes de estudiantes x 2 lotes de actividades
    assert progress[-1] == (6, 6)
    for _, params, _ in calls:
        student_values = [value for key, value in params if key == "student_ids[]"]
        assignment_values = [value for key, value in params if key == "assignment_ids[]"]
        include_values = [value for key, value in params if key == "include[]"]
        assert len(student_values) <= 25
        assert len(assignment_values) <= 40
        assert include_values == []


def test_timeout_message_is_friendly(monkeypatch):
    service = CanvasService("https://example.instructure.com", "token")

    def raise_timeout(*args, **kwargs):
        raise requests.exceptions.ReadTimeout("technical pool detail")

    monkeypatch.setattr(service.session, "request", raise_timeout)
    with pytest.raises(CanvasAPIError) as error:
        service.get("/api/v1/users/self/profile")

    message = str(error.value)
    assert "tardó demasiado" in message
    assert "technical pool detail" not in message


def test_course_student_directory_requests_identity_fields(monkeypatch):
    service = CanvasService("https://example.instructure.com", "token")
    captured = {}

    def fake_get_paginated(path, params=None, max_pages=100):
        captured["path"] = path
        captured["params"] = list(params or [])
        return []

    monkeypatch.setattr(service, "get_paginated", fake_get_paginated)
    service.list_course_students(77)

    assert captured["path"] == "/api/v1/courses/77/users"
    include_values = [value for key, value in captured["params"] if key == "include[]"]
    assert "email" in include_values
    assert "enrollments" in include_values
