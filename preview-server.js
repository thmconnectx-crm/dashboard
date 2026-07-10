const http = require("http");
const fs = require("fs");
const path = require("path");

const root = __dirname;
const port = Number(process.env.PORT || 8000);

const daily = [
  ["2026-06-11", "google", 4200, 312, 688.4, 21, 2840],
  ["2026-06-11", "meta", 6100, 428, 532.1, 29, 3610],
  ["2026-06-18", "google", 5200, 364, 771.9, 24, 3180],
  ["2026-06-18", "meta", 7400, 512, 624.7, 36, 4520],
  ["2026-06-25", "google", 5800, 410, 846.2, 31, 4260],
  ["2026-06-25", "meta", 8200, 596, 711.5, 42, 5140],
  ["2026-07-02", "google", 6700, 482, 982.6, 38, 5390],
  ["2026-07-02", "meta", 9100, 690, 835.3, 49, 6420],
  ["2026-07-09", "google", 7200, 548, 1034.8, 44, 6040],
  ["2026-07-09", "meta", 9800, 762, 901.2, 58, 7560],
].map(([date, platform, impressions, clicks, spend, conversions, conversion_value], index) => {
  const campaign = platform === "google" ? "Search - Alta Intencao" : "Instagram - Conversao";
  return metricRow({
    date,
    platform,
    account_id: platform === "google" ? "1234567890" : "act_1234567890",
    campaign_id: `${platform}-${index + 1}`,
    campaign_name: campaign,
    impressions,
    clicks,
    spend,
    conversions,
    conversion_value,
  });
});

function metricRow(row) {
  return {
    ...row,
    ctr: row.impressions ? round((row.clicks / row.impressions) * 100) : 0,
    cpc: row.clicks ? round(row.spend / row.clicks) : 0,
    cost_per_conversion: row.conversions ? round(row.spend / row.conversions) : 0,
    roas: row.spend ? round(row.conversion_value / row.spend) : 0,
  };
}

function round(value) {
  return Math.round(value * 100) / 100;
}

function summary(rows) {
  const buckets = new Map();
  for (const row of rows) {
    const current = buckets.get(row.platform) || {
      platform: row.platform,
      impressions: 0,
      clicks: 0,
      spend: 0,
      conversions: 0,
      conversion_value: 0,
    };
    current.impressions += row.impressions;
    current.clicks += row.clicks;
    current.spend += row.spend;
    current.conversions += row.conversions;
    current.conversion_value += row.conversion_value;
    buckets.set(row.platform, current);
  }
  return [...buckets.values()].map(metricRow);
}

function sendJson(response, payload) {
  response.writeHead(200, { "Content-Type": "application/json; charset=utf-8" });
  response.end(JSON.stringify(payload));
}

function sendFile(response, filePath, contentType) {
  fs.readFile(filePath, (error, content) => {
    if (error) {
      response.writeHead(404);
      response.end("Not found");
      return;
    }
    response.writeHead(200, { "Content-Type": contentType });
    response.end(content);
  });
}

const server = http.createServer((request, response) => {
  const url = new URL(request.url, `http://127.0.0.1:${port}`);

  if (url.pathname === "/") {
    const template = fs.readFileSync(path.join(root, "app", "templates", "index.html"), "utf8");
    response.writeHead(200, { "Content-Type": "text/html; charset=utf-8" });
    response.end(template.replaceAll("{{ app_name }}", "Paid Traffic Dashboard - Previa"));
    return;
  }

  if (url.pathname === "/static/app.js") {
    return sendFile(response, path.join(root, "app", "static", "app.js"), "application/javascript; charset=utf-8");
  }

  if (url.pathname === "/static/styles.css") {
    return sendFile(response, path.join(root, "app", "static", "styles.css"), "text/css; charset=utf-8");
  }

  if (url.pathname === "/auth/status") {
    return sendJson(response, {
      items: [
        { platform: "google", configured: true, has_local_token: true, has_refresh_token: true, has_env_token: false },
        { platform: "meta", configured: true, has_local_token: true, has_refresh_token: false, has_env_token: false },
      ],
    });
  }

  if (url.pathname === "/api/accounts") {
    return sendJson(response, {
      items: [
        { platform: "google", id: "1234567890", name: "Conta Google Ads Demo", currency: "BRL" },
        { platform: "meta", id: "act_1234567890", name: "Conta Meta Ads Demo", currency: "BRL" },
      ],
    });
  }

  if (url.pathname === "/api/campaigns") {
    return sendJson(response, {
      items: [
        { platform: "google", account_id: "1234567890", id: "google-1", name: "Search - Alta Intencao", status: "ENABLED" },
        { platform: "meta", account_id: "act_1234567890", id: "meta-1", name: "Instagram - Conversao", status: "ACTIVE" },
      ],
    });
  }

  if (url.pathname === "/api/dashboard") {
    return sendJson(response, {
      range: { start_date: "2026-06-11", end_date: "2026-07-10" },
      summary: summary(daily),
      daily,
    });
  }

  if (url.pathname === "/api/sync/status") {
    return sendJson(response, {
      last_run_at: "2026-07-10T09:00:00Z",
      source: "preview",
      start_date: "2026-06-11",
      end_date: "2026-07-10",
      ok: true,
      results: [
        { platform: "google", account_id: "1234567890", campaigns: 1, metric_rows: 5 },
        { platform: "meta", account_id: "act_1234567890", campaigns: 1, metric_rows: 5 },
      ],
    });
  }

  if (url.pathname === "/api/metrics") {
    return sendJson(response, { items: daily });
  }

  if (url.pathname === "/api/sync" && request.method === "POST") {
    return sendJson(response, {
      items: [
        { platform: "google", account_id: "1234567890", campaigns: 1, metric_rows: 5 },
        { platform: "meta", account_id: "act_1234567890", campaigns: 1, metric_rows: 5 },
      ],
    });
  }

  if (url.pathname === "/api/accounts/refresh" && request.method === "POST") {
    return sendJson(response, { items: [] });
  }

  if (url.pathname.startsWith("/api/export/")) {
    response.writeHead(200, { "Content-Type": "text/plain; charset=utf-8" });
    response.end("Na aplicacao Python real, este endpoint baixa PDF ou Excel.");
    return;
  }

  response.writeHead(404);
  response.end("Not found");
});

server.listen(port, "127.0.0.1", () => {
  console.log(`Preview running at http://127.0.0.1:${port}`);
});
