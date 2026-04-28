from typing import Dict

import pandas as pd
from sklearn.linear_model import LogisticRegression


def run(df: pd.DataFrame, protected_attr: str, label_col: str, favorable_label: str) -> Dict:
    work = df.copy()
    if work[protected_attr].nunique() != 2:
        return {"agent": "counterfactual", "skipped": True, "reason": "binary protected attribute required"}

    work["_label"] = (work[label_col].astype(str) == str(favorable_label)).astype(int)
    x = pd.get_dummies(work.drop(columns=[label_col, "_label"]), drop_first=True).fillna(0)
    y = work["_label"]
    if x.shape[1] == 0 or y.nunique() != 2:
        return {"agent": "counterfactual", "skipped": True, "reason": "insufficient model features or non-binary label"}

    clf = LogisticRegression(max_iter=1000, class_weight="balanced", random_state=42)
    clf.fit(x, y)

    sample = work.sample(min(40, len(work)), random_state=42).copy()
    groups = [str(v) for v in sorted(work[protected_attr].astype(str).unique().tolist())]
    g0, g1 = groups[0], groups[1]

    original_x = pd.get_dummies(sample.drop(columns=[label_col]), drop_first=True).fillna(0)
    original_x = original_x.reindex(columns=x.columns, fill_value=0)
    original_preds = clf.predict(original_x)

    flipped = sample.copy()
    flipped[protected_attr] = flipped[protected_attr].astype(str).apply(lambda v: g1 if v == g0 else g0)
    flipped_x = pd.get_dummies(flipped.drop(columns=[label_col]), drop_first=True).fillna(0)
    flipped_x = flipped_x.reindex(columns=x.columns, fill_value=0)
    flipped_preds = clf.predict(flipped_x)

    changed = int((original_preds != flipped_preds).sum())
    tested = int(len(sample))
    flip_rate = float(changed / tested) if tested else 0.0

    return {
        "agent": "counterfactual",
        "skipped": False,
        "flip_rate": round(flip_rate, 4),
        "samples_tested": tested,
        "samples_changed": changed,
    }
