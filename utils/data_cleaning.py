from __future__ import annotations

from collections import defaultdict
from pathlib import Path
from typing import Any, BinaryIO, Iterable
import re
import unicodedata

import pandas as pd

from utils.ids import extract_carne


STANDARD_COLUMNS = [
    "carne",
    "nombre_completo",
    "correo",
    "carrera",
    "asesor_bienestar",
    "estado_bienestar",
    "etapa_bienestar",
    "solicitudes_particulares",
    "riesgo_ciclo_regular",
]


def _clean_text(value: Any) -> str:
    if value is None or value is pd.NA:
        return ""
    text = re.sub(r"\s+", " ", str(value)).strip()
    return "" if text in {"0", "0.0", "nan", "None", "<NA>"} else text


def _ascii_key(value: Any) -> str:
    text = _clean_text(value).lower()
    text = unicodedata.normalize("NFKD", text)
    text = "".join(char for char in text if not unicodedata.combining(char))
    return re.sub(r"[^a-z0-9]+", " ", text).strip()


def _name_key(value: Any, *, sort_tokens: bool = False) -> str:
    tokens = [token for token in _ascii_key(value).split() if token]
    if sort_tokens:
        tokens = sorted(tokens)
    return " ".join(tokens)


def _email_key(value: Any) -> str:
    return _clean_text(value).lower().replace(" ", "")


def _carne_candidates(value: Any) -> list[str]:
    """Genera variantes seguras del carné sin usar el ID interno de Canvas.

    Canvas puede devolver el identificador como ``cas262786``, ``262786.0`` o
    con un prefijo SIS. Se conserva la coincidencia exacta y, para cadenas
    largas, también los últimos seis dígitos.
    """
    text = _clean_text(value)
    if not text or text.lower().startswith("canvas-"):
        return []

    candidates: list[str] = []
    extracted = extract_carne(text)
    if extracted:
        candidates.append(extracted)
    for group in re.findall(r"\d+", text):
        if group:
            candidates.append(group)
            if len(group) > 6:
                candidates.append(group[-6:])

    result: list[str] = []
    for candidate in candidates:
        normalized = candidate.lstrip("0") or "0"
        if normalized not in result:
            result.append(normalized)
    return result


