from typing import Dict

import pandas as pd

from config import THRESHOLDS, settings
from core.agents import counterfactual_agent, data_bias_agent, model_bias_agent
from core.explanation_agent import explain_findings_simple


def run_orchestration(
    df: pd.DataFrame,
    protected_attr: str,
    label_col: str,
    favorable_label: str,
    domain: str = "general",          # NEW — pass from your API router
) -> Dict:
    data_result = data_bias_agent.run(df, protected_attr, label_col, favorable_label)

    model_result = {
        "agent": "model_bias",
        "skipped": True,
        "reason": "dataset too small or non-binary label",
    }
    if len(df) >= settings.min_rows_for_model and df[label_col].nunique() == 2:
        model_result = model_bias_agent.run(df, protected_attr, label_col, favorable_label)

    cf_result = {
        "agent": "counterfactual",
        "skipped": True,
        "reason": "model issue not detected",
    }
    if not model_result.get("skipped"):
        trigger_cf = (
            abs(model_result["demographic_parity_difference"]) > THRESHOLDS["demographic_parity_difference"]
            or abs(model_result["equalized_odds_difference"]) > THRESHOLDS["equalized_odds_difference"]
        )
        if trigger_cf:
            cf_result = counterfactual_agent.run(df, protected_attr, label_col, favorable_label)

    findings = _build_findings(
        data_result, model_result, cf_result,
        protected_attr=protected_attr,
        label_col=label_col,
    )
    trust_score = _trust_score(findings)

    # explain_findings_simple now receives real numbers for a specific explanation
    explanation = explain_findings_simple(
        findings=findings,
        trust_score=trust_score,
        mode="dataset",
        data_result=data_result,
        domain=domain,
        protected_attr=protected_attr,
        label_col=label_col,
    )

    report = format_fairness_report(
        findings=findings,
        trust_score=trust_score,
        data_result=data_result,
        model_result=model_result,
        cf_result=cf_result,
        protected_attr=protected_attr,
        label_col=label_col,
        total_rows=len(df),
        domain=domain,
    )

    return {
        "overall_severity": _overall_severity(findings),
        "trust_score": trust_score,
        "findings": findings,
        "simple_explanation": explanation,
        "dataset_metrics": data_result,
        "model_metrics": model_result,
        "counterfactual_metrics": cf_result,
        "report": report,
    }


def run_model_only_orchestration(model_name: str, model_notes: str) -> Dict:
    findings = [
        {
            "id": "model_review_needed",
            "severity": "medium",
            "headline": f"Uploaded model '{model_name}' needs fairness validation on evaluation data.",
            "recommendation": "Run fairness checks with labeled test data and sensitive attributes before deployment.",
        }
    ]
    trust_score = 65.0
    explanation = explain_findings_simple(findings, trust_score, mode="model")
    explanation["summary"] += f" Model notes: {model_notes[:180]}" if model_notes else ""
    return {
        "overall_severity": "medium",
        "trust_score": trust_score,
        "findings": findings,
        "simple_explanation": explanation,
        "dataset_metrics": None,
        "model_metrics": {"uploaded_model_name": model_name},
        "counterfactual_metrics": None,
        "report": {
            "verdict": {"status": "Review Required", "severity": "medium", "trust_score": trust_score},
            "explanation": explanation.get("summary", ""),
            "evidence": [],
            "fairness_metrics": [],
            "bias_attribution": {
                "data_bias": "Minimal",
                "model_bias": "Minimal",
                "data_bias_pct": 0,
                "model_bias_pct": 0,
                "data_bias_description": "No dataset provided for data-level analysis.",
                "model_bias_description": "Model was uploaded without evaluation data.",
                "method": "heuristic fallback",
            },
            "robustness_check": "Robustness check unavailable because no evaluation dataset was provided.",
            "recommended_actions": explanation.get("suggestions", []),
            "final_decision": {"status": "Review Before Deploy", "confidence": trust_score},
            "metadata": {"mode": "model_upload"},
        },
    }


# ── FIX 1: _build_findings — human headlines instead of metric dumps ──────────

