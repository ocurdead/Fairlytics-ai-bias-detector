from typing import Dict

import pandas as pd


def get_group_statistics(df: pd.DataFrame, protected_attr: str, label_col: str, favorable_label: str):
    work = df[[protected_attr, label_col]].dropna().copy()
    work["_is_positive"] = (work[label_col].astype(str) == str(favorable_label)).astype(float)
    grouped = work.groupby(protected_attr, dropna=False)["_is_positive"].agg(["count", "mean"]).reset_index()
    grouped = grouped.sort_values("count", ascending=False)
    stats = []
    for _, row in grouped.iterrows():
        stats.append(
            {
                "group": str(row[protected_attr]),
                "count": int(row["count"]),
                "positive_rate": round(float(row["mean"]), 4),
            }
        )
    return stats


def run(df: pd.DataFrame, protected_attr: str, label_col: str, favorable_label: str) -> Dict:
    group_stats = get_group_statistics(df, protected_attr, label_col, favorable_label)
    rates = [item["positive_rate"] for item in group_stats if item["count"] > 0]
    if len(rates) < 2:
        di = 1.0
        spd = 0.0
        comparison_note = "Insufficient data to compute group-level comparison."
    else:
        ordered = sorted(rates)
        di = float(ordered[0] / ordered[-1]) if ordered[-1] > 0 else 1.0
        spd = float(ordered[0] - ordered[-1])
        comparison_note = "Computed from observed sensitive-attribute groups."

    return {
        "agent": "data_bias",
        "disparate_impact": round(di, 4),
        "statistical_parity_difference": round(spd, 4),
        "group_rates": {item["group"]: item["positive_rate"] for item in group_stats},
        "group_statistics_map": {
            item["group"]: {
                "count": item["count"],
                "positive_outcome_rate": item["positive_rate"],
                "positive_outcome_rate_pct": round(item["positive_rate"] * 100, 2),
            }
            for item in group_stats
        },
        "group_statistics": group_stats,
        "comparison_note": comparison_note,
    }
