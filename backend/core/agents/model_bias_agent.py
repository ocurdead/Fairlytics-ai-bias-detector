from typing import Dict

import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import recall_score
from sklearn.model_selection import train_test_split


def run(df: pd.DataFrame, protected_attr: str, label_col: str, favorable_label: str) -> Dict:
    work = df.copy()
    y = (work[label_col].astype(str) == str(favorable_label)).astype(int)
    sensitive = work[protected_attr].astype(str)
    x = pd.get_dummies(work.drop(columns=[label_col, protected_attr]), drop_first=True).fillna(0)

    if x.shape[1] == 0 or y.nunique() != 2:
        return {"agent": "model_bias", "skipped": True, "reason": "insufficient model features or non-binary label"}

    x_train, x_test, y_train, y_test, _, s_test = train_test_split(
        x, y, sensitive, test_size=0.3, random_state=42, stratify=y
    )

    clf = LogisticRegression(max_iter=1000, class_weight="balanced", random_state=42)
    clf.fit(x_train, y_train)
    preds = clf.predict(x_test)

    positive_rate_by_group = {}
    tpr_by_group = {}
    counts_by_group = {}
    for group in sorted(s_test.unique()):
        mask = s_test == group
        grp_pred = preds[mask]
        grp_true = y_test[mask]
        counts_by_group[str(group)] = int(mask.sum())
        positive_rate_by_group[str(group)] = float(grp_pred.mean()) if len(grp_pred) else 0.0
        tpr_by_group[str(group)] = float(recall_score(grp_true, grp_pred, zero_division=0)) if len(grp_true) else 0.0

    if len(positive_rate_by_group) < 2:
        dpd = 0.0
        eod = 0.0
        comparison_note = "Insufficient data to compute group-level comparison."
    else:
        dp_vals = list(positive_rate_by_group.values())
        eo_vals = list(tpr_by_group.values())
        dpd = max(dp_vals) - min(dp_vals)
        eod = max(eo_vals) - min(eo_vals)
        comparison_note = "Computed from model predictions on held-out test data."

    return {
        "agent": "model_bias",
        "skipped": False,
        "demographic_parity_difference": round(float(dpd), 4),
        "equalized_odds_difference": round(float(eod), 4),
        "positive_rate_by_group": {k: round(v, 4) for k, v in positive_rate_by_group.items()},
        "tpr_by_group": {k: round(v, 4) for k, v in tpr_by_group.items()},
        "counts_by_group": counts_by_group,
        "comparison_note": comparison_note,
    }
