let spendChart;
let dailyChart;
let platformTrendChart;
let currentRange = { start_date: "", end_date: "" };
let chartRetryCount = 0;
let pendingChartData = null;

const money = new Intl.NumberFormat("pt-BR", { style: "currency", currency: "BRL" });
const number = new Intl.NumberFormat("pt-BR");

document.addEventListener("DOMContentLoaded", async () => {
  bindEvents();
  setDefaultDates();
  await Promise.all([loadAuthStatus(), loadAccounts(), loadCampaigns(), loadSyncStatus()]);
  await refreshDashboard();
  hydrateIcons();
});

function bindEvents() {
  document.querySelector("#period").addEventListener("change", () => {
    document.querySelector("#customDates").hidden = document.querySelector("#period").value !== "custom";
    refreshDashboard();
  });
  document.querySelector("#startDate").addEventListener("change", refreshDashboard);
  document.querySelector("#endDate").addEventListener("change", refreshDashboard);
  document.querySelectorAll("input[name='platform']").forEach((checkbox) => checkbox.addEventListener("change", refreshDashboard));
  document.querySelector("#accountSelect").addEventListener("change", async () => {
    await loadCampaigns();
    await refreshDashboard();
  });
  document.querySelector("#campaignSelect").addEventListener("change", refreshDashboard);
  document.querySelector("#refreshAccounts").addEventListener("click", refreshSelectedAccounts);
  document.querySelector("#syncData").addEventListener("click", syncData);
}

function setDefaultDates() {
  const end = new Date();
  const start = new Date();
  start.setDate(end.getDate() - 29);
  document.querySelector("#startDate").value = toIsoDate(start);
  document.querySelector("#endDate").value = toIsoDate(end);
}

async function loadAuthStatus() {
  const response = await fetch("/auth/status");
  const payload = await response.json();
  const strip = document.querySelector("#connectionStrip");
  strip.innerHTML = "";
  for (const item of payload.items) {
    const label = item.platform === "google" ? "Google Ads" : "Meta Ads";
    const ready = item.configured && (item.has_local_token || item.has_refresh_token || item.has_env_token);
    const href = item.configured ? `/auth/${item.platform}/start` : "#";
    strip.insertAdjacentHTML(
      "beforeend",
      `<a class="status-pill ${ready ? "ready" : ""}" href="${href}">
        <span class="status-dot"></span>
        <span>${label}</span>
      </a>`
    );
  }
}

async function loadAccounts() {
  const response = await fetch("/api/accounts");
  const payload = await response.json();
  const select = document.querySelector("#accountSelect");
  const selected = select.value;
  select.innerHTML = `<option value="">Todas</option>`;
  for (const account of payload.items) {
    select.insertAdjacentHTML("beforeend", `<option value="${account.id}">${account.platform} - ${account.name}</option>`);
  }
  select.value = selected;
}

async function loadCampaigns() {
  const accountId = document.querySelector("#accountSelect").value;
  const url = accountId ? `/api/campaigns?account_id=${encodeURIComponent(accountId)}` : "/api/campaigns";
  const response = await fetch(url);
  const payload = await response.json();
  const select = document.querySelector("#campaignSelect");
  const selected = select.value;
  select.innerHTML = `<option value="">Todas</option>`;
  for (const campaign of payload.items) {
    select.insertAdjacentHTML("beforeend", `<option value="${campaign.id}">${campaign.platform} - ${campaign.name}</option>`);
  }
  select.value = selected;
}

async function refreshDashboard() {
  const period = document.querySelector("#period").value;
  const params = new URLSearchParams({
    period,
    platforms: selectedPlatforms().join(","),
    account_ids: document.querySelector("#accountSelect").value,
    campaign_ids: document.querySelector("#campaignSelect").value,
  });
  if (period === "custom") {
    params.set("start_date", document.querySelector("#startDate").value);
    params.set("end_date", document.querySelector("#endDate").value);
  }
  const dashboardResponse = await fetch(`/api/dashboard?${params.toString()}`);
  const dashboard = await dashboardResponse.json();
  currentRange = dashboard.range;
  const rangeText = `${formatDate(currentRange.start_date)} a ${formatDate(currentRange.end_date)}`;
  document.querySelector("#rangeLabel").textContent = rangeText;
  document.querySelector("#topRangeLabel").textContent = rangeText;
  renderMetricTiles(dashboard.summary);
  renderSummaryLedger(dashboard.summary);
  renderCharts(dashboard.summary, dashboard.daily);
  await loadMetricTable();
  updateExportLinks();
}

