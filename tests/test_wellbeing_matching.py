import pandas as pd

from utils.data_cleaning import merge_wellbeing, normalize_wellbeing_dataframe


def wellbeing_base():
    return normalize_wellbeing_dataframe(
        pd.DataFrame(
            [
                {
                    "Carné": "262786",
                    "Nombre completo": "Adriana Benard Urizar",
                    "Asesor de bienestar": "Ana Leticia Montúfar Rios",
                },
                {
                    "Carné": "262620",
                    "Nombre completo": "Alejandro Xavier Martínez Meza",
                    "Asesor de bienestar": "Flor De María Morales Torres",
                },
            ]
        )
    )


def test_matches_top_level_sis_style_carne():
    analysis = pd.DataFrame(
        [
            {
                "canvas_user_id": "10",
                "carne": "cas262786",
                "student_name": "Adriana Benard Urizar",
                "email": "",
            }
        ]
    )
    result = merge_wellbeing(analysis, wellbeing_base())
    assert result.loc[0, "asesor_bienestar"] == "Ana Leticia Montúfar Rios"
    assert result.loc[0, "wellbeing_match_method"] == "Carné"
    assert result.loc[0, "carne"] == "262786"


def test_matches_sortable_canvas_name_when_identifier_is_missing():
    analysis = pd.DataFrame(
        [
            {
                "canvas_user_id": "11",
                "carne": "canvas-11",
                "student_name": "Martínez Meza, Alejandro Xavier",
                "email": "",
            }
        ]
    )
    result = merge_wellbeing(analysis, wellbeing_base())
    assert result.loc[0, "asesor_bienestar"] == "Flor De María Morales Torres"
    assert result.loc[0, "wellbeing_match_method"] == "Nombre reordenado"
    assert result.loc[0, "carne"] == "262620"


def test_unmatched_student_remains_unassigned():
    analysis = pd.DataFrame(
        [{"canvas_user_id": "12", "carne": "canvas-12", "student_name": "Persona Desconocida"}]
    )
    result = merge_wellbeing(analysis, wellbeing_base())
    assert result.loc[0, "asesor_bienestar"] == "Sin asignar"
    assert not bool(result.loc[0, "wellbeing_record_found"])
