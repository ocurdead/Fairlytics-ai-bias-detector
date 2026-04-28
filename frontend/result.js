const auditPayload = parseStoredAudit();

const verdictStatusEl = document.getElementById("verdictStatus");
const verdictScoreEl = document.getElementById("verdictScore");
const verdictMetaEl = document.getElementById("verdictMeta");
const verdictCardEl = document.getElementById("verdictCard");
const explanationTextEl = document.getElementById("explanationText");
const evidenceGridEl = document.getElementById("evidenceGrid");
const evidenceDifferenceEl = document.getElementById("evidenceDifference");
const metricsListEl = document.getElementById("metricsList");
const dataBiasBarEl = document.getElementById("dataBiasBar");
const modelBiasBarEl = document.getElementById("modelBiasBar");
const dataBiasTextEl = document.getElementById("dataBiasText");
const modelBiasTextEl = document.getElementById("modelBiasText");
const robustnessTextEl = document.getElementById("robustnessText");
const actionsListEl = document.getElementById("actionsList");
const decisionStatusEl = document.getElementById("decisionStatus");
const decisionConfidenceEl = document.getElementById("decisionConfidence");
const decisionColumnsEl = document.getElementById("decisionColumns");
const backBtn = document.getElementById("backBtn");
const downloadBtn = document.getElementById("downloadBtn");
const shareBtn = document.getElementById("shareBtn");

if (!auditPayload) {
  document.body.innerHTML =
    '<main class="container"><section class="card"><h2>No audit result found</h2><p>Please run an audit first from the home page.</p><a href="./index.html">Go to home</a></section></main>';
} else {
  renderResult(auditPayload);
}

backBtn.addEventListener("click", () => {
  window.location.href = "./index.html";
});

downloadBtn.addEventListener("click", () => {
  if (!auditPayload) return;
  exportPdfReport(auditPayload);
});

shareBtn.addEventListener("click", async () => {
  if (!auditPayload) return;
  const report = auditPayload?.result?.report || {};
  const shareText = `Fairlytics audit: ${report?.verdict?.status || "Audit completed"}, confidence ${
    Math.round(Number(report?.final_decision?.confidence || 0)) || 0
  }%.`;
  if (navigator.share) {
    try {
      await navigator.share({ title: "Fairlytics Audit Report", text: shareText });
      return;
    } catch {
      return;
    }
  }
  await navigator.clipboard.writeText(shareText);
  alert("Audit summary copied to clipboard.");
});

function renderResult(auditData) {
  const payload = auditData.result || {};
  const report = payload.report || {};
  const quality = auditData.quality || {};
  const resolvedColumns = quality.resolved_columns || {};
  const autoDetected = quality.protected_attr_auto_detected === true;
  const severity = String(report.verdict?.severity || payload.overall_severity || "low");
  const trustScore = Number(report.verdict?.trust_score ?? payload.trust_score ?? 0);
  const findingCount = (payload.findings || []).length;

  const verdictConfig = getVerdictConfig(severity, trustScore);
  verdictStatusEl.textContent = `${verdictConfig.icon} ${report.verdict?.status || verdictConfig.label}`;
  verdictScoreEl.textContent = `${Math.round(trustScore)} / 100`;
  verdictMetaEl.textContent = `Severity: ${capitalize(severity)}`;
  verdictCardEl.className = `verdict-card ${verdictConfig.className}`;

  explanationTextEl.textContent = cleanExplanation(report.explanation) || "No explanation available.";
  renderEvidence(report, payload, quality);
  renderMetrics(report, payload);
  renderAttribution(report, findingCount);
  robustnessTextEl.textContent = report.robustness_check || "Robustness check unavailable.";
  renderActions(report);

function cleanExplanation(text) {
  if (!text) return text;

  return text
    .replaceAll("treatment_given", "treatment")
    .replaceAll("loan_status", "loan approval")
    .replaceAll("hired", "hiring outcome")
    .replace(/\s+/g, " ") // remove extra spaces
    .trim();
} 

  const decisionText =
    String(report.final_decision?.status || "")
      .replaceAll("_", " ")
      .toUpperCase() || (trustScore >= 80 && (severity === "low" || severity === "medium") ? "SAFE TO DEPLOY" : "REVIEW BEFORE DEPLOY");
  decisionStatusEl.textContent = decisionText;
  decisionConfidenceEl.textContent = `Confidence: ${Math.max(
    0,
    Math.min(100, Math.round(Number(report.final_decision?.confidence ?? trustScore - findingCount * 2)))
  )}%`;
  decisionColumnsEl.textContent =
    resolvedColumns.protected_attr && resolvedColumns.label_col
      ? `Using sensitive attribute "${resolvedColumns.protected_attr}" and label "${resolvedColumns.label_col}"${
          autoDetected ? " (auto-detected)." : "."
        }`
      : "No resolved columns captured for this run.";
}