async function loadMetricTable() {
  const params = new URLSearchParams({
    start_date: currentRange.start_date,
    end_date: currentRange.end_date,
    platforms: selectedPlatforms().join(","),
    account_ids: document.querySelector("#accountSelect").value,
    campaign_ids: document.querySelector("#campaignSelect").value,
  });
  const response = await fetch(`/api/metrics?${params.toString()}`);
  const payload = await response.json();
  const body = document.querySelector("#metricsTable");
  body.innerHTML = "";
  if (!payload.items.length) {
    body.innerHTML = `<tr><td class="empty-row" colspan="13">Nenhum dado salvo para este filtro. Sincronize a conta ou ajuste o período selecionado.</td></tr>`;
    return;
  }
  for (const row of payload.items) {
    body.insertAdjacentHTML(
      "beforeend",
      `<tr>
        <td>${formatDate(row.date)}</td>
        <td><span class="platform-tag ${row.platform === "meta" ? "meta" : ""}">${platformLabel(row.platform)}</span></td>
        <td>${campaignModel(row.campaign_objective)}</td>
        <td>${row.campaign_name}</td>
        <td class="numeric">${number.format(row.reach || 0)}</td>
        <td class="numeric">${number.format(row.impressions)}</td>
        <td class="numeric">${frequency(row.impressions, row.reach).toFixed(2)}</td>
        <td class="numeric">${number.format(row.clicks)}</td>
        <td class="numeric">${row.ctr.toFixed(2)}%</td>
        <td class="numeric">${money.format(row.cpc)}</td>
        <td class="numeric">${money.format(row.spend)}</td>
        <td class="numeric">${number.format(row.messages || row.conversions || 0)}</td>
        <td class="numeric">${money.format(row.cost_per_message || row.cost_per_conversion || 0)}</td>
      </tr>`
    );
  }
}

async function loadSyncStatus() {
  const status = document.querySelector("#syncStatus");
  if (!status) return;
  try {
    const response = await fetch("/api/sync/status");
    const payload = await response.json();
    status.classList.toggle("ok", payload.ok === true);
    status.classList.toggle("error", payload.ok === false);
    if (!payload.last_run_at) {
      status.innerHTML = `<span>Última sincronização</span><strong>Nenhum registro ainda</strong>`;
      return;
    }
    const label = payload.ok ? "Concluída" : "Com erro";
    status.innerHTML = `<span>Última sincronização</span><strong>${label} em ${formatDateTime(payload.last_run_at)}</strong>`;
  } catch {
    status.innerHTML = `<span>Última sincronização</span><strong>Status indisponível</strong>`;
  }
}

function renderMetricTiles(summary) {
  const totals = summary.reduce(
    (acc, row) => {
      acc.impressions += row.impressions;
      acc.reach += row.reach || 0;
      acc.clicks += row.clicks;
      acc.spend += row.spend;
      acc.messages += row.messages || 0;
      acc.conversions += row.conversions;
      acc.value += row.conversion_value;
      return acc;
    },
    { impressions: 0, reach: 0, clicks: 0, spend: 0, messages: 0, conversions: 0, value: 0 }
  );
  const ctr = totals.impressions ? (totals.clicks / totals.impressions) * 100 : 0;
  const costPerMessage = totals.messages ? totals.spend / totals.messages : 0;
  const avgFrequency = frequency(totals.impressions, totals.reach);
  const tiles = [
    ["Investimento", money.format(totals.spend), "wallet-cards", "Total aplicado no período"],
    ["Conversas", number.format(totals.messages), "messages-square", "Conversas iniciadas"],
    ["Custo/conv.", money.format(costPerMessage), "badge-dollar-sign", "Custo por conversa"],
    ["Alcance", number.format(totals.reach), "radar", "Pessoas alcançadas"],
    ["Impressões", number.format(totals.impressions), "eye", "Exibições totais"],
    ["Frequência", avgFrequency.toFixed(2), "repeat-2", "Média de impressões por pessoa"],
    ["Cliques", number.format(totals.clicks), "mouse-pointer-click", "Volume de tráfego capturado"],
    ["CTR médio", `${ctr.toFixed(2)}%`, "activity", "Taxa de cliques"],
    ["CPC médio", money.format(totals.clicks ? totals.spend / totals.clicks : 0), "mouse-pointer-2", "Custo médio por clique"],
  ];
  document.querySelector("#metricGrid").innerHTML = tiles
    .map(
      ([label, value, icon, foot]) =>
        `<article class="metric-tile">
          <span class="metric-kicker"><span>${label}</span><i data-lucide="${icon}"></i></span>
          <strong>${value}</strong>
          <span class="metric-foot">${foot}</span>
        </article>`
    )
    .join("");
  hydrateIcons();
}

