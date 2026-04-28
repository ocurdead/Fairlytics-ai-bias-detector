import json
import sys
from pathlib import Path
from typing import Dict, List, Optional

if __package__ is None or __package__ == "":
    sys.path.append(str(Path(__file__).resolve().parents[1]))

from config import settings


# ─────────────────────────────────────────────
# Domain + Label Helpers
# ─────────────────────────────────────────────

def _infer_domain(label_col: str) -> str:
    label = label_col.lower().replace("_", " ")

    if any(word in label for word in ["treatment", "medical", "patient", "hospital"]):
        return "healthcare"

    if any(word in label for word in ["loan", "credit", "approval", "finance"]):
        return "lending"

    if any(word in label for word in ["admission", "student", "exam", "college"]):
        return "education"

    if any(word in label for word in ["hire", "job", "recruit", "employee"]):
        return "hiring"

    return "general"


def _humanize_label(label: str, domain: str) -> str:
    label_clean = label.replace("_", " ").lower()

    if "treatment" in label_clean:
        return "treatment"
    if "loan" in label_clean:
        return "loan approval"
    if "hire" in label_clean:
        return "hiring outcome"

    return label_clean


# ─────────────────────────────────────────────
# Public Entry
# ─────────────────────────────────────────────

def explain_findings_simple(
    findings: List[Dict],
    trust_score: float,
    mode: str = "dataset_or_model",
    data_result: Optional[Dict] = None,
    domain: Optional[str] = None,
    protected_attr: str = "attribute",
    label_col: str = "outcome",
) -> Dict:

    # 🔥 AUTO domain detection
    domain = domain or _infer_domain(label_col)
    human_label = _humanize_label(label_col, domain)

    if not findings:
        return {
            "summary": (
                "No major fairness issues were detected. "
                "Continue monitoring fairness as new data arrives."
            ),
            "suggestions": [
                "Monitor fairness metrics during each retraining cycle.",
                "Validate fairness across different demographic groups.",
                "Perform periodic bias audits.",
            ],
            "source": "rule-based",
        }

    if settings.groq_api_key:
        try:
            return _llm_explain(
                findings,
                trust_score,
                data_result,
                domain,
                protected_attr,
                human_label,
            )
        except Exception:
            pass

    return _template_explain(
        findings,
        data_result,
        domain,
        protected_attr,
        human_label,
    )


# ─────────────────────────────────────────────
# LLM Explanation (Controlled)
# ─────────────────────────────────────────────

def _llm_explain(
    findings,
    trust_score,
    data_result,
    domain,
    protected_attr,
    human_label,
):
    from groq import Groq

    client = Groq(api_key=settings.groq_api_key)

    context = _build_metric_context(data_result, protected_attr, human_label, domain)

    prompt = f"""
You are a fairness auditor writing for a non-technical decision-maker.

AUDIT CONTEXT:
{context}

FINDINGS:
{json.dumps(findings, indent=2)}

Rules:
- Use the EXACT numbers provided
- Use domain-appropriate wording:
  healthcare → treatment, patients
  lending → approval, applicants
  hiring → hiring outcomes, candidates
- Do NOT use raw column names
- Do NOT include trust score
- Keep tone professional, simple and clear

Respond ONLY as JSON:
{{"summary": "...", "suggestions": ["...", "...", "..."]}}
"""

    message = client.chat.completions.create(
        model=settings.groq_model,
        max_tokens=400,
        messages=[{"role": "user", "content": prompt}],
    )

    text = message.choices[0].message.content.strip()

    try:
        parsed = json.loads(text)
        parsed["source"] = "llm"
        return parsed
    except:
        return _template_explain(
            findings,
            data_result,
            domain,
            protected_attr,
            human_label,
        )


