const state = {
  portfolios: [],
  selectedPortfolioId: null,
  tradeSide: "BUY",
  backtestDateSide: "BUY",
  chartTicker: null,
  chartDays: 30,
  chartInterval: null,
  chartHistory: [],
  comparePoints: [],
  backtestTrade: null,
};

async function refreshPortfolioList() {
  const res = await Api.listPortfolios();
  state.portfolios = await res.json();
  Render.portfolioList(state.portfolios, state.selectedPortfolioId, selectPortfolio, deletePortfolio);
  return state.portfolios;
}

async function deletePortfolio(id) {
  const portfolio = state.portfolios.find((p) => p.id === id);
  const name = portfolio ? portfolio.name : "this portfolio";
  if (!window.confirm(`Delete "${name}"? This removes its holdings, trade history, and alerts — it can't be undone.`)) {
    return;
  }

  try {
    const res = await Api.deletePortfolio(id);
    if (!res.ok) {
      const body = await res.json().catch(() => ({}));
      Render.createPortfolioStatus(`Error: ${body.error || "couldn't delete portfolio"}`, true);
      return;
    }
    const remaining = await refreshPortfolioList();
    if (id === state.selectedPortfolioId) {
      state.selectedPortfolioId = null;
      if (remaining.length > 0) {
        selectPortfolio(remaining[0].id);
      } else {
        Render.showEmptyPanel();
      }
    }
  } catch (err) {
    Render.createPortfolioStatus(`Request failed: ${err.message}`, true);
  }
}

async function selectPortfolio(id) {
  state.selectedPortfolioId = id;
  Render.portfolioList(state.portfolios, id, selectPortfolio, deletePortfolio);

  const portfolio = await refreshPortfolioDetail(id);
  Render.tradeStatus("");

  if (portfolio.holdings.length > 0) showChart(portfolio.holdings[0].ticker, state.chartDays);
  loadAlerts(id);
}

// Re-fetches and re-renders the stat cards / holdings table for the given portfolio without
// touching the chart or its locked compare points — used after a backtest trade, where the
// whole point is to keep the same chart/points visible so you can click a second point next.
async function refreshPortfolioDetail(id) {
  const res = await Api.getPortfolio(id);
  const portfolio = await res.json();
  Render.detail(portfolio, showChart);
  return portfolio;
}

async function loadAlerts(portfolioId) {
  try {
    const res = await Api.listAlerts(portfolioId);
    const alerts = await res.json();
    if (res.ok) Render.alertsList(alerts, (alertId) => dismissAlert(portfolioId, alertId));
  } catch (err) {
    console.error("alerts load failed:", err);
  }
}

async function dismissAlert(portfolioId, alertId) {
  try {
    await Api.markAlertRead(portfolioId, alertId);
    loadAlerts(portfolioId);
  } catch (err) {
    console.error("alert dismiss failed:", err);
  }
}

async function showChart(ticker, days = state.chartDays, interval = null) {
  state.chartTicker = ticker;
  state.chartDays = days;
  state.chartInterval = interval;
  state.comparePoints = [];
  state.backtestTrade = null;
  Render.rangeSelector(days, interval);
  Render.els.tickerInput.value = ticker;

  try {
    const res = await Api.getHistory(ticker, days, interval);
    const body = await res.json();
    if (res.ok) {
      state.chartHistory = body.history;
      renderChart();
    }
  } catch (err) {
    console.error("chart load failed:", err);
  }
}

function renderChart() {
  Render.priceChart(state.chartTicker, state.chartHistory, state.chartDays, state.comparePoints, handlePointClick);
  Render.comparisonPanel(state.comparePoints, state.chartHistory, state.backtestTrade, handleBacktestTrade);
}

function handlePointClick(index, point) {
  if (state.comparePoints.length >= 2) {
    state.comparePoints = [{ index, ...point }];
    state.backtestTrade = null;
  } else {
    state.comparePoints.push({ index, ...point });
  }
  renderChart();
}