function renderSummaryLedger(summary) {
  const ledger = document.querySelector("#summaryLedger");
  if (!summary.length) {
    ledger.innerHTML = `<div class="ledger-item"><span><i class="ledger-dot"></i>Nenhum dado</span><strong>Sincronize uma conta</strong></div>`;
    return;
  }
  ledger.innerHTML = summary
    .map(
      (row) =>
        `<div class="ledger-item ${row.platform === "meta" ? "meta" : ""}">
          <span><i class="ledger-dot"></i>${platformLabel(row.platform)} | ${number.format(row.messages || 0)} conversas</span>
          <strong>${money.format(row.cost_per_message || 0)} por conversa</strong>
        </div>`
    )
    .join("");
}

function renderCharts(summary, daily) {
  pendingChartData = { summary, daily };
  if (!summary.length && !daily.length) {
    if (spendChart) spendChart.destroy();
    if (dailyChart) dailyChart.destroy();
    if (platformTrendChart) platformTrendChart.destroy();
    renderChartFallback(summary, daily);
    return;
  }
  if (!window.Chart) {
    renderChartFallback(summary, daily);
    if (chartRetryCount < 20) {
      chartRetryCount += 1;
      window.setTimeout(() => renderCharts(pendingChartData.summary, pendingChartData.daily), 350);
    }
    return;
  }

  clearChartFallbacks();
  const spendContext = document.querySelector("#spendChart");
  const dailyContext = document.querySelector("#dailyChart");
  const platformTrendContext = document.querySelector("#platformTrendChart");
  if (spendChart) spendChart.destroy();
  if (dailyChart) dailyChart.destroy();
  if (platformTrendChart) platformTrendChart.destroy();

  spendChart = new Chart(spendContext, {
    type: "doughnut",
    data: {
      labels: summary.map((row) => platformLabel(row.platform)),
      datasets: [
        {
          data: summary.map((row) => row.spend),
          backgroundColor: ["#38a4c8", "#31c48d", "#e2a15b"],
          borderColor: "#12171d",
          borderWidth: 5,
          hoverOffset: 8,
        },
      ],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      cutout: "64%",
      plugins: {
        legend: { position: "bottom", labels: { color: "#aeb9c5", usePointStyle: true, boxWidth: 8, padding: 18 } },
      },
    },
  });

  const labels = [...new Set(daily.map((row) => row.date))];
  dailyChart = new Chart(dailyContext, {
    type: "line",
    data: {
      labels: labels.map(formatDate),
      datasets: [
        {
          label: "Cliques",
          data: labels.map((day) => sumDaily(daily, day, "clicks")),
          borderColor: "#38a4c8",
          backgroundColor: "rgba(56, 164, 200, 0.14)",
          pointRadius: 3,
          pointHoverRadius: 6,
          tension: 0.32,
          fill: true,
        },
        {
          label: "Conversas",
          data: labels.map((day) => sumDaily(daily, day, "messages")),
          borderColor: "#e2a15b",
          backgroundColor: "rgba(226, 161, 91, 0.13)",
          pointRadius: 3,
          pointHoverRadius: 6,
          tension: 0.32,
          fill: true,
        },
      ],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      interaction: { intersect: false, mode: "index" },
      plugins: { legend: { position: "bottom", labels: { color: "#aeb9c5", usePointStyle: true, boxWidth: 8, padding: 18 } } },
      scales: {
        x: { ticks: { color: "#9ba8b5" }, grid: { display: false } },
        y: { beginAtZero: true, ticks: { color: "#9ba8b5" }, grid: { color: "rgba(155, 168, 181, 0.16)" } },
      },
    },
  });

  const trendLabels = [...new Set(daily.map((row) => row.date))];
  const platforms = [...new Set(daily.map((row) => row.platform))];
  const colors = {
    google: { spend: "#38a4c8", conversions: "#7bd6ef" },
    meta: { spend: "#31c48d", conversions: "#a6e7cd" },
  };
  platformTrendChart = new Chart(platformTrendContext, {
    type: "line",
    data: {
      labels: trendLabels.map(formatDate),
      datasets: platforms.flatMap((platform) => [
        {
          label: `${platformLabel(platform)} investimento`,
          data: trendLabels.map((day) => sumDailyByPlatform(daily, day, platform, "spend")),
          borderColor: colors[platform]?.spend || "#e2a15b",
          backgroundColor: "transparent",
          pointRadius: 3,
          pointHoverRadius: 6,
          tension: 0.32,
          yAxisID: "money",
        },
        {
          label: `${platformLabel(platform)} conversas`,
          data: trendLabels.map((day) => sumDailyByPlatform(daily, day, platform, "messages")),
          borderColor: colors[platform]?.conversions || "#f0c18c",
          backgroundColor: "transparent",
          borderDash: [5, 5],
          pointRadius: 3,
          pointHoverRadius: 6,
          tension: 0.32,
          yAxisID: "conversions",
        },
      ]),
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      interaction: { intersect: false, mode: "index" },
      plugins: { legend: { position: "bottom", labels: { color: "#aeb9c5", usePointStyle: true, boxWidth: 8, padding: 18 } } },
      scales: {
        x: { ticks: { color: "#9ba8b5" }, grid: { display: false } },
        money: { type: "linear", position: "left", beginAtZero: true, ticks: { color: "#9ba8b5" }, grid: { color: "rgba(155, 168, 181, 0.14)" } },
        conversions: { type: "linear", position: "right", beginAtZero: true, ticks: { color: "#9ba8b5" }, grid: { drawOnChartArea: false } },
      },
    },
  });
}

