from __future__ import annotations

import re
from typing import Any


def extract_carne(value: Any) -> str:
    """Extrae el número de carné desde correo, login o texto libre."""
    if value is None:
        return ""
    text = str(value).strip()
    if not text:
        return ""

    # Prioriza la parte numérica del usuario antes de @.
    local = text.split("@", 1)[0]
    groups = re.findall(r"\d+", local)
    if not groups:
        groups = re.findall(r"\d+", text)
    if not groups:
        return ""
    return max(groups, key=len)


def safe_int(value: Any) -> int | None:
    try:
        if value is None or value == "":
            return None
        return int(float(value))
    except (TypeError, ValueError):
        return None