def _build_findings(
    data_result: Dict,
    model_result: Dict,
    cf_result: Dict,
    protected_attr: str = "the protected attribute",
    label_col: str = "the outcome",
):
    findings = []
    stats = data_result.get("group_statistics", [])

    # Build human headline for disparate impact
    if data_result["disparate_impact"] < THRESHOLDS["disparate_impact_low"]:
        # Get actual group names and rates for the headline
        if len(stats) >= 2:
            highest = max(stats, key=lambda x: x["positive_rate"])
            lowest  = min(stats, key=lambda x: x["positive_rate"])
            adv_pct = round(highest["positive_rate"] * 100, 1)
            dis_pct = round(lowest["positive_rate"]  * 100, 1)
            gap     = round(adv_pct - dis_pct, 1)
            headline = (
                f"'{lowest['group']}' receives '{label_col}' {gap}pp less often "
                f"than '{highest['group']}' ({dis_pct}% vs {adv_pct}%)"
            )
        else:
            di = round(data_result["disparate_impact"], 3)
            headline = (
                f"Unequal outcome rates detected across '{protected_attr}' groups "
                f"(Disparate Impact: {di}, threshold ≥ 0.8)"
            )

        findings.append({
            "id": "data_disparate_impact",
            "severity": "high" if data_result["disparate_impact"] < 0.65 else "medium",
            "headline": headline,
            "recommendation": "Apply reweighing or balanced sampling before training.",
            "recommendations": {
                "pre_processing": "Apply Reweighing algorithm (AIF360) to balance outcome rates in training data.",
                "in_processing": "Use ExponentiatedGradient with DemographicParity constraint (Fairlearn).",
                "post_processing": "Use ThresholdOptimizer (Fairlearn) to calibrate decision thresholds per group.",
            },
        })

    if not model_result.get("skipped"):
        dpd = model_result["demographic_parity_difference"]
        if abs(dpd) > THRESHOLDS["demographic_parity_difference"]:
            direction = "higher" if dpd > 0 else "lower"
            findings.append({
                "id": "model_dpd",
                "severity": "high" if abs(dpd) > 0.2 else "medium",
                "headline": (
                    f"Model predicts positive outcomes {round(abs(dpd)*100,1)}pp "
                    f"{direction} for the privileged group across '{protected_attr}'"
                ),
                "recommendation": "Use fairness-constrained training or threshold optimization.",
                "recommendations": {
                    "in_processing": "ExponentiatedGradient with DemographicParity (Fairlearn).",
                    "post_processing": "ThresholdOptimizer with demographic_parity constraint (Fairlearn).",
                },
            })

        eod = model_result["equalized_odds_difference"]
        if abs(eod) > THRESHOLDS["equalized_odds_difference"]:
            findings.append({
                "id": "model_eod",
                "severity": "high" if abs(eod) > 0.2 else "medium",
                "headline": (
                    f"Error rates differ across '{protected_attr}' groups by "
                    f"{round(abs(eod)*100,1)}pp — some groups face more false rejections"
                ),
                "recommendation": "Tune decision thresholds and compare group-level error rates.",
                "recommendations": {
                    "in_processing": "ExponentiatedGradient with EqualizedOdds (Fairlearn).",
                    "post_processing": "ThresholdOptimizer with equalized_odds constraint (Fairlearn).",
                },
            })

    if not cf_result.get("skipped") and cf_result["flip_rate"] > THRESHOLDS["counterfactual_flip_rate"]:
        findings.append({
            "id": "counterfactual_flip_rate",
            "severity": "high",
            "headline": (
                f"{round(cf_result['flip_rate']*100,1)}% of predictions change when "
                f"only '{protected_attr}' is flipped — model is directly sensitive to this attribute"
            ),
            "recommendation": "Reduce direct/proxy use of protected attributes in model features.",
            "recommendations": {
                "pre_processing": "Remove direct use of the protected attribute from features.",
                "in_processing": "Retrain with fairness constraints applied.",
            },
        })

    return findings


def _trust_score(findings):
    if not findings:
        return 95.0
    penalties = {"medium": 15, "high": 25, "critical": 40}
    score = 100
    for finding in findings:
        score -= penalties.get(finding["severity"], 10)
    return max(0.0, float(score))


def _overall_severity(findings):
    levels = [f["severity"] for f in findings]
    if "critical" in levels:
        return "critical"
    if "high" in levels:
        return "high"
    if "medium" in levels:
        return "medium"
    return "low"


