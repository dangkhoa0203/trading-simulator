const API_BASE = "https://trading-simulator-cern.onrender.com";
const TOKEN_STORAGE_KEY = "tradenow_token";

const Api = {
  base: API_BASE,
  loginUrl: `${API_BASE}/login`,
  logoutUrl: `${API_BASE}/logout`,

  // Pulls ?token=... off the URL after the Auth0 redirect lands back here, stores it, and
  // cleans the URL so the token doesn't linger in browser history / get shared via a copied
  // link. Bearer token, not a cookie: the frontend and API are on different sites (different
  // AWS public suffixes), so a session cookie would be a third-party cookie and gets blocked
  // by Safari ITP / Chrome's third-party cookie phaseout.
  captureTokenFromUrl() {
    const params = new URLSearchParams(window.location.search);
    const token = params.get("token");
    if (token) {
      localStorage.setItem(TOKEN_STORAGE_KEY, token);
      params.delete("token");
      const cleanUrl = window.location.pathname + (params.toString() ? `?${params}` : "");
      window.history.replaceState({}, "", cleanUrl);
    }
  },

  getToken() {
    return localStorage.getItem(TOKEN_STORAGE_KEY);
  },

  clearToken() {
    localStorage.removeItem(TOKEN_STORAGE_KEY);
  },

  async request(path, options = {}) {
    const token = this.getToken();
    const headers = { "Content-Type": "application/json", ...options.headers };
    if (token) headers.Authorization = `Bearer ${token}`;

    const res = await fetch(API_BASE + path, {
      credentials: "include",
      headers,
      ...options,
    });
    return res;
  },

  me() {
    return this.request("/me");
  },

  register(displayName, email, password) {
    return this.request("/register", {
      method: "POST",
      body: JSON.stringify({ display_name: displayName, email, password }),
    });
  },

  listPortfolios() {
    return this.request("/api/portfolios");
  },

  createPortfolio(name) {
    return this.request("/api/portfolios", {
      method: "POST",
      body: JSON.stringify({ name }),
    });
  },

  getPortfolio(id) {
    return this.request(`/api/portfolios/${id}`);
  },

  deletePortfolio(id) {
    return this.request(`/api/portfolios/${id}`, { method: "DELETE" });
  },

  submitTrade(portfolioId, ticker, side, quantity, date = null) {
    const body = { ticker, side, quantity };
    if (date) body.date = date;
    return this.request(`/api/portfolios/${portfolioId}/trades`, {
      method: "POST",
      body: JSON.stringify(body),
    });
  },

  getHistory(ticker, days = 30, interval = null) {
    const params = interval ? `interval=${interval}` : `days=${days}`;
    return this.request(`/api/market/history/${encodeURIComponent(ticker)}?${params}`);
  },

  getLatestTrends() {
    return this.request("/api/reports/latest");
  },

  listAlerts(portfolioId) {
    return this.request(`/api/portfolios/${portfolioId}/alerts`);
  },

  markAlertRead(portfolioId, alertId) {
    return this.request(`/api/portfolios/${portfolioId}/alerts/${alertId}/read`, { method: "POST" });
  },

  getStatementPdf(portfolioId) {
    return this.request(`/api/portfolios/${portfolioId}/statement.pdf`);
  },

  getTransactionsCsv(portfolioId) {
    return this.request(`/api/portfolios/${portfolioId}/transactions.csv`);
  },

  getWatchlist() {
    return this.request("/api/watchlist");
  },

  addWatchlistItem(ticker, alertDirection = null, targetPrice = null) {
    const body = { ticker };
    if (alertDirection) {
      body.alert_direction = alertDirection;
      body.target_price = targetPrice;
    }
    return this.request("/api/watchlist", { method: "POST", body: JSON.stringify(body) });
  },

  deleteWatchlistItem(id) {
    return this.request(`/api/watchlist/${id}`, { method: "DELETE" });
  },
};
