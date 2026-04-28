const API_BASE = "https://fairlytics.onrender.com";

const datasetSection = document.getElementById("datasetSection");
const modelSection = document.getElementById("modelSection");
const loadingCard = document.getElementById("loadingCard");
const resultCard = document.getElementById("resultCard");
const previewCard = document.getElementById("previewCard");
const previewMeta = document.getElementById("previewMeta");
const previewTable = document.getElementById("previewTable");
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

let latestAuditPayload = null;

document.querySelectorAll("input[name='mode']").forEach((radio) => {
  radio.addEventListener("change", () => {
    const isDataset = radio.value === "dataset" && radio.checked;
    datasetSection.classList.toggle("hidden", !isDataset);
    modelSection.classList.toggle("hidden", isDataset);
    hideResults();
  });
});

document.getElementById("datasetForm").addEventListener("submit", async (event) => {
  event.preventDefault();
  hideResults();
  loadingCard.classList.remove("hidden");
  try {
    const file = document.getElementById("datasetFile").files[0];
    if (!file) throw new Error("Please upload a dataset CSV file.");

    const uploadFd = new FormData();
    uploadFd.append("file", file);
    const uploadRes = await fetch(`${API_BASE}/upload-dataset`, { method: "POST", body: uploadFd });
    const uploadData = await parseJson(uploadRes);
    renderPreview(uploadData);

    const body = {
      upload_id: uploadData.upload_id,
      protected_attr: document.getElementById("protectedAttr").value.trim(),
      label_col: document.getElementById("labelCol").value.trim(),
      favorable_label: document.getElementById("favorableLabel").value.trim(),
    };

    const runRes = await fetch(`${API_BASE}/run-dataset-audit`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    const runData = await parseJson(runRes);

    const resultRes = await fetch(`${API_BASE}/results/${runData.audit_id}`);
    const result = await parseJson(resultRes);
    openResultPage(result);
  } catch (error) {
    alert(error.message);
  } finally {
    loadingCard.classList.add("hidden");
  }
});

document.getElementById("modelForm").addEventListener("submit", async (event) => {
  event.preventDefault();
  hideResults();
  loadingCard.classList.remove("hidden");
  try {
    const file = document.getElementById("modelFile").files[0];
    if (!file) throw new Error("Please upload a model file.");

    const fd = new FormData();
    fd.append("model_file", file);
    fd.append("model_name", document.getElementById("modelName").value.trim() || "uploaded_model");
    fd.append("model_notes", document.getElementById("modelNotes").value.trim());

    const runRes = await fetch(`${API_BASE}/upload-model`, {
      method: "POST",
      body: fd,
    });
    const runData = await parseJson(runRes);

    const resultRes = await fetch(`${API_BASE}/results/${runData.audit_id}`);
    const result = await parseJson(resultRes);
    openResultPage(result);
  } catch (error) {
    alert(error.message);
  } finally {
    loadingCard.classList.add("hidden");
  }
});

function renderPreview(uploadData) {
  const columns = uploadData.columns || [];
  const rows = uploadData.preview_rows || [];
  previewMeta.textContent = `${uploadData.row_count || 0} rows detected | Columns: ${columns.join(", ")}`;

  if (!columns.length) {
    previewTable.innerHTML = "<tbody><tr><td>No preview available.</td></tr></tbody>";
    previewCard.classList.remove("hidden");
    return;
  }

  const thead = `<thead><tr>${columns.map((c) => `<th>${escapeHtml(c)}</th>`).join("")}</tr></thead>`;
  const tbodyRows = rows
    .map((row) => `<tr>${columns.map((c) => `<td>${escapeHtml(String(row[c] ?? ""))}</td>`).join("")}</tr>`)
    .join("");
  previewTable.innerHTML = `${thead}<tbody>${tbodyRows}</tbody>`;
  previewCard.classList.remove("hidden");
}

function renderResult(auditPayload) {
  latestAuditPayload = auditPayload;
  const payload = auditPayload.result || {};
  const report = payload.report || {};
  const quality = auditPayload.quality || {};
  const explanation = payload.simple_explanation || {};
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

  explanationTextEl.textContent =
    report.explanation ||
    explanation.summary ||
    "No explanation available. Run a dataset audit to generate a human-readable explanation.";

  renderEvidence(report, payload, quality);
  renderMetrics(report, payload);
  renderAttribution(report, payload, findingCount);
  renderRobustness(report, payload);
  renderActions(report, explanation);

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

  resultCard.classList.remove("hidden");
}

function hideResults() {
  resultCard.classList.add("hidden");
}

function renderEvidence(report, payload, quality) {
  const evidence = report.evidence || [];
  const evidenceRows = evidence.filter((item) => item.group && typeof item.count === "number");
  const comparison = evidence.find((item) => item.comparison_summary);
  const message = evidence.find((item) => item.message)?.message;

  if (message) {
    evidenceGridEl.innerHTML = `<div class="ev-label">${escapeHtml(message)}</div><div class="ev-value">Analysis rows: ${escapeHtml(
      String(quality.analysis_rows ?? 0)
    )}</div>`;
    evidenceDifferenceEl.textContent = "Provide more balanced labeled data for reliable group comparison.";
    return;
  }

  const rows = evidenceRows.map((item) => ({
    label: `${item.group} positive outcome rate (${item.count} rows)`,
    value: `${Number(item.positive_outcome_rate_pct ?? item.positive_outcome_rate * 100).toFixed(1)}%`,
  }));
  rows.push({ label: "Analysis rows", value: String(quality.analysis_rows ?? report.metadata?.analysis_row_count ?? 0) });

  evidenceGridEl.innerHTML = rows
    .map((row) => `<div class="ev-label">${escapeHtml(row.label)}</div><div class="ev-value">${escapeHtml(row.value)}</div>`)
    .join("");
  if (comparison && typeof comparison.gap === "number") {
    const thresholdPct = 10;
    const diffPct = comparison.gap * 100;
    evidenceDifferenceEl.textContent = `Difference: ${diffPct.toFixed(1)}% (${diffPct <= thresholdPct ? "within" : "above"} ${thresholdPct}% threshold)`;
  } else {
    const stats = payload.dataset_metrics?.group_statistics || [];
    if (stats.length >= 2) {
      const rates = stats.map((item) => Number(item.positive_rate)).filter((value) => Number.isFinite(value));
      const diffPct = (Math.max(...rates) - Math.min(...rates)) * 100;
      evidenceDifferenceEl.textContent = `Difference: ${diffPct.toFixed(1)}% based on observed groups.`;
    } else {
      evidenceDifferenceEl.textContent = "Insufficient data to compute group-level comparison.";
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
        return `<div class="metric-item"><span>${escapeHtml(metric.name || "Metric")}</span><span>Insufficient data to evaluate</span></div>`;
      }
      const isPass = Boolean(metric.pass);
      return `<div class="metric-item">
        <span>${escapeHtml(metric.name)}</span>
        <span>Value: ${value.toFixed(4)} | Threshold: ${metric.operator || "<="} ${threshold.toFixed(4)} ${isPass ? "✅" : "⚠️"}</span>
      </div>`;
    })
    .join("");
}