async function handleBacktestTrade(side, quantity) {
  if (state.selectedPortfolioId === null || state.comparePoints.length !== 1) return;
  if (!quantity || quantity <= 0) return;

  const point = state.comparePoints[0];
  try {
    const res = await Api.submitTrade(state.selectedPortfolioId, state.chartTicker, side, quantity, point.date);
    const body = await res.json();
    if (res.ok) {
      state.backtestTrade = { index: point.index, side, quantity, price: body.transaction.price };
      renderChart();
      refreshPortfolioDetail(state.selectedPortfolioId); // refresh cash/holdings/total value only
    } else {
      Render.tradeStatus(`Error: ${body.error}`, true);
    }
  } catch (err) {
    Render.tradeStatus(`Request failed: ${err.message}`, true);
  }
}

const themeToggleEl = document.getElementById("theme-toggle");

function applyTheme(theme) {
  document.documentElement.dataset.theme = theme;
  if (themeToggleEl) themeToggleEl.textContent = theme === "dark" ? "Light mode" : "Dark mode";
}

applyTheme(document.documentElement.dataset.theme || "light");

themeToggleEl?.addEventListener("click", () => {
  const next = document.documentElement.dataset.theme === "dark" ? "light" : "dark";
  localStorage.setItem("tradenow_theme", next);
  applyTheme(next);
});

document.getElementById("chart-compare-clear")?.addEventListener("click", () => {
  state.comparePoints = [];
  state.backtestTrade = null;
  renderChart();
});

document.getElementById("range-selector")?.addEventListener("click", (event) => {
  const button = event.target.closest(".range-option");
  if (!button || state.chartTicker === null) return;
  if (button.dataset.interval) {
    showChart(state.chartTicker, state.chartDays, button.dataset.interval);
  } else {
    showChart(state.chartTicker, Number(button.dataset.days));
  }
});

const tickerInputEl = document.getElementById("chart-ticker-input");
const tickerComboboxEl = document.getElementById("ticker-combobox");

tickerInputEl?.addEventListener("focus", () => Render.tickerDropdown(tickerInputEl.value, chooseTicker));
tickerInputEl?.addEventListener("input", () => Render.tickerDropdown(tickerInputEl.value, chooseTicker));

document.addEventListener("click", (event) => {
  if (tickerComboboxEl && !tickerComboboxEl.contains(event.target)) Render.hideTickerDropdown();
});

function chooseTicker(ticker) {
  tickerInputEl.value = ticker;
  Render.hideTickerDropdown();
  showChart(ticker, state.chartDays);
}

document.getElementById("chart-ticker-form")?.addEventListener("submit", (event) => {
  event.preventDefault();
  Render.hideTickerDropdown();
  if (tickerInputEl.value.trim()) showChart(tickerInputEl.value.trim(), state.chartDays);
});

document.getElementById("create-portfolio-form")?.addEventListener("submit", async (event) => {
  event.preventDefault();
  const input = document.getElementById("new-portfolio-name");
  Render.createPortfolioStatus("Creating...", false);

  try {
    const res = await Api.createPortfolio(input.value);
    const body = await res.json();
    if (res.ok) {
      input.value = "";
      Render.createPortfolioStatus("");
      await refreshPortfolioList();
      selectPortfolio(body.id);
    } else {
      Render.createPortfolioStatus(`Error: ${body.error}`, true);
    }
  } catch (err) {
    Render.createPortfolioStatus(`Request failed: ${err.message}`, true);
  }
});

const landingEl = document.getElementById("landing");
const registerEl = document.getElementById("register");

document.getElementById("show-register")?.addEventListener("click", (event) => {
  event.preventDefault();
  landingEl.hidden = true;
  registerEl.hidden = false;
});

document.getElementById("show-login")?.addEventListener("click", (event) => {
  event.preventDefault();
  registerEl.hidden = true;
  landingEl.hidden = false;
});

