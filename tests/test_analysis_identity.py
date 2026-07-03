from datetime import date

import pandas as pd

from services.analysis_service import AnalysisService


class FakeCanvas:
    def list_enrollments(self, course_id, section_id=None):
        return [
            {
                "user_id": 100,
                "sis_user_id": "cas262786",
                "user": {"id": 100, "name": "Adriana Benard Urizar"},
                "grades": {"current_score": 80},
                "last_activity_at": "2026-06-15T12:00:00Z",
            }
        ]

    def list_course_students(self, course_id):
        return []

    def list_assignments(self, course_id):
        return [
            {
                "id": 1,
                "name": "Actividad 1",
                "published": True,
                "submission_types": ["online_text_entry"],
                "points_possible": 10,
                "position": 1,
                "due_at": "2026-06-15T23:59:00Z",
            }
        ]

    def list_submissions(self, course_id, section_id=None, **kwargs):
        return []


def test_analysis_uses_top_level_enrollment_sis_user_id():
    service = AnalysisService(FakeCanvas())
    dataframe, _, diagnostics = service.analyze_course(
        course={"id": 5, "name": "Curso", "start_at": "2026-06-09T00:00:00Z"},
        section_id=None,
        section_name="Todas",
        week=1,
        analysis_date=date(2026, 6, 15),
        include_page_views=False,
        include_zero_point=False,
        latest_messages=pd.DataFrame(),
        previous_history=pd.DataFrame(),
    )
    assert dataframe.loc[0, "carne"] == "262786"
    assert dataframe.loc[0, "canvas_sis_user_id"] == "cas262786"
    assert diagnostics["identity_coverage_from_enrollments"] == 1