# ─────────────────────────────────────────────
# Template Explanation (MAIN ENGINE)
# ─────────────────────────────────────────────
def _template_explain(
    findings,
    data_result,
    domain,
    protected_attr,
    human_label,
):
    # ─────────────────────────────────────────────
    # Domain wording
    # ─────────────────────────────────────────────
    domain_frames = {
        "healthcare": {
            "subject": "patients",
            "action": "received treatment",
            "risk": "unequal access to care",
        },
        "lending": {
            "subject": "applicants",
            "action": "were approved",
            "risk": "unfair lending decisions",
        },
        "hiring": {
            "subject": "candidates",
            "action": "were selected",
            "risk": "biased hiring decisions",
        },
        "education": {
            "subject": "students",
            "action": "were admitted",
            "risk": "unfair selection practices",
        },
        "general": {
            "subject": "individuals",
            "action": "received positive outcomes",
            "risk": "potential bias",
        },
    }

    frame = domain_frames.get(domain, domain_frames["general"])
    # 🔥 Force correct wording based on label (backup safety)
    label_lower = human_label.lower()

    if "treatment" in label_lower:
        frame["action"] = "received treatment"
    elif "loan" in label_lower:
        frame["action"] = "were approved"
    elif "hire" in label_lower:
        frame["action"] = "were selected"

    # ─────────────────────────────────────────────
    # Humanize group names
    # ─────────────────────────────────────────────
    def humanize_group(g):
        g = str(g).strip().lower()
        mapping = {
            "m": "Male",
            "male": "Male",
            "f": "Female",
            "female": "Female",
        }
        return mapping.get(g, g.capitalize())

    # ─────────────────────────────────────────────
    # Extract rates correctly
    # ─────────────────────────────────────────────
    rates = {}

    if data_result:
        if "group_rates" in data_result:
            rates = data_result["group_rates"]

        elif "group_statistics" in data_result:
            rates = {
                item["group"]: item["positive_rate"]
                for item in data_result["group_statistics"]
            }

        elif "group_statistics_map" in data_result:
            rates = {
                g: v["positive_outcome_rate"]
                for g, v in data_result["group_statistics_map"].items()
            }

    # fallback (rare)
    if not rates and findings:
        for f in findings:
            if "group_rates" in f:
                rates = f["group_rates"]
                break

    # ─────────────────────────────────────────────
    # MAIN LOGIC
    # ─────────────────────────────────────────────
    groups = list(rates.keys())

    if len(groups) >= 2:
        sorted_groups = sorted(groups, key=lambda g: rates[g], reverse=True)

        adv = sorted_groups[0]
        dis = sorted_groups[-1]

        adv_pct = round(rates[adv] * 100, 1)
        dis_pct = round(rates[dis] * 100, 1)
        gap = round(adv_pct - dis_pct, 1)

        adv_name = humanize_group(adv)
        dis_name = humanize_group(dis)

        # ✅ CLEAN, SIMPLE, HUMAN
        return {
            "summary": (
                f"{dis_name} {frame['action']} much less often than {adv_name} "
                f"({dis_pct}% vs {adv_pct}%). "
                f"There is a {gap}% gap and suggests {frame['risk']}."
            ),
            "suggestions": [
                "Balance the dataset across groups",
                "Apply reweighing or resampling",
                "Check fairness before deployment",
            ],
            "source": "rule-based",
        }

    # ─────────────────────────────────────────────
    # FALLBACK
    # ─────────────────────────────────────────────
    return {
        "summary": (
            f"A fairness issue was detected in {human_label}, "
            f"but not enough data is available to measure it clearly."
        ),
        "suggestions": [
            "Ensure all groups have enough data",
            "Verify dataset quality",
            "Re-run the analysis",
        ],
        "source": "rule-based",
    }


# ─────────────────────────────────────────────
# Metric Context Builder
# ─────────────────────────────────────────────

def _build_metric_context(data_result, protected_attr, label, domain):
    if not data_result:
        return f"{domain} | {protected_attr} | {label}"

    rates = data_result.get("group_positive_rates", {})

    rate_lines = "\n".join([
        f"{g}: {round(v.get('positive_rate', 0) * 100, 1)}% (n={v.get('n', '?')})"
        for g, v in rates.items()
    ])

    return f"""
Domain: {domain}
Attribute: {protected_attr}
Outcome: {label}

Group outcomes:
{rate_lines}
"""