function renderChartFallback(summary, daily) {
  const spendCanvas = document.querySelector("#spendChart");
  const dailyCanvas = document.querySelector("#dailyChart");
  const platformTrendCanvas = document.querySelector("#platformTrendChart");
  spendCanvas.hidden = true;
  dailyCanvas.hidden = true;
  platformTrendCanvas.hidden = true;
  ensureFallback(spendCanvas, "spendFallback").innerHTML = summary.length
    ? summary
        .map((row) => {
          const total = summary.reduce((sum, item) => sum + item.spend, 0) || 1;
          return `<div class="fallback-row">
            <span>${platformLabel(row.platform)}</span>
            <strong>${money.format(row.spend)}</strong>
            <i style="--bar:${Math.max(8, (row.spend / total) * 100)}%"></i>
          </div>`;
        })
        .join("")
    : `<div class="fallback-empty">Sincronize dados para visualizar o investimento.</div>`;

  const labels = [...new Set(daily.map((row) => row.date))].slice(-6);
  ensureFallback(dailyCanvas, "dailyFallback").innerHTML = labels.length
    ? `<div class="fallback-bars">${labels
        .map((day) => {
          const clicks = sumDaily(daily, day, "clicks");
          const maxClicks = Math.max(...labels.map((item) => sumDaily(daily, item, "clicks")), 1);
          return `<div class="fallback-bar">
            <i style="height:${Math.max(10, (clicks / maxClicks) * 100)}%"></i>
            <span>${formatDate(day).slice(0, 5)}</span>
          </div>`;
        })
        .join("")}</div>`
    : `<div class="fallback-empty">Sincronize dados para visualizar a evolução diária de cliques e conversas.</div>`;

  ensureFallback(platformTrendCanvas, "platformTrendFallback").innerHTML = labels.length
    ? `<div class="fallback-bars">${labels
        .map((day) => {
          const spend = sumDaily(daily, day, "spend");
          const maxSpend = Math.max(...labels.map((item) => sumDaily(daily, item, "spend")), 1);
          return `<div class="fallback-bar">
            <i style="height:${Math.max(10, (spend / maxSpend) * 100)}%"></i>
            <span>${formatDate(day).slice(0, 5)}</span>
          </div>`;
        })
        .join("")}</div>`
    : `<div class="fallback-empty">Sincronize dados para visualizar investimento e conversas por plataforma.</div>`;
}

function ensureFallback(canvas, id) {
  let fallback = document.querySelector(`#${id}`);
  if (!fallback) {
    fallback = document.createElement("div");
    fallback.id = id;
    fallback.className = "chart-fallback";
    canvas.insertAdjacentElement("afterend", fallback);
  }
  return fallback;
}

function clearChartFallbacks() {
  document.querySelector("#spendChart").hidden = false;
  document.querySelector("#dailyChart").hidden = false;
  document.querySelector("#platformTrendChart").hidden = false;
  document.querySelectorAll(".chart-fallback").forEach((item) => item.remove());
}