def format_fairness_report(
    findings: Dict,
    trust_score: float,
    data_result: Dict,
    model_result: Dict,
    cf_result: Dict,
    protected_attr: str,
    label_col: str,
    total_rows: int,
    domain: str = "general",
) -> Dict:
    severity = _overall_severity(findings)
    verdict_status = (
        "Fair (Low Risk)" if severity == "low"
        else "Moderate Risk" if severity == "medium"
        else "High Risk"
    )
    final_status = (
        "Safe To Deploy"
        if trust_score >= 80 and severity in {"low", "medium"}
        else "Review Before Deploy"
    )
    confidence = max(0.0, min(99.0, trust_score - (2.0 * len(findings))))

    evidence    = _build_evidence(data_result=data_result, protected_attr=protected_attr, label_col=label_col)
    fairness_metrics = _build_standardized_metrics(data_result=data_result, model_result=model_result, cf_result=cf_result)
    attribution = _build_bias_attribution(data_result=data_result, model_result=model_result, findings=findings)
    robustness  = _build_robustness_text(cf_result)

    # FIX: report.explanation now comes from explain_findings_simple (specific text)
    # instead of _build_plain_english_explanation (vague text)
    explanation_obj = explain_findings_simple(
        findings=findings,
        trust_score=trust_score,
        mode="dataset",
        data_result=data_result,
        domain=domain,
        protected_attr=protected_attr,
        label_col=label_col,
    )
    explanation_text = explanation_obj.get("summary", "")

    recommendations = [f["recommendation"] for f in findings[:3]] or [
        "Continue monitoring fairness across retraining cycles.",
        "Review performance by sensitive attribute groups before deployment.",
        "Validate fairness again when data distribution changes.",
    ]

    return {
        "verdict": {
            "status": verdict_status,
            "severity": severity,
            "trust_score": round(trust_score, 2),
        },
        "explanation": explanation_text,          # ← now uses real numbers + domain context
        "evidence": evidence,
        "fairness_metrics": fairness_metrics,
        "bias_attribution": attribution,          # ← now has _pct and _description fields
        "robustness_check": robustness,
        "recommended_actions": recommendations,
        "final_decision": {
            "status": final_status,
            "confidence": round(confidence, 2),
        },
        "metadata": {
            "protected_attribute": protected_attr,
            "label_column": label_col,
            "analysis_row_count": total_rows,
            "finding_count": len(findings),
            "data_note": data_result.get("comparison_note", ""),
            "model_note": (
                model_result.get("comparison_note", "")
                if isinstance(model_result, dict)
                else ""
            ),
        },
    }


def _build_evidence(data_result: Dict, protected_attr: str, label_col: str):
    stats = data_result.get("group_statistics", [])
    if len(stats) < 2:
        return [{
            "message": (
                "There is not enough balanced data across sensitive groups "
                "to produce a reliable comparison yet."
            ),
            "protected_attribute": protected_attr,
            "label_column": label_col,
        }]

    top    = max(stats, key=lambda x: x["positive_rate"])
    bottom = min(stats, key=lambda x: x["positive_rate"])
    return [
        {
            "group": item["group"],
            "count": item["count"],
            "positive_outcome_rate": item["positive_rate"],
            "positive_outcome_rate_pct": round(item["positive_rate"] * 100, 2),
        }
        for item in stats
    ] + [{
        "comparison_summary": (
            f"Observed gap between '{top['group']}' and '{bottom['group']}' "
            "for positive outcomes."
        ),
        "gap": round(abs(top["positive_rate"] - bottom["positive_rate"]), 4),
    }]


def _build_standardized_metrics(data_result: Dict, model_result: Dict, cf_result: Dict):
    items = [
        {
            "name": "Disparate Impact",
            "value": data_result.get("disparate_impact"),
            "threshold": THRESHOLDS["disparate_impact_low"],
            "operator": ">=",
            "pass": data_result.get("disparate_impact", 0) >= THRESHOLDS["disparate_impact_low"],
        },
        {
            "name": "Statistical Parity Difference",
            "value": abs(data_result.get("statistical_parity_difference", 0)),
            "threshold": THRESHOLDS["demographic_parity_difference"],
            "operator": "<=",
            "pass": (
                abs(data_result.get("statistical_parity_difference", 0))
                <= THRESHOLDS["demographic_parity_difference"]
            ),
        },
    ]

    if not model_result.get("skipped"):
        items.extend([
            {
                "name": "Demographic Parity Difference",
                "value": abs(model_result.get("demographic_parity_difference", 0)),
                "threshold": THRESHOLDS["demographic_parity_difference"],
                "operator": "<=",
                "pass": (
                    abs(model_result.get("demographic_parity_difference", 0))
                    <= THRESHOLDS["demographic_parity_difference"]
                ),
            },
            {
                "name": "Equalized Odds Difference",
                "value": abs(model_result.get("equalized_odds_difference", 0)),
                "threshold": THRESHOLDS["equalized_odds_difference"],
                "operator": "<=",
                "pass": (
                    abs(model_result.get("equalized_odds_difference", 0))
                    <= THRESHOLDS["equalized_odds_difference"]
                ),
            },
        ])
    else:
        items.append({
            "name": "Model-based Fairness Metrics",
            "value": 0.0,
            "threshold": 0.0,
            "operator": "info",
            "pass": False,
            "note": model_result.get("reason", "Model metrics unavailable."),
        })

    if not cf_result.get("skipped"):
        items.append({
            "name": "Counterfactual Flip Rate",
            "value": cf_result.get("flip_rate", 0),
            "threshold": THRESHOLDS["counterfactual_flip_rate"],
            "operator": "<=",
            "pass": cf_result.get("flip_rate", 1) <= THRESHOLDS["counterfactual_flip_rate"],
        })

    return items


