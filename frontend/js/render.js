function formatMoney(value) {
  if (value == null) return "—";
  return `$${value.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
}

function parseHistoryDate(dateStr) {
  return new Date(dateStr.length > 10 ? dateStr : `${dateStr}T00:00:00`);
}

function formatAxisDate(dateStr, days) {
  const d = parseHistoryDate(dateStr);
  // Intraday bars carry a time component ("YYYY-MM-DD HH:MM:SS") — a plain daily/weekly/
  // monthly close is just "YYYY-MM-DD" (10 chars). Time is the useful axis label there.
  if (dateStr.length > 10) return d.toLocaleTimeString(undefined, { hour: "2-digit", minute: "2-digit" });
  if (days > 180) return d.toLocaleDateString(undefined, { month: "short", year: "2-digit" });
  return d.toLocaleDateString(undefined, { month: "short", day: "numeric" });
}

function formatTooltipDate(dateStr) {
  const d = parseHistoryDate(dateStr);
  const opts = { weekday: "short", month: "short", day: "numeric", year: "numeric" };
  if (dateStr.length > 10) {
    opts.hour = "2-digit";
    opts.minute = "2-digit";
  }
  return d.toLocaleDateString(undefined, opts);
}

const Render = {
  els: {
    authArea: document.getElementById("auth-area"),
    landing: document.getElementById("landing"),
    landingLogin: document.getElementById("landing-login"),
    app: document.getElementById("app"),
    portfolioList: document.getElementById("portfolio-list"),
    portfolioListEmpty: document.getElementById("portfolio-list-empty"),
    detailPanel: document.getElementById("detail-panel"),
    emptyPanel: document.getElementById("empty-panel"),
    detailName: document.getElementById("detail-name"),
    detailCash: document.getElementById("detail-cash"),
    detailTotal: document.getElementById("detail-total"),
    holdingsBody: document.getElementById("holdings-body"),
    holdingsEmpty: document.getElementById("holdings-empty"),
    tradeStatus: document.getElementById("trade-status"),
    createPortfolioStatus: document.getElementById("create-portfolio-status"),
    chartPanel: document.getElementById("chart-panel"),
    chartTitle: document.getElementById("chart-title"),
    chartMeta: document.getElementById("chart-meta"),
    priceChart: document.getElementById("price-chart"),
    chartTooltip: document.getElementById("chart-tooltip"),
    chartCompare: document.getElementById("chart-compare"),
    chartCompareBody: document.getElementById("chart-compare-body"),
    rangeSelector: document.getElementById("range-selector"),
    tickerInput: document.getElementById("chart-ticker-input"),
    tickerDropdown: document.getElementById("ticker-dropdown"),
    trendsStatus: document.getElementById("trends-status"),
    trendsTable: document.getElementById("trends-table"),
    trendsBody: document.getElementById("trends-body"),
    trendsChart: document.getElementById("trends-chart"),
    alertsList: document.getElementById("alerts-list"),
    watchlistTable: document.getElementById("watchlist-table"),
    watchlistBody: document.getElementById("watchlist-body"),
    watchlistEmpty: document.getElementById("watchlist-empty"),
    watchlistStatus: document.getElementById("watchlist-status"),
  },

  showSignedOut() {
    this.els.landing.hidden = false;
    this.els.app.hidden = true;
    this.els.landingLogin.href = Api.loginUrl;

    this.els.authArea.textContent = "";
    const link = document.createElement("a");
    link.className = "button button-primary";
    link.href = Api.loginUrl;
    link.textContent = "Log in";
    this.els.authArea.appendChild(link);
  },

  showSignedIn(email) {
    this.els.landing.hidden = true;
    this.els.app.hidden = false;

    this.els.authArea.textContent = "";
    const emailSpan = document.createElement("span");
    emailSpan.className = "user-email";
    emailSpan.textContent = email;
    const link = document.createElement("a");
    link.className = "button button-secondary";
    link.href = Api.logoutUrl;
    link.textContent = "Log out";
    link.addEventListener("click", () => Api.clearToken());
    this.els.authArea.appendChild(emailSpan);
    this.els.authArea.appendChild(link);
  },

  portfolioList(portfolios, selectedId, onSelect, onDelete) {
    this.els.portfolioList.textContent = "";
    this.els.portfolioListEmpty.hidden = portfolios.length > 0;

    for (const portfolio of portfolios) {
      const li = document.createElement("li");
      li.className = "portfolio-list-item";
      if (portfolio.id === selectedId) li.classList.add("selected");
      li.addEventListener("click", () => onSelect(portfolio.id));

      const name = document.createElement("span");
      name.className = "portfolio-list-name";
      name.textContent = portfolio.name;
      li.appendChild(name);

      const del = document.createElement("button");
      del.type = "button";
      del.className = "portfolio-list-delete";
      del.textContent = "✕";
      del.setAttribute("aria-label", `Delete ${portfolio.name}`);
      del.addEventListener("click", (event) => {
        event.stopPropagation(); // don't also trigger the row's onSelect
        onDelete(portfolio.id);
      });
      li.appendChild(del);

      this.els.portfolioList.appendChild(li);
    }
  },

  detail(portfolio, onSelectTicker) {
    this.els.emptyPanel.hidden = true;
    this.els.detailPanel.hidden = false;

    this.els.detailName.textContent = portfolio.name;
    this.els.detailCash.textContent = formatMoney(portfolio.cash_balance);
    this.els.detailTotal.textContent = formatMoney(portfolio.total_value);

    this.els.holdingsBody.textContent = "";
    this.els.holdingsEmpty.hidden = portfolio.holdings.length > 0;

    for (const holding of portfolio.holdings) {
      const row = document.createElement("tr");
      const cells = [
        holding.ticker,
        holding.quantity,
        formatMoney(holding.avg_cost),
        holding.current_price != null ? formatMoney(holding.current_price) : "—",
        holding.market_value != null ? formatMoney(holding.market_value) : "—",
      ];
      for (const value of cells) {
        const td = document.createElement("td");
        td.textContent = value;
        row.appendChild(td);
      }
      row.addEventListener("click", () => onSelectTicker(holding.ticker));
      this.els.holdingsBody.appendChild(row);
    }
  },

  priceChart(ticker, history, days, comparePoints = [], onPointClick = () => {}) {
    this.els.chartTitle.textContent = ticker;
    const ns = "http://www.w3.org/2000/svg";
    const svg = this.els.priceChart;
    while (svg.firstChild) svg.removeChild(svg.firstChild);
    // Pinned-point labels are plain HTML siblings of the SVG (so real text stays crisp),
    // added fresh below — clear last render's before rebuilding.
    svg.parentElement.querySelectorAll(".chart-point-label").forEach((el) => el.remove());

    if (history.length < 2) {
      this.els.chartPanel.hidden = true;
      return;
    }
    this.els.chartPanel.hidden = false;

    const width = 600;
    const height = 220;
    const margin = { top: 14, right: 12, bottom: 26, left: 54 };
    const plotWidth = width - margin.left - margin.right;
    const plotHeight = height - margin.top - margin.bottom;

    const closes = history.map((h) => h.close);
    const min = Math.min(...closes);
    const max = Math.max(...closes);
    const range = max - min || 1;

    const xAt = (i) => margin.left + (i / (history.length - 1)) * plotWidth;
    const yAt = (close) => margin.top + (1 - (close - min) / range) * plotHeight;

    const trendUp = closes[closes.length - 1] >= closes[0];
    const color = trendUp ? "#1f7a5c" : "#a93a2e";
    const gradientId = "chart-fill-gradient";

    // Gridlines + y-axis price labels at min/mid/max.
    [min, min + range / 2, max].forEach((value) => {
      const y = yAt(value);
      const line = document.createElementNS(ns, "line");
      line.setAttribute("class", "chart-gridline");
      line.setAttribute("x1", margin.left);
      line.setAttribute("x2", width - margin.right);
      line.setAttribute("y1", y.toFixed(1));
      line.setAttribute("y2", y.toFixed(1));
      svg.appendChild(line);

      const label = document.createElementNS(ns, "text");
      label.setAttribute("class", "chart-axis-label");
      label.setAttribute("x", margin.left - 6);
      label.setAttribute("y", (y + 3).toFixed(1));
      label.setAttribute("text-anchor", "end");
      label.textContent = formatMoney(value);
      svg.appendChild(label);
    });

    // X-axis date labels: first, thirds, last.
    const labelIndices = [0, Math.round((history.length - 1) / 3), Math.round(((history.length - 1) * 2) / 3), history.length - 1];
    [...new Set(labelIndices)].forEach((i) => {
      const label = document.createElementNS(ns, "text");
      label.setAttribute("class", "chart-axis-label");
      label.setAttribute("x", xAt(i).toFixed(1));
      label.setAttribute("y", height - 6);
      label.setAttribute("text-anchor", i === 0 ? "start" : i === history.length - 1 ? "end" : "middle");
      label.textContent = formatAxisDate(history[i].date, days);
      svg.appendChild(label);
    });

    const linePoints = history.map((h, i) => [xAt(i), yAt(h.close)]);

    // Area fill under the line, fading to transparent.
    const gradient = document.createElementNS(ns, "linearGradient");
    gradient.setAttribute("id", gradientId);
    gradient.setAttribute("x1", "0");
    gradient.setAttribute("y1", "0");
    gradient.setAttribute("x2", "0");
    gradient.setAttribute("y2", "1");
    const stop1 = document.createElementNS(ns, "stop");
    stop1.setAttribute("offset", "0%");
    stop1.setAttribute("stop-color", color);
    stop1.setAttribute("stop-opacity", "0.25");
    const stop2 = document.createElementNS(ns, "stop");
    stop2.setAttribute("offset", "100%");
    stop2.setAttribute("stop-color", color);
    stop2.setAttribute("stop-opacity", "0");
    gradient.appendChild(stop1);
    gradient.appendChild(stop2);
    const defs = document.createElementNS(ns, "defs");
    defs.appendChild(gradient);
    svg.appendChild(defs);

    const baseline = margin.top + plotHeight;
    const areaPoints = [[linePoints[0][0], baseline], ...linePoints, [linePoints[linePoints.length - 1][0], baseline]];
    const area = document.createElementNS(ns, "polygon");
    area.setAttribute("points", areaPoints.map(([x, y]) => `${x.toFixed(1)},${y.toFixed(1)}`).join(" "));
    area.setAttribute("fill", `url(#${gradientId})`);
    svg.appendChild(area);

    const polyline = document.createElementNS(ns, "polyline");
    polyline.setAttribute("points", linePoints.map(([x, y]) => `${x.toFixed(1)},${y.toFixed(1)}`).join(" "));
    polyline.setAttribute("fill", "none");
    polyline.setAttribute("stroke", color);
    polyline.setAttribute("stroke-width", "2");
    polyline.setAttribute("stroke-linejoin", "round");
    polyline.setAttribute("stroke-linecap", "round");
    svg.appendChild(polyline);

    const first = closes[0];
    const last = closes[closes.length - 1];
    const changePct = ((last - first) / first) * 100;
    const sign = changePct >= 0 ? "+" : "";
    this.els.chartMeta.textContent = `${formatMoney(last)} (${sign}${changePct.toFixed(2)}%)`;
    this.els.chartMeta.style.color = color;

    // Locked comparison points (click-to-lock): shaded range + a solid marker line per point.
    const compareColors = ["#146356", "#c77d20"];
    if (comparePoints.length === 2) {
      const sorted = [...comparePoints].sort((a, b) => a.index - b.index);
      const rectX1 = xAt(sorted[0].index);
      const rectX2 = xAt(sorted[1].index);
      const band = document.createElementNS(ns, "rect");
      band.setAttribute("x", Math.min(rectX1, rectX2).toFixed(1));
      band.setAttribute("y", margin.top);
      band.setAttribute("width", Math.abs(rectX2 - rectX1).toFixed(1));
      band.setAttribute("height", plotHeight);
      band.setAttribute("fill", "#146356");
      band.setAttribute("fill-opacity", "0.08");
      band.setAttribute("pointer-events", "none");
      svg.appendChild(band);
    }
    comparePoints.forEach((point, i) => {
      const px = xAt(point.index);
      const py = yAt(history[point.index].close);
      const markerColor = compareColors[i % compareColors.length];

      const line = document.createElementNS(ns, "line");
      line.setAttribute("x1", px.toFixed(1));
      line.setAttribute("x2", px.toFixed(1));
      line.setAttribute("y1", margin.top);
      line.setAttribute("y2", margin.top + plotHeight);
      line.setAttribute("stroke", markerColor);
      line.setAttribute("stroke-width", "2");
      line.setAttribute("pointer-events", "none");
      svg.appendChild(line);

      const dot = document.createElementNS(ns, "circle");
      dot.setAttribute("cx", px.toFixed(1));
      dot.setAttribute("cy", py.toFixed(1));
      dot.setAttribute("r", "5");
      dot.setAttribute("fill", markerColor);
      dot.setAttribute("stroke", "#fff");
      dot.setAttribute("stroke-width", "2");
      dot.setAttribute("pointer-events", "none");
      svg.appendChild(dot);

      // A persistent date/price box for this pinned point — same look as the hover
      // tooltip, but it stays put instead of disappearing when the mouse leaves.
      const label = document.createElement("div");
      label.className = "chart-tooltip chart-point-label";
      label.style.borderColor = markerColor;
      const dateLine = document.createElement("div");
      dateLine.className = "chart-tooltip-date";
      dateLine.textContent = formatTooltipDate(history[point.index].date);
      const priceLine = document.createElement("div");
      priceLine.className = "chart-tooltip-price";
      priceLine.textContent = formatMoney(history[point.index].close);
      label.appendChild(dateLine);
      label.appendChild(priceLine);
      svg.parentElement.appendChild(label);

      const svgRect = svg.getBoundingClientRect();
      const containerRect = svg.parentElement.getBoundingClientRect();
      label.style.left = `${(px / width) * svgRect.width + (svgRect.left - containerRect.left)}px`;
      label.style.top = `${(py / height) * svgRect.height + (svgRect.top - containerRect.top)}px`;
    });

    // Hover interaction: crosshair + dot + tooltip tracking the nearest data point.
    const crosshair = document.createElementNS(ns, "line");
    crosshair.setAttribute("y1", margin.top);
    crosshair.setAttribute("y2", margin.top + plotHeight);
    crosshair.setAttribute("stroke", "#4b5a53");
    crosshair.setAttribute("stroke-width", "1");
    crosshair.setAttribute("stroke-dasharray", "3,3");
    crosshair.setAttribute("pointer-events", "none");
    crosshair.style.display = "none";
    svg.appendChild(crosshair);

    const hoverDot = document.createElementNS(ns, "circle");
    hoverDot.setAttribute("r", "4");
    hoverDot.setAttribute("fill", color);
    hoverDot.setAttribute("stroke", "#fff");
    hoverDot.setAttribute("stroke-width", "1.5");
    hoverDot.setAttribute("pointer-events", "none");
    hoverDot.style.display = "none";
    svg.appendChild(hoverDot);

    const overlay = document.createElementNS(ns, "rect");
    overlay.setAttribute("x", margin.left);
    overlay.setAttribute("y", 0);
    overlay.setAttribute("width", plotWidth);
    overlay.setAttribute("height", height);
    overlay.setAttribute("fill", "transparent");
    overlay.style.cursor = "crosshair";
    svg.appendChild(overlay);

    const tooltip = this.els.chartTooltip;

    const indexFromClientX = (clientX) => {
      const rect = svg.getBoundingClientRect();
      const svgX = ((clientX - rect.left) / rect.width) * width;
      const idx = Math.round(((svgX - margin.left) / plotWidth) * (history.length - 1));
      return Math.max(0, Math.min(history.length - 1, idx));
    };

    const showAtClientPoint = (clientX, clientY) => {
      const idx = indexFromClientX(clientX);
      const px = xAt(idx);
      const py = yAt(history[idx].close);

      crosshair.setAttribute("x1", px);
      crosshair.setAttribute("x2", px);
      crosshair.style.display = "block";
      hoverDot.setAttribute("cx", px);
      hoverDot.setAttribute("cy", py);
      hoverDot.style.display = "block";

      tooltip.textContent = "";
      const dateLine = document.createElement("div");
      dateLine.className = "chart-tooltip-date";
      dateLine.textContent = formatTooltipDate(history[idx].date);
      const priceLine = document.createElement("div");
      priceLine.className = "chart-tooltip-price";
      priceLine.textContent = formatMoney(history[idx].close);
      tooltip.appendChild(dateLine);
      tooltip.appendChild(priceLine);

      // `rect` isn't in scope here — indexFromClientX() has its own copy. Read it fresh
      // rather than threading it through, since it's cheap and avoids staleness on resize.
      const svgRect = svg.getBoundingClientRect();
      const containerRect = svg.parentElement.getBoundingClientRect();
      tooltip.style.left = `${(px / width) * svgRect.width + (svgRect.left - containerRect.left)}px`;
      tooltip.style.top = `${(py / height) * svgRect.height + (svgRect.top - containerRect.top)}px`;
      tooltip.hidden = false;
    };

    const hideHover = () => {
      crosshair.style.display = "none";
      hoverDot.style.display = "none";
      tooltip.hidden = true;
    };

    overlay.addEventListener("mousemove", (e) => showAtClientPoint(e.clientX, e.clientY));
    overlay.addEventListener("mouseleave", hideHover);
    overlay.addEventListener(
      "touchmove",
      (e) => {
        if (e.touches[0]) showAtClientPoint(e.touches[0].clientX, e.touches[0].clientY);
        e.preventDefault();
      },
      { passive: false }
    );
    overlay.addEventListener("touchend", hideHover);
    overlay.addEventListener("click", (e) => {
      const idx = indexFromClientX(e.clientX);
      onPointClick(idx, history[idx]);
    });
  },

  _comparePointLabel(point, colorIndex) {
    const span = document.createElement("span");
    span.className = "compare-point";
    const dot = document.createElement("span");
    dot.className = "compare-dot";
    dot.style.background = colorIndex === 0 ? "#146356" : "#c77d20";
    const label = document.createElement("span");
    // Always show month+day here, regardless of the chart's overall range — passing the
    // real range (e.g. 365) makes formatAxisDate switch to "month + 2-digit year" for
    // long ranges, which read as "Sep 26" (September '26) and looked identical for any
    // two points landing in the same month.
    label.textContent = `${formatAxisDate(point.date, 1)} · ${formatMoney(point.close)}`;
    span.appendChild(dot);
    span.appendChild(label);
    return span;
  },

  comparisonPanel(comparePoints, history, backtestTrade, onTrade) {
    const panel = this.els.chartCompare;
    const body = this.els.chartCompareBody;
    body.textContent = "";

    if (comparePoints.length === 0) {
      panel.hidden = true;
      return;
    }
    panel.hidden = false;

    if (comparePoints.length === 1) {
      const point = history[comparePoints[0].index];
      const row = document.createElement("div");
      row.className = "compare-row";
      row.appendChild(this._comparePointLabel(point, 0));
      body.appendChild(row);

      if (backtestTrade && backtestTrade.index === comparePoints[0].index) {
        const note = document.createElement("div");
        note.className = "compare-days";
        note.textContent = `${backtestTrade.side === "BUY" ? "Bought" : "Sold"} ${backtestTrade.quantity} @ ${formatMoney(backtestTrade.price)} here — click another point to check win/loss.`;
        body.appendChild(note);
      } else {
        const form = document.createElement("div");
        form.className = "compare-trade-form";
        const qty = document.createElement("input");
        qty.type = "number";
        qty.min = "0";
        qty.step = "any";
        qty.placeholder = "Quantity";
        const buyBtn = document.createElement("button");
        buyBtn.type = "button";
        buyBtn.className = "button button-primary";
        buyBtn.textContent = "Buy here";
        const sellBtn = document.createElement("button");
        sellBtn.type = "button";
        sellBtn.className = "button button-secondary";
        sellBtn.textContent = "Sell here";
        buyBtn.addEventListener("click", () => onTrade("BUY", Number(qty.value)));
        sellBtn.addEventListener("click", () => onTrade("SELL", Number(qty.value)));
        form.appendChild(qty);
        form.appendChild(buyBtn);
        form.appendChild(sellBtn);
        body.appendChild(form);
      }
      return;
    }

    const sorted = [...comparePoints].sort((a, b) => a.index - b.index);
    const pointA = history[sorted[0].index];
    const pointB = history[sorted[1].index];
    const days = Math.round((parseHistoryDate(pointB.date) - parseHistoryDate(pointA.date)) / 86400000);
    // Dot colour follows click order (matches the chart's markers, which are coloured by
    // comparePoints[0]/[1] i.e. first/second click) — not chronological order. If the later
    // point was clicked first, sorted[0] (the earlier date, shown on the left here) is
    // actually the second click, so it needs the second colour.
    const colorA = sorted[0].index === comparePoints[0].index ? 0 : 1;
    const colorB = sorted[1].index === comparePoints[0].index ? 0 : 1;
    const dollarChange = pointB.close - pointA.close;
    const pctChange = (dollarChange / pointA.close) * 100;
    const up = dollarChange >= 0;
    const sign = up ? "+" : "";

    const row = document.createElement("div");
    row.className = "compare-row";

    const arrow = document.createElement("span");
    arrow.className = "compare-arrow";
    arrow.textContent = "→";

    const summary = document.createElement("span");
    summary.className = `compare-summary ${up ? "up" : "down"}`;
    summary.textContent = `${sign}${formatMoney(Math.abs(dollarChange))} (${sign}${pctChange.toFixed(2)}%)`;

    const daysLabel = document.createElement("span");
    daysLabel.className = "compare-days";
    daysLabel.textContent = `${days} day${days === 1 ? "" : "s"}`;

    row.appendChild(this._comparePointLabel(pointA, colorA));
    row.appendChild(arrow);
    row.appendChild(this._comparePointLabel(pointB, colorB));
    row.appendChild(summary);
    row.appendChild(daysLabel);
    body.appendChild(row);

    // The backtest trade sits at whichever point was clicked first (comparePoints[0]),
    // which isn't necessarily the chronologically-earlier one (sorted[0]) — check both
    // and compare against whichever point it isn't, or a later-then-earlier click order
    // would silently hide the win/loss row entirely.
    const tradeIsPointA = backtestTrade && backtestTrade.index === sorted[0].index;
    const tradeIsPointB = backtestTrade && backtestTrade.index === sorted[1].index;
    if (tradeIsPointA || tradeIsPointB) {
      const otherPoint = tradeIsPointA ? pointB : pointA;
      const direction = backtestTrade.side === "SELL" ? -1 : 1;
      const pnl = (otherPoint.close - backtestTrade.price) * backtestTrade.quantity * direction;
      const pnlPct = ((otherPoint.close - backtestTrade.price) / backtestTrade.price) * 100 * direction;
      const pnlUp = pnl >= 0;
      const pnlSign = pnlUp ? "+" : "";

      const pnlRow = document.createElement("div");
      pnlRow.className = "compare-row";
      const label = document.createElement("span");
      label.textContent = `Position: ${backtestTrade.side} ${backtestTrade.quantity} @ ${formatMoney(backtestTrade.price)} →`;
      const result = document.createElement("span");
      result.className = `compare-summary ${pnlUp ? "up" : "down"}`;
      result.textContent = `${pnlUp ? "WIN " : "LOSS "}${pnlSign}${formatMoney(Math.abs(pnl))} (${pnlSign}${pnlPct.toFixed(2)}%)`;
      pnlRow.appendChild(label);
      pnlRow.appendChild(result);
      body.appendChild(pnlRow);
    }
  },

  rangeSelector(selectedDays, selectedInterval) {
    this.els.rangeSelector.querySelectorAll(".range-option").forEach((btn) => {
      const selected = selectedInterval
        ? btn.dataset.interval === selectedInterval
        : !btn.dataset.interval && Number(btn.dataset.days) === selectedDays;
      btn.classList.toggle("selected", selected);
    });
  },

  tickerDropdown(query, onSelect) {
    const dropdown = this.els.tickerDropdown;
    dropdown.textContent = "";
    const q = query.trim().toLowerCase();

    let anyMatch = false;
    for (const group of TICKER_CATALOG) {
      const matches = q
        ? group.tickers.filter((s) => s.ticker.toLowerCase().includes(q) || s.name.toLowerCase().includes(q))
        : group.tickers;
      if (q && matches.length === 0) continue;

      anyMatch = anyMatch || matches.length > 0;

      const header = document.createElement("div");
      header.className = "combobox-category";
      const expanded = Boolean(q) || group.expanded;
      header.textContent = `${group.category} ${expanded ? "▾" : "▸"}`;
      header.addEventListener("click", (event) => {
        event.stopPropagation();
        group.expanded = !group.expanded;
        this.tickerDropdown(this.els.tickerInput.value, onSelect);
      });
      dropdown.appendChild(header);

      if (!expanded) continue;

      for (const item of matches) {
        const row = document.createElement("div");
        row.className = "combobox-item";
        const tickerSpan = document.createElement("span");
        tickerSpan.className = "item-ticker";
        tickerSpan.textContent = item.ticker;
        const nameSpan = document.createElement("span");
        nameSpan.className = "item-name";
        nameSpan.textContent = item.name;
        row.appendChild(tickerSpan);
        row.appendChild(nameSpan);
        row.addEventListener("click", (event) => {
          event.stopPropagation();
          onSelect(item.ticker);
        });
        dropdown.appendChild(row);
      }
    }

    if (q && !anyMatch) {
      const empty = document.createElement("div");
      empty.className = "combobox-empty";
      empty.textContent = `No matches — press "View chart" to look up "${query}" anyway.`;
      dropdown.appendChild(empty);
    }

    dropdown.hidden = false;
  },

  hideTickerDropdown() {
    this.els.tickerDropdown.hidden = true;
  },

  showEmptyPanel() {
    this.els.detailPanel.hidden = true;
    this.els.emptyPanel.hidden = false;
  },

  tradeStatus(message, isError) {
    this.els.tradeStatus.textContent = message;
    this.els.tradeStatus.classList.toggle("status-error", Boolean(isError));
    this.els.tradeStatus.classList.toggle("status-success", !isError && Boolean(message));
  },

  watchlistStatus(message, isError) {
    this.els.watchlistStatus.textContent = message;
    this.els.watchlistStatus.classList.toggle("status-error", Boolean(isError));
    this.els.watchlistStatus.classList.toggle("status-success", !isError && Boolean(message));
  },

  createPortfolioStatus(message, isError) {
    this.els.createPortfolioStatus.textContent = message;
    this.els.createPortfolioStatus.classList.toggle("status-error", Boolean(isError));
  },

  trendsStatus(message) {
    this.els.trendsStatus.textContent = message;
    this.els.trendsStatus.hidden = !message;
  },

  trendsTable(rows) {
    this.els.trendsBody.textContent = "";
    for (const row of rows) {
      const tr = document.createElement("tr");
      const cells = [row.ticker, formatMoney(row.close), formatMoney(row.ma_7d), formatMoney(row.ma_30d)];
      for (const value of cells) {
        const td = document.createElement("td");
        td.textContent = value;
        tr.appendChild(td);
      }
      const trendTd = document.createElement("td");
      const badge = document.createElement("span");
      badge.className = `trend-badge ${row.trend}`;
      const dot = document.createElement("span");
      dot.className = "dot";
      badge.appendChild(dot);
      badge.appendChild(document.createTextNode(row.trend === "up" ? "Up" : "Down"));
      trendTd.appendChild(badge);
      tr.appendChild(trendTd);
      this.els.trendsBody.appendChild(tr);
    }
    this.els.trendsTable.hidden = rows.length === 0;
  },

  watchlist(items, onDelete) {
    this.els.watchlistBody.textContent = "";
    for (const item of items) {
      const tr = document.createElement("tr");

      const tickerTd = document.createElement("td");
      tickerTd.textContent = item.ticker;
      tr.appendChild(tickerTd);

      const priceTd = document.createElement("td");
      priceTd.textContent = item.current_price != null ? formatMoney(item.current_price) : "—";
      tr.appendChild(priceTd);

      const alertTd = document.createElement("td");
      alertTd.textContent = item.alert_direction
        ? `${item.alert_direction === "above" ? "Above" : "Below"} ${formatMoney(item.target_price)}`
        : "—";
      tr.appendChild(alertTd);

      const statusTd = document.createElement("td");
      if (item.triggered_at) {
        const badge = document.createElement("span");
        badge.className = "trend-badge down";
        badge.textContent = "🔔 Triggered";
        statusTd.appendChild(badge);
      } else {
        statusTd.textContent = "—";
      }
      tr.appendChild(statusTd);

      const actionTd = document.createElement("td");
      const removeBtn = document.createElement("button");
      removeBtn.type = "button";
      removeBtn.className = "portfolio-list-delete";
      removeBtn.textContent = "Remove";
      removeBtn.addEventListener("click", () => onDelete(item.id));
      actionTd.appendChild(removeBtn);
      tr.appendChild(actionTd);

      this.els.watchlistBody.appendChild(tr);
    }
    this.els.watchlistTable.hidden = items.length === 0;
    this.els.watchlistEmpty.hidden = items.length > 0;
  },

  trendsChart(rows) {
    const ns = "http://www.w3.org/2000/svg";
    const svg = this.els.trendsChart;
    while (svg.firstChild) svg.removeChild(svg.firstChild);

    if (rows.length === 0) {
      svg.hidden = true;
      return;
    }
    svg.hidden = false;

    const width = 600;
    const height = 180;
    const margin = { top: 20, right: 12, bottom: 34, left: 12 };
    const plotWidth = width - margin.left - margin.right;
    const plotHeight = height - margin.top - margin.bottom;

    const groupWidth = plotWidth / rows.length;
    const barWidth = Math.min(28, groupWidth / 3);

    rows.forEach((row, i) => {
      // Each ticker is scaled against its own max (close vs 30D MA) — prices span wildly
      // different scales (e.g. BTC-USD vs AAPL), so a shared axis would flatten the smaller
      // ones. This shows "close relative to its own 30-day trend" per ticker instead.
      const localMax = Math.max(row.close, row.ma_30d) || 1;
      const closeHeight = (row.close / localMax) * plotHeight;
      const maHeight = (row.ma_30d / localMax) * plotHeight;
      const color = row.trend === "up" ? "#1f7a5c" : "#a93a2e";
      const groupCenter = margin.left + groupWidth * i + groupWidth / 2;

      const closeBar = document.createElementNS(ns, "rect");
      closeBar.setAttribute("x", (groupCenter - barWidth - 2).toFixed(1));
      closeBar.setAttribute("y", (margin.top + plotHeight - closeHeight).toFixed(1));
      closeBar.setAttribute("width", barWidth);
      closeBar.setAttribute("height", closeHeight.toFixed(1));
      closeBar.setAttribute("fill", color);
      closeBar.setAttribute("rx", "3");
      svg.appendChild(closeBar);

      const maBar = document.createElementNS(ns, "rect");
      maBar.setAttribute("x", (groupCenter + 2).toFixed(1));
      maBar.setAttribute("y", (margin.top + plotHeight - maHeight).toFixed(1));
      maBar.setAttribute("width", barWidth);
      maBar.setAttribute("height", maHeight.toFixed(1));
      maBar.setAttribute("fill", color);
      maBar.setAttribute("fill-opacity", "0.4");
      maBar.setAttribute("rx", "3");
      svg.appendChild(maBar);

      const label = document.createElementNS(ns, "text");
      label.setAttribute("class", "chart-axis-label");
      label.setAttribute("x", groupCenter.toFixed(1));
      label.setAttribute("y", height - 16);
      label.setAttribute("text-anchor", "middle");
      label.textContent = row.ticker;
      svg.appendChild(label);
    });

    const legend = document.createElementNS(ns, "text");
    legend.setAttribute("class", "chart-axis-label");
    legend.setAttribute("x", margin.left);
    legend.setAttribute("y", 12);
    legend.textContent = "Solid = close · Faded = 30D MA (each ticker scaled to itself)";
    svg.appendChild(legend);
  },

  alertsList(alerts, onDismiss) {
    this.els.alertsList.textContent = "";
    const unread = alerts.filter((a) => !a.is_read);
    // Keep it out of the flex layout entirely when empty — otherwise .detail-panel's gap
    // still reserves space around an invisible, childless div.
    this.els.alertsList.hidden = unread.length === 0;
    for (const alert of unread) {
      const banner = document.createElement("div");
      banner.className = "alert-banner";

      const message = document.createElement("span");
      message.className = "alert-message";
      message.textContent = alert.message;

      const time = document.createElement("span");
      time.className = "alert-time";
      time.textContent = parseHistoryDate(alert.created_at.slice(0, 10)).toLocaleDateString(undefined, {
        month: "short",
        day: "numeric",
      });

      const dismiss = document.createElement("button");
      dismiss.className = "alert-dismiss";
      dismiss.type = "button";
      dismiss.textContent = "✕";
      dismiss.addEventListener("click", () => onDismiss(alert.id));

      banner.appendChild(message);
      banner.appendChild(time);
      banner.appendChild(dismiss);
      this.els.alertsList.appendChild(banner);
    }
  },
};