def _unique_map(pairs: Iterable[tuple[str, dict[str, Any]]]) -> dict[str, dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for key, record in pairs:
        if key:
            grouped[key].append(record)
    return {key: values[0] for key, values in grouped.items() if len(values) == 1}


def load_wellbeing_csv(source: str | Path | BinaryIO) -> pd.DataFrame:
    """Lee y normaliza la base de bienestar, incluso si viene en CSV latino y con ;."""
    attempts = [
        {"sep": ";", "encoding": "latin1", "engine": "python"},
        {"sep": ",", "encoding": "utf-8-sig", "engine": "python"},
        {"sep": ",", "encoding": "latin1", "engine": "python"},
    ]
    last_error: Exception | None = None
    for options in attempts:
        try:
            if hasattr(source, "seek"):
                source.seek(0)
            raw = pd.read_csv(source, **options)
            if len(raw.columns) >= 2:
                return normalize_wellbeing_dataframe(raw)
        except Exception as exc:  # pragma: no cover - fallback de formatos
            last_error = exc
    raise ValueError(f"No fue posible leer la base de bienestar: {last_error}")


def normalize_wellbeing_dataframe(raw: pd.DataFrame) -> pd.DataFrame:
    aliases_by_key = {
        "carne": "carne",
        "carne academico": "carne",
        "registro academico": "carne",
        "nombre completo": "nombre_completo",
        "nombre": "nombre_completo",
        "correo": "correo",
        "correo electronico": "correo",
        "email": "correo",
        "carrera": "carrera",
        "programa": "carrera",
        "asesor de bienestar": "asesor_bienestar",
        "asesor bienestar": "asesor_bienestar",
        "estado bienestar": "estado_bienestar",
        "estado de bienestar": "estado_bienestar",
        "etapa en bienestar": "etapa_bienestar",
        "etapa de bienestar": "etapa_bienestar",
        "solicitudes particulares": "solicitudes_particulares",
        "nivel de riesgo ciclo regular": "riesgo_ciclo_regular",
        "nivel de riesgo del ciclo regular": "riesgo_ciclo_regular",
    }
    rename_map = {
        column: aliases_by_key.get(_ascii_key(column), column)
        for column in raw.columns
    }
    df = raw.rename(columns=rename_map).copy()

    if "carne" not in df.columns and "correo" in df.columns:
        df["carne"] = df["correo"].map(extract_carne)
    if "nombre_completo" not in df.columns:
        raise ValueError("La base debe contener una columna de nombre completo.")

    for column in STANDARD_COLUMNS:
        if column not in df.columns:
            df[column] = ""

    # Primero se extraen los dígitos para aceptar valores como cas262958.
    df["carne"] = df["carne"].map(lambda value: (_carne_candidates(value) or [""])[0])
    df["carne"] = pd.to_numeric(df["carne"], errors="coerce").astype("Int64")
    df = df[df["carne"].notna() & (df["carne"] > 0)].copy()

    for column in STANDARD_COLUMNS[1:]:
        df[column] = df[column].map(_clean_text)

    df.loc[df["asesor_bienestar"] == "", "asesor_bienestar"] = "Sin asignar"
    df = df[STANDARD_COLUMNS].drop_duplicates("carne", keep="last")
    return df.sort_values("nombre_completo").reset_index(drop=True)


def merge_wellbeing(analysis: pd.DataFrame, wellbeing: pd.DataFrame) -> pd.DataFrame:
    """Vincula estudiantes de Canvas con la base de bienestar.

    La coincidencia se intenta, en orden, por carné, correo, nombre normalizado
    y nombre con tokens reordenados. Esto cubre el formato ``Apellido, Nombre``
    de Canvas sin asignar automáticamente nombres ambiguos.
    """
    if analysis.empty:
        return analysis.copy()

    base = normalize_wellbeing_dataframe(wellbeing) if not set(STANDARD_COLUMNS).issubset(wellbeing.columns) else wellbeing.copy()
    base_records = base.to_dict(orient="records")

    by_carne = _unique_map(
        ((candidate, record) for record in base_records for candidate in _carne_candidates(record.get("carne")))
    )
    by_email = _unique_map((_email_key(record.get("correo")), record) for record in base_records)
    by_name = _unique_map((_name_key(record.get("nombre_completo")), record) for record in base_records)
    by_name_sorted = _unique_map(
        (_name_key(record.get("nombre_completo"), sort_tokens=True), record) for record in base_records
    )

    result_rows: list[dict[str, Any]] = []
    for source_row in analysis.to_dict(orient="records"):
        row = dict(source_row)
        original_carne = _clean_text(row.get("carne"))
        match: dict[str, Any] | None = None
        method = "Sin coincidencia"

        identifier_values = [
            row.get("carne"),
            row.get("sis_user_id"),
            row.get("canvas_sis_user_id"),
            row.get("login_id"),
            row.get("canvas_login_id"),
            row.get("email"),
            row.get("correo"),
        ]
        for value in identifier_values:
            for candidate in _carne_candidates(value):
                if candidate in by_carne:
                    match = by_carne[candidate]
                    method = "Carné"
                    break
            if match:
                break

        if match is None:
            for value in (row.get("email"), row.get("correo")):
                key = _email_key(value)
                if key and key in by_email:
                    match = by_email[key]
                    method = "Correo"
                    break

        name = row.get("student_name") or row.get("nombre_completo") or row.get("name")
        if match is None:
            key = _name_key(name)
            if key and key in by_name:
                match = by_name[key]
                method = "Nombre"

        if match is None:
            key = _name_key(name, sort_tokens=True)
            if key and key in by_name_sorted:
                match = by_name_sorted[key]
                method = "Nombre reordenado"

        row["carne_canvas_original"] = original_carne
        row["wellbeing_match_method"] = method
        row["wellbeing_record_found"] = match is not None

        if match is not None:
            row["carne"] = str(match.get("carne") or original_carne)
            row["asesor_bienestar"] = _clean_text(match.get("asesor_bienestar")) or "Sin asignar"
            row["advisor_name"] = row["asesor_bienestar"]
            for column in (
                "estado_bienestar",
                "etapa_bienestar",
                "solicitudes_particulares",
                "riesgo_ciclo_regular",
            ):
                row[column] = _clean_text(match.get(column))

            if not _clean_text(row.get("email")):
                row["email"] = _clean_text(match.get("correo"))
            if not _clean_text(row.get("career")):
                row["career"] = _clean_text(match.get("carrera"))
        else:
            row["asesor_bienestar"] = "Sin asignar"
            row["advisor_name"] = "Sin asignar"
            for column in (
                "estado_bienestar",
                "etapa_bienestar",
                "solicitudes_particulares",
                "riesgo_ciclo_regular",
            ):
                row.setdefault(column, "")

        result_rows.append(row)

    return pd.DataFrame(result_rows)