# ── FIX 2: _build_bias_attribution — adds _pct and _description fields ────────

def _build_bias_attribution(data_result: Dict, model_result: Dict, findings):
    di = data_result.get("disparate_impact", 1.0)
    data_signal = max(0.0, (THRESHOLDS["disparate_impact_low"] - di) * 100)

    model_signal = 0.0
    if not model_result.get("skipped"):
        model_signal = max(
            abs(model_result.get("demographic_parity_difference", 0)),
            abs(model_result.get("equalized_odds_difference", 0)),
        ) * 100

    data_text  = _qualitative_level(data_signal)
    model_text = _qualitative_level(model_signal)

    # NEW: numeric percentages for bar widths (0–100)
    data_pct  = _qualitative_to_pct(data_text)
    model_pct = _qualitative_to_pct(model_text)

    # NEW: clean one-sentence descriptions (not reasoning paragraphs)
    if data_result.get("eeoc_flag") or data_signal > 0:
        data_description = (
            f"Disparate Impact Ratio is {round(di, 3)} "
            f"(threshold ≥ {THRESHOLDS['disparate_impact_low']}). "
            "Historical data shows unequal outcome rates across groups."
        )
    else:
        data_description = "No significant data-level bias detected."

    if model_result.get("skipped"):
        raw_reason = model_result.get("reason", "")
        if "small" in raw_reason.lower():
            model_description = "Dataset too small for model-level analysis (need 100+ rows)."
        elif "binary" in raw_reason.lower():
            model_description = "Requires a binary label column to run."
        else:
            model_description = "Model-level check was skipped."
    elif model_signal > 0:
        dpd = round(abs(model_result.get("demographic_parity_difference", 0)) * 100, 1)
        model_description = (
            f"Model predictions differ by {dpd}pp across groups — "
            "some groups are favoured in automated decisions."
        )
    else:
        model_description = "Model predictions are roughly equal across groups."

    return {
        # Kept for backward compat with your existing JS
        "data_bias":  data_text,
        "model_bias": model_text,
        # NEW fields consumed by the fixed renderAttribution()
        "data_bias_pct":         data_pct,
        "model_bias_pct":        model_pct,
        "data_bias_description":  data_description,
        "model_bias_description": model_description,
        "method": "rule-based qualitative attribution",
    }


def _build_robustness_text(cf_result: Dict) -> str:
    if cf_result.get("skipped"):
        reason = cf_result.get("reason", "insufficient evaluation evidence")
        return f"Robustness check was not run because {reason.replace('_', ' ')}."
    flip_rate = float(cf_result.get("flip_rate", 0))
    if flip_rate <= THRESHOLDS["counterfactual_flip_rate"]:
        return (
            f"Predictions remain stable under the robustness test "
            f"(flip rate: {round(flip_rate * 100, 1)}%), which suggests "
            "limited sensitivity to protected-attribute changes."
        )
    return (
        f"Predictions change materially under the robustness test "
        f"(flip rate: {round(flip_rate * 100, 1)}%), "
        "which indicates potential instability."
    )


def _qualitative_level(signal: float) -> str:
    if signal < 5:   return "Minimal"
    if signal < 12:  return "Low"
    if signal < 25:  return "Moderate"
    return "High"


def _qualitative_to_pct(level: str) -> float:
    """Convert a qualitative label to a numeric bar percentage."""
    return {"Minimal": 8.0, "Low": 25.0, "Moderate": 55.0, "High": 80.0}.get(level, 8.0)