function renderEvidence(report, payload, quality) {
  const evidence = report.evidence || [];
  const evidenceRows = evidence.filter((item) => item.group && typeof item.count === "number");
  const comparison = evidence.find((item) => item.comparison_summary);
  const message = evidence.find((item) => item.message)?.message;

  if (message) {
    evidenceGridEl.innerHTML = `<div class="ev-label">Comparison</div><div class="ev-value">${escapeHtml(message)}</div>`;
    evidenceDifferenceEl.textContent = `Based on ${escapeHtml(
      String(quality.analysis_rows ?? report.metadata?.analysis_row_count ?? 0)
    )} analyzed rows.`;
    return;
  }

  if (evidenceRows.length >= 2) {
    const top = [...evidenceRows].sort((a, b) => Number(b.positive_outcome_rate) - Number(a.positive_outcome_rate))[0];
    const bottom = [...evidenceRows].sort((a, b) => Number(a.positive_outcome_rate) - Number(b.positive_outcome_rate))[0];
    evidenceGridEl.innerHTML = `
      <div class="ev-label">Comparison</div>
      <div class="ev-value">${escapeHtml(top.group)} vs ${escapeHtml(bottom.group)}</div>
      <div class="ev-label">Positive outcome rates</div>
      <div class="ev-value">${Number(top.positive_outcome_rate_pct).toFixed(1)}% vs ${Number(bottom.positive_outcome_rate_pct).toFixed(1)}%</div>
      <div class="ev-label">Group sizes</div>
      <div class="ev-value">${top.count} vs ${bottom.count} rows</div>
    `;
  } else {
    evidenceGridEl.innerHTML = evidenceRows
      .map(
        (item) =>
          `<div class="ev-label">${escapeHtml(item.group)}</div><div class="ev-value">${Number(
            item.positive_outcome_rate_pct ?? item.positive_outcome_rate * 100
          ).toFixed(1)}% (${item.count} rows)</div>`
      )
      .join("");
  }

  if (comparison && typeof comparison.gap === "number") {
    const thresholdPct = 10;
    const diffPct = comparison.gap * 100;
    evidenceDifferenceEl.textContent = `Observed gap: ${diffPct.toFixed(1)} percentage points, which is ${
      diffPct <= thresholdPct ? "within" : "above"
    } the ${thresholdPct}% reference threshold.`;
  } else {
    const stats = payload.dataset_metrics?.group_statistics || [];
    if (stats.length >= 2) {
      const rates = stats.map((item) => Number(item.positive_rate)).filter((value) => Number.isFinite(value));
      const diffPct = (Math.max(...rates) - Math.min(...rates)) * 100;
      evidenceDifferenceEl.textContent = `Observed gap across groups: ${diffPct.toFixed(1)} percentage points.`;
    } else {
      evidenceDifferenceEl.textContent = "A reliable group comparison could not be produced from the available rows.";
    }
  }
}

function renderMetrics(report, payload) {
  const reportMetrics = report.fairness_metrics || [];
  const fallbackMetrics = [];
  const dataMetrics = payload.dataset_metrics || {};
  if (Number.isFinite(Number(dataMetrics.disparate_impact))) {
    fallbackMetrics.push({
      name: "Disparate Impact",
      value: Number(dataMetrics.disparate_impact),
      threshold: 0.8,
      operator: ">=",
      pass: Number(dataMetrics.disparate_impact) >= 0.8,
    });
  }
  const metricRows = reportMetrics.length ? reportMetrics : fallbackMetrics;

  metricsListEl.innerHTML = metricRows
    .map((metric) => {
      const value = Number(metric.value);
      const threshold = Number(metric.threshold);
      if (metric.operator === "info") {
        return `<div class="metric-item"><span>${escapeHtml(metric.name)}</span><span>${escapeHtml(
          metric.note || "Context only"
        )}</span></div>`;
      }
      if (!Number.isFinite(value) || !Number.isFinite(threshold)) {
        return `<div class="metric-item"><span>${escapeHtml(metric.name || "Metric")}</span><span>Not enough evidence to evaluate this metric yet</span></div>`;
      }
      const isPass = Boolean(metric.pass);
      return `<div class="metric-item">
        <span>${escapeHtml(metric.name)}</span>
        <span>${value.toFixed(4)} vs ${metric.operator || "<="} ${threshold.toFixed(4)} ${isPass ? "✅ within threshold" : "⚠ exceeds threshold"}</span>
      </div>`;
    })
    .join("");
}

function renderAttribution(report, findingCount) {
  const attribution = report.bias_attribution || {};
  const dataText = String(attribution.data_bias || "Minimal");
  const modelText = String(attribution.model_bias || "Minimal");
  dataBiasBarEl.style.width = `${qualitativeToPercent(dataText, findingCount)}%`;
  modelBiasBarEl.style.width = `${qualitativeToPercent(modelText, Math.max(1, findingCount - 1))}%`;
  dataBiasTextEl.textContent = dataText;
  modelBiasTextEl.textContent = attribution.reasoning ? `${modelText} - ${attribution.reasoning}` : modelText;
}

function renderActions(report) {
  const suggestions = report.recommended_actions || [];
  const fallback = [
    "Continue monitoring fairness every retraining cycle.",
    "Re-evaluate fairness for newly observed demographic groups.",
    "Test for proxy bias in correlated features.",
  ];
  const list = suggestions.length ? suggestions : fallback;
  actionsListEl.innerHTML = list.map((item) => `<li>✔ ${escapeHtml(item)}</li>`).join("");
}