function renderAttribution(report, payload, findingCount) {
  const attribution = report.bias_attribution || {};
  const dataText = String(attribution.data_bias || "Minimal");
  const modelText = String(attribution.model_bias || "Minimal");
  const dataBias = qualitativeToPercent(dataText, findingCount);
  const modelBias = qualitativeToPercent(modelText, Math.max(1, findingCount - 1));
  dataBiasBarEl.style.width = `${dataBias}%`;
  modelBiasBarEl.style.width = `${modelBias}%`;
  dataBiasTextEl.textContent = dataText;
  modelBiasTextEl.textContent = modelText;
}

function renderRobustness(report, payload) {
  if (report.robustness_check) {
    robustnessTextEl.textContent = report.robustness_check;
    return;
  }
  const cf = payload.counterfactual_metrics || {};
  robustnessTextEl.textContent =
    cf && !cf.skipped && typeof cf.flip_rate === "number"
      ? `Counterfactual flip rate is ${(cf.flip_rate * 100).toFixed(1)}%.`
      : "Robustness check unavailable.";
}

function renderActions(report, explanation) {
  const suggestions = report.recommended_actions || explanation.suggestions || [];
  const defaultActions = [
    "Continue monitoring fairness every retraining cycle.",
    "Re-evaluate fairness for newly observed demographic groups.",
    "Test for proxy bias (for example: location and income).",
  ];
  const list = suggestions.length ? suggestions : defaultActions;
  actionsListEl.innerHTML = list.map((item) => `<li>✔ ${escapeHtml(item)}</li>`).join("");
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

function percent(value) {
  return Number.isFinite(value) ? `${(value * 100).toFixed(1)}%` : "Insufficient data";
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

backBtn.addEventListener("click", () => {
  resultCard.classList.add("hidden");
  window.scrollTo({ top: 0, behavior: "smooth" });
});

downloadBtn.addEventListener("click", () => {
  if (!latestAuditPayload) return;
  const blob = new Blob([JSON.stringify(latestAuditPayload, null, 2)], { type: "application/json" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = `fairlytics-audit-report-${Date.now()}.json`;
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
});

shareBtn.addEventListener("click", async () => {
  if (!latestAuditPayload) return;
  const shareText = `Fairlytics audit: score ${Math.round(
    latestAuditPayload?.result?.trust_score || 0
  )}/100, severity ${latestAuditPayload?.result?.overall_severity || "unknown"}.`;
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

function escapeHtml(value) {
  return value
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}

async function parseJson(response) {
  const data = await response.json().catch(() => ({}));
  if (!response.ok) {
    const message = Array.isArray(data.detail) ? data.detail.join(" | ") : data.detail || "Request failed.";
    throw new Error(message);
  }
  return data;
}

function openResultPage(result) {
  sessionStorage.setItem("fairlytics_latest_audit", JSON.stringify(result));
  window.location.href = "./result.html";
}