document.getElementById("register-form")?.addEventListener("submit", async (event) => {
  event.preventDefault();
  const displayName = document.getElementById("register-display-name").value.trim();
  const email = document.getElementById("register-email").value.trim();
  const password = document.getElementById("register-password").value;
  const confirm = document.getElementById("register-confirm").value;
  const statusEl = document.getElementById("register-status");

  if (password !== confirm) {
    statusEl.textContent = "Passwords don't match.";
    statusEl.classList.add("status-error");
    return;
  }

  statusEl.textContent = "Creating your account...";
  statusEl.classList.remove("status-error");

  try {
    const res = await Api.register(displayName, email, password);
    const body = await res.json();
    if (res.ok) {
      statusEl.textContent = "Account created — redirecting to log in...";
      window.setTimeout(() => { window.location.href = Api.loginUrl; }, 1200);
    } else {
      statusEl.textContent = `Error: ${body.error}`;
      statusEl.classList.add("status-error");
    }
  } catch (err) {
    statusEl.textContent = `Request failed: ${err.message}`;
    statusEl.classList.add("status-error");
  }
});

async function downloadFromResponse(fetchPromise, filename, statusEl) {
  try {
    const res = await fetchPromise;
    if (!res.ok) {
      const body = await res.json();
      statusEl.textContent = `Error: ${body.error}`;
      statusEl.classList.add("status-error");
      return;
    }
    const blob = await res.blob();
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = filename;
    link.click();
    URL.revokeObjectURL(url);
    statusEl.textContent = "";
  } catch (err) {
    statusEl.textContent = `Request failed: ${err.message}`;
    statusEl.classList.add("status-error");
  }
}

document.getElementById("export-pdf-button")?.addEventListener("click", () => {
  if (state.selectedPortfolioId === null) return;
  const statusEl = document.getElementById("export-pdf-status");
  statusEl.textContent = "Generating PDF...";
  statusEl.classList.remove("status-error");
  downloadFromResponse(Api.getStatementPdf(state.selectedPortfolioId), "statement.pdf", statusEl);
});

document.getElementById("export-csv-button")?.addEventListener("click", () => {
  if (state.selectedPortfolioId === null) return;
  const statusEl = document.getElementById("export-csv-status");
  statusEl.textContent = "Generating CSV...";
  statusEl.classList.remove("status-error");
  downloadFromResponse(Api.getTransactionsCsv(state.selectedPortfolioId), "transactions.csv", statusEl);
});

document.getElementById("trade-side-toggle")?.addEventListener("click", (event) => {
  const button = event.target.closest(".segmented-option");
  if (!button) return;
  state.tradeSide = button.dataset.value;
  document.querySelectorAll("#trade-side-toggle .segmented-option").forEach((el) => {
    el.classList.toggle("selected", el === button);
  });
});

const backtestDateInputEl = document.getElementById("backtest-date");
if (backtestDateInputEl) backtestDateInputEl.max = new Date().toISOString().slice(0, 10);

document.getElementById("backtest-date-side-toggle")?.addEventListener("click", (event) => {
  const button = event.target.closest(".segmented-option");
  if (!button) return;
  state.backtestDateSide = button.dataset.value;
  document.querySelectorAll("#backtest-date-side-toggle .segmented-option").forEach((el) => {
    el.classList.toggle("selected", el === button);
  });
});

document.getElementById("backtest-date-form")?.addEventListener("submit", async (event) => {
  event.preventDefault();
  if (state.selectedPortfolioId === null || state.chartTicker === null) return;

  const date = document.getElementById("backtest-date").value;
  const quantity = Number(document.getElementById("backtest-date-quantity").value);
  const statusEl = document.getElementById("backtest-date-status");
  statusEl.textContent = "Submitting...";
  statusEl.classList.remove("status-error");

  try {
    const res = await Api.submitTrade(state.selectedPortfolioId, state.chartTicker, state.backtestDateSide, quantity, date);
    const body = await res.json();

    if (res.ok) {
      const dateNote = body.actual_trade_date !== date
        ? ` — market closed that day, used ${body.actual_trade_date}`
        : "";
      statusEl.textContent = `${state.backtestDateSide} ${quantity} ${state.chartTicker} @ ${formatMoney(body.transaction.price)}${dateNote}`;
      statusEl.classList.remove("status-error");
      refreshPortfolioDetail(state.selectedPortfolioId);
    } else {
      statusEl.textContent = `Error: ${body.error}`;
      statusEl.classList.add("status-error");
    }
  } catch (err) {
    statusEl.textContent = `Request failed: ${err.message}`;
    statusEl.classList.add("status-error");
  }
});