function hydrateIcons(attempt = 0) {
  if (window.lucide) {
    window.lucide.createIcons();
    return;
  }
  if (attempt < 20) {
    window.setTimeout(() => hydrateIcons(attempt + 1), 250);
  }
}

async function refreshSelectedAccounts() {
  const platforms = selectedPlatforms();
  if (!platforms.length) return showToast("Selecione ao menos uma plataforma.");
  for (const platform of platforms) {
    const response = await fetch(`/api/accounts/refresh?platform=${platform}`, { method: "POST" });
    if (!response.ok) {
      const error = await response.json();
      showToast(`${platformLabel(platform)}: ${error.detail || "falha ao buscar contas"}`);
      continue;
    }
  }
  await loadAccounts();
  showToast("Contas atualizadas.");
}

async function syncData() {
  const platforms = selectedPlatforms();
  if (!platforms.length) return showToast("Selecione ao menos uma plataforma.");
  const payload = {
    platforms,
    start_date: currentRange.start_date,
    end_date: currentRange.end_date,
    account_ids: document.querySelector("#accountSelect").value ? [document.querySelector("#accountSelect").value] : [],
    campaign_ids: document.querySelector("#campaignSelect").value ? [document.querySelector("#campaignSelect").value] : [],
  };
  const response = await fetch("/api/sync", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  const result = await response.json();
  const errors = result.items.filter((item) => item.error);
  if (errors.length) showToast(errors.map((item) => `${platformLabel(item.platform)}: ${item.error}`).join(" | "));
  else showToast("Dados sincronizados com sucesso.");
  await Promise.all([loadAccounts(), loadCampaigns(), loadSyncStatus(), refreshDashboard()]);
}

function updateExportLinks() {
  const params = new URLSearchParams({
    start_date: currentRange.start_date,
    end_date: currentRange.end_date,
    platforms: selectedPlatforms().join(","),
    account_ids: document.querySelector("#accountSelect").value,
    campaign_ids: document.querySelector("#campaignSelect").value,
  });
  document.querySelector("#exportPdf").href = `/api/export/pdf?${params.toString()}`;
  document.querySelector("#exportXlsx").href = `/api/export/xlsx?${params.toString()}`;
}

function selectedPlatforms() {
  return [...document.querySelectorAll("input[name='platform']:checked")].map((item) => item.value);
}

function sumDaily(rows, day, field) {
  return rows.filter((row) => row.date === day && selectedPlatforms().includes(row.platform)).reduce((sum, row) => sum + (row[field] || 0), 0);
}

function sumDailyByPlatform(rows, day, platform, field) {
  return rows.filter((row) => row.date === day && row.platform === platform && selectedPlatforms().includes(row.platform)).reduce((sum, row) => sum + (row[field] || 0), 0);
}

function platformLabel(platform) {
  return platform === "google" ? "Google Ads" : "Meta Ads";
}

function campaignModel(objective) {
  const value = (objective || "").toUpperCase();
  if (["OUTCOME_ENGAGEMENT", "MESSAGES", "POST_ENGAGEMENT"].includes(value)) return "Engajamento para mensagens";
  if (["OUTCOME_LEADS", "LEAD_GENERATION"].includes(value)) return "Geração de cadastros";
  if (["OUTCOME_TRAFFIC", "LINK_CLICKS"].includes(value)) return "Tráfego";
  if (["OUTCOME_SALES", "CONVERSIONS"].includes(value)) return "Vendas / conversões";
  if (["OUTCOME_AWARENESS", "BRAND_AWARENESS", "REACH"].includes(value)) return "Reconhecimento / alcance";
  return objective ? objective.replaceAll("_", " ").toLowerCase() : "Não informado";
}

function frequency(impressions, reach) {
  return reach ? impressions / reach : 0;
}

function formatDate(value) {
  if (!value) return "";
  const [year, month, day] = value.split("-");
  return `${day}/${month}/${year}`;
}

function formatDateTime(value) {
  const clean = value.replace("Z", "");
  const [datePart, timePart = ""] = clean.split("T");
  return `${formatDate(datePart)} ${timePart.slice(0, 5)}`.trim();
}

function toIsoDate(value) {
  return value.toISOString().slice(0, 10);
}

function showToast(message) {
  const toast = document.querySelector("#toast");
  toast.textContent = message;
  toast.classList.add("visible");
  window.clearTimeout(showToast.timer);
  showToast.timer = window.setTimeout(() => toast.classList.remove("visible"), 5200);
}
