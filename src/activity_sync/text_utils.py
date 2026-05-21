from __future__ import annotations

import hashlib
import re
from typing import Iterable

import pandas as pd


def clean_text(value: object) -> str:
    if pd.isna(value):
        return ""

    text = str(value).strip()
    text = re.sub(r"\s+", " ", text)
    return text


def clean_int(value: object) -> int | None:
    """
    Converts Excel numeric values safely.

    Examples:
    100010      -> 100010
    100010.0    -> 100010
    "100010"    -> 100010
    "100010.0"  -> 100010
    blank/NaN    -> None

    Do not use this for Meydan official codes like 0140.00.
    Official codes must remain text.
    """
    if pd.isna(value):
        return None

    text = str(value).strip()

    if not text:
        return None

    if text.lower() == "nan":
        return None

    try:
        return int(float(text))
    except ValueError:
        return None


def clean_official_code(value: object) -> str:
    """
    Keeps official jurisdiction/API codes as text.
    Example: Meydan official code 0140.00 must remain 0140.00.
    """
    return clean_text(value)


def normalize_activity_name(value: object) -> str:
    text = clean_text(value).lower()
    text = text.replace("&", " and ")
    text = re.sub(r"[^a-z0-9\s]", " ", text)

    replacements = {
        "services": "service",
        "activities": "activity",
        "consultancy": "consulting",
        "trading": "trade",
        "repairing": "repair",
        "programme": "program",
        "centre": "center",
        "licence": "license",
    }

    for old, new in replacements.items():
        text = re.sub(rf"\b{old}\b", new, text)

    text = re.sub(r"\s+", " ", text).strip()
    return text


def row_hash(values: Iterable[object]) -> str:
    joined = "||".join(clean_text(value) for value in values)
    return hashlib.sha256(joined.encode("utf-8")).hexdigest()


def length_ratio_ok(
    name_a: str,
    name_b: str,
    min_ratio: float = 0.75,
    max_ratio: float = 1.35,
) -> bool:
    a = max(len(normalize_activity_name(name_a)), 1)
    b = max(len(normalize_activity_name(name_b)), 1)
    ratio = a / b
    return min_ratio <= ratio <= max_ratio