from __future__ import annotations


def region_text(region) -> str:
    if not region:
        return "não configurado"
    if len(region) == 4:
        return f"x={region[0]}  y={region[1]}  {region[2]}x{region[3]}"
    return f"x={region[0]}  y={region[1]}"


def parse_float(value: str, fallback: float) -> float:
    try:
        return float(str(value).replace(",", "."))
    except (TypeError, ValueError):
        return fallback


def parse_int(value: str, fallback: int) -> int:
    try:
        return int(float(str(value).replace(",", ".")))
    except (TypeError, ValueError):
        return fallback