document.getElementById("trade-form")?.addEventListener("submit", async (event) => {
  event.preventDefault();
  if (state.selectedPortfolioId === null) return;

  const ticker = document.getElementById("trade-ticker").value;
  const quantity = Number(document.getElementById("trade-quantity").value);

  Render.tradeStatus("Submitting...");
  try {
    const res = await Api.submitTrade(state.selectedPortfolioId, ticker, state.tradeSide, quantity);
    const body = await res.json();

    if (res.ok) {
      const staleNote = body.price_stale ? " (stale price)" : "";
      Render.tradeStatus(`${state.tradeSide} ${quantity} ${ticker} @ ${formatMoney(body.transaction.price)}${staleNote}`, false);
      document.getElementById("trade-ticker").value = "";
      document.getElementById("trade-quantity").value = "";
      selectPortfolio(state.selectedPortfolioId);
    } else {
      Render.tradeStatus(`Error: ${body.error}`, true);
    }
  } catch (err) {
    Render.tradeStatus(`Request failed: ${err.message}`, true);
  }
});

async function init() {
  try {
    Api.captureTokenFromUrl();
    const res = await Api.me();
    const me = await res.json();

    if (!me.authenticated) {
      Render.showSignedOut();
      return;
    }

    Render.showSignedIn(me.email);
    Render.showEmptyPanel();
    const portfolios = await refreshPortfolioList();
    if (portfolios.length > 0) selectPortfolio(portfolios[0].id);
    loadTrends();
    loadWatchlist();
  } catch (err) {
    console.error("init failed:", err);
    Render.showSignedOut();
  }
}

async function loadWatchlist() {
  try {
    const res = await Api.getWatchlist();
    const body = await res.json();
    if (res.ok) {
      Render.watchlist(body, deleteWatchlistItem);
    }
  } catch (err) {
    Render.watchlistStatus("Watchlist unavailable — request failed.", true);
  }
}

async function deleteWatchlistItem(id) {
  try {
    const res = await Api.deleteWatchlistItem(id);
    if (res.ok) loadWatchlist();
  } catch (err) {
    Render.watchlistStatus(`Request failed: ${err.message}`, true);
  }
}

const watchlistDirectionEl = document.getElementById("watchlist-direction");
const watchlistTargetEl = document.getElementById("watchlist-target");
watchlistDirectionEl?.addEventListener("change", () => {
  const hasAlert = Boolean(watchlistDirectionEl.value);
  watchlistTargetEl.disabled = !hasAlert;
  watchlistTargetEl.required = hasAlert;
  if (!hasAlert) watchlistTargetEl.value = "";
});

document.getElementById("watchlist-form")?.addEventListener("submit", async (event) => {
  event.preventDefault();
  const ticker = document.getElementById("watchlist-ticker").value;
  const direction = watchlistDirectionEl.value || null;
  const target = direction ? Number(watchlistTargetEl.value) : null;

  Render.watchlistStatus("Adding...");
  try {
    const res = await Api.addWatchlistItem(ticker, direction, target);
    const body = await res.json();
    if (res.ok) {
      Render.watchlistStatus("");
      document.getElementById("watchlist-ticker").value = "";
      watchlistDirectionEl.value = "";
      watchlistTargetEl.value = "";
      watchlistTargetEl.disabled = true;
      loadWatchlist();
    } else {
      Render.watchlistStatus(`Error: ${body.error}`, true);
    }
  } catch (err) {
    Render.watchlistStatus(`Request failed: ${err.message}`, true);
  }
});

async function loadTrends() {
  try {
    const res = await Api.getLatestTrends();
    const body = await res.json();
    if (res.ok && body.length > 0) {
      Render.trendsStatus("");
      Render.trendsTable(body);
      Render.trendsChart(body);
    } else if (res.ok) {
      Render.trendsStatus("No trend report yet — the scheduled job hasn't run.");
    } else {
      Render.trendsStatus(`Trends unavailable: ${body.error || res.status}`);
    }
  } catch (err) {
    Render.trendsStatus("Trends unavailable — request failed.");
  }
}

init();
