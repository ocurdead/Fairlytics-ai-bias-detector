import io
from typing import Dict, List, Tuple

import pandas as pd


SENSITIVE_ATTRIBUTE_HINTS = (
    "gender",
    "sex",
    "race",
    "ethnicity",
    "religion",
    "caste",
    "age",
    "disability",
    "nationality",
    "marital_status",
)


def normalize_column_name(value: str) -> str:
    return value.strip().lower().replace(" ", "_")


def resolve_column_name(df: pd.DataFrame, raw_name: str) -> str:
    if not raw_name:
        return ""
    candidate = normalize_column_name(raw_name)
    if candidate in df.columns:
        return candidate
    return ""


def detect_sensitive_attribute(df: pd.DataFrame) -> str:
    for column in df.columns:
        if any(hint in column for hint in SENSITIVE_ATTRIBUTE_HINTS):
            return column
    return ""


def parse_csv_bytes(file_bytes: bytes) -> pd.DataFrame:
    df = pd.read_csv(io.BytesIO(file_bytes))
    df.columns = [normalize_column_name(c) for c in df.columns]
    return df


def validate_for_audit(
    df: pd.DataFrame, protected_attr: str, label_col: str, favorable_label: str
) -> Tuple[List[str], Dict]:
    errors: List[str] = []
    resolved_label_col = resolve_column_name(df, label_col)
    if not resolved_label_col:
        errors.append(f"Label column '{label_col}' not found.")

    resolved_protected_attr = resolve_column_name(df, protected_attr)
    auto_detected = False
    if not resolved_protected_attr:
        resolved_protected_attr = detect_sensitive_attribute(df)
        auto_detected = bool(resolved_protected_attr)

    if not resolved_protected_attr:
        if protected_attr.strip():
            errors.append(f"Protected attribute '{protected_attr}' not found.")
        else:
            errors.append("No sensitive attribute detected automatically. Please enter one manually.")

    if errors:
        return errors, {}

    if str(favorable_label) not in set(df[resolved_label_col].astype(str).tolist()):
        errors.append(f"favorable_label '{favorable_label}' not present in '{resolved_label_col}'.")

    clean = df.dropna(subset=[resolved_protected_attr, resolved_label_col]).copy()
    if clean.empty:
        errors.append("No valid rows remain after removing missing sensitive attribute and label values.")
        return errors, {}

    group_counts = clean[resolved_protected_attr].value_counts()
    quality = {
        "original_rows": int(len(df)),
        "analysis_rows": int(len(clean)),
        "dropped_nulls": int(len(df) - len(clean)),
        "label_is_binary": bool(clean[resolved_label_col].nunique() == 2),
        "min_group_size": int(group_counts.min()),
        "group_count": int(group_counts.shape[0]),
        "resolved_columns": {
            "protected_attr": resolved_protected_attr,
            "label_col": resolved_label_col,
        },
        "protected_attr_auto_detected": auto_detected and not bool(protected_attr.strip()),
        "notes": [],
    }
    if quality["group_count"] < 2:
        quality["notes"].append("Insufficient data to compute group-level comparison.")
    elif quality["group_count"] > 2:
        quality["notes"].append(
            "Sensitive attribute has more than two groups. Pairwise comparisons are summarized using observed min/max rates."
        )
    return errors, quality