function exportPdfReport(auditData) {
  const { jsPDF } = window.jspdf;
  const doc = new jsPDF({ unit: "pt", format: "a4" });
  const report = auditData?.result?.report || {};
  const margin = 48;
  let y = 56;

  const addLine = (text, opts = {}) => {
    const size = opts.size || 11;
    const weight = opts.bold ? "bold" : "normal";
    doc.setFont("helvetica", weight);
    doc.setFontSize(size);
    const wrapped = doc.splitTextToSize(String(text), 500);
    if (y + wrapped.length * (size + 3) > 780) {
      doc.addPage();
      y = 56;
    }
    doc.text(wrapped, margin, y);
    y += wrapped.length * (size + 3) + (opts.gap ?? 8);
  };

  addLine("Fairlytics Audit Report", { size: 18, bold: true, gap: 12 });
  addLine(`Generated: ${new Date().toLocaleString()}`, { size: 10, gap: 14 });
  addLine("Verdict", { size: 13, bold: true, gap: 6 });
  addLine(`${report?.verdict?.status || "N/A"} | Score: ${Math.round(Number(report?.verdict?.trust_score || 0))}/100`);

  addLine("Explanation", { size: 13, bold: true, gap: 6 });
  addLine(report.explanation || "No explanation available.");

  addLine("Evidence", { size: 13, bold: true, gap: 6 });
  const evidence = report.evidence || [];
  if (!evidence.length) {
    addLine("Insufficient data to compute group-level comparison.");
  } else {
    evidence.forEach((item) => {
      if (item.group) {
        addLine(`- ${item.group}: ${item.count} rows, positive outcome rate ${Number(item.positive_outcome_rate_pct).toFixed(1)}%`, {
          gap: 4,
        });
      } else if (item.comparison_summary) {
        addLine(`- ${item.comparison_summary} Gap: ${(Number(item.gap) * 100).toFixed(1)}%.`, { gap: 4 });
      } else if (item.message) {
        addLine(`- ${item.message}`, { gap: 4 });
      }
    });
  }

  addLine("Fairness Metrics", { size: 13, bold: true, gap: 6 });
  (report.fairness_metrics || []).forEach((metric) => {
    if (metric.operator === "info") {
      addLine(`- ${metric.name}: ${metric.note || "Context only"}`, { gap: 4 });
    } else {
      addLine(
        `- ${metric.name}: value ${Number(metric.value).toFixed(4)}, threshold ${metric.operator} ${Number(metric.threshold).toFixed(
          4
        )}, status ${metric.pass ? "PASS" : "FLAG"}`,
        { gap: 4 }
      );
    }
  });

  addLine("Bias Attribution", { size: 13, bold: true, gap: 6 });
  addLine(`Data Bias: ${report?.bias_attribution?.data_bias || "Minimal"}`, { gap: 4 });
  addLine(`Model Bias: ${report?.bias_attribution?.model_bias || "Minimal"}`);
  addLine(report?.bias_attribution?.reasoning || "Attribution is based on observed outcome and prediction disparities.", {
    gap: 8,
  });

  addLine("Robustness Check", { size: 13, bold: true, gap: 6 });
  addLine(report.robustness_check || "Robustness check unavailable.");

  addLine("Recommended Actions", { size: 13, bold: true, gap: 6 });
  (report.recommended_actions || []).forEach((action) => addLine(`- ${action}`, { gap: 4 }));

  addLine("Final Decision", { size: 13, bold: true, gap: 6 });
  addLine(
    `${String(report?.final_decision?.status || "Review Before Deploy")} | Confidence: ${Math.round(
      Number(report?.final_decision?.confidence || 0)
    )}%`
  );

  doc.save(`fairlytics-audit-report-${Date.now()}.pdf`);
}

function parseStoredAudit() {
  const raw = sessionStorage.getItem("fairlytics_latest_audit");
  if (!raw) return null;
  try {
    return JSON.parse(raw);
  } catch {
    return null;
  }
}

function getVerdictConfig(severity, score) {
  if (severity === "high" || severity === "critical" || score < 70) {
    return { icon: "🔴", label: "High Risk", className: "verdict-risk-high" };
  }
  if (severity === "medium" || score < 85) {
    return { icon: "🟡", label: "Moderate Risk", className: "verdict-risk-medium" };
  }
  return { icon: "🟢", label: "Fair (Low Risk)", className: "verdict-risk-low" };
}

function capitalize(value) {
  return value ? value.charAt(0).toUpperCase() + value.slice(1) : value;
}

function qualitativeToPercent(value, fallbackSeed) {
  const normalized = value.toLowerCase();
  if (normalized.includes("minimal")) return 8;
  if (normalized.includes("low")) return 22;
  if (normalized.includes("moderate")) return 48;
  if (normalized.includes("high")) return 74;
  return Math.min(85, Math.max(10, fallbackSeed * 12));
}

function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}
