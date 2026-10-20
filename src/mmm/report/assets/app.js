/* ABADE · Relatório de mídia — comportamento.
 *
 * A página está completa sem este arquivo: todo número e título está no HTML e
 * todo gráfico tem tabela-gêmea. Este script acrescenta:
 *   - os gráficos, desenhados do JSON embutido pelo page.py, nas cores do tema
 *     ativo; o plotly.js só é baixado quando o primeiro gráfico se aproxima da
 *     tela, e se não carregar as tabelas-gêmeas abrem no lugar;
 *   - o mapa por estado (SVG puro, sem biblioteca), o seletor de tema e o
 *     destaque da seção atual na navegação.
 * Infraestrutura adaptada do dashboard de unit-economics-olist.
 */
(function () {
  "use strict";

  const DATA = JSON.parse(document.getElementById("dashboard-data").textContent);
  const GEO = JSON.parse(document.getElementById("geo-data").textContent);
  const root = document.documentElement;
  const mobile = () => window.matchMedia("(max-width: 720px)").matches;

  /* ------------------------------------------------------------ formatação (pt-BR) */
  const NBSP = " ", MINUS = "−";
  const nf0 = new Intl.NumberFormat("pt-BR", { maximumFractionDigits: 0 });
  const nf1 = new Intl.NumberFormat("pt-BR", { minimumFractionDigits: 1, maximumFractionDigits: 1 });
  const nf2 = new Intl.NumberFormat("pt-BR", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  const sign = (v) => (v < 0 ? MINUS : "");
  const brl = (v) => (v == null ? "—" : sign(v) + "R$" + NBSP + nf0.format(Math.abs(v)));
  const brlShort = (v) => {
    if (v == null) return "—";
    const a = Math.abs(v);
    if (a >= 1e6) return sign(v) + "R$" + NBSP + nf2.format(a / 1e6) + NBSP + "mi";
    if (a >= 1e4) return sign(v) + "R$" + NBSP + nf0.format(a / 1e3) + NBSP + "mil";
    if (a >= 1e3) return sign(v) + "R$" + NBSP + nf1.format(a / 1e3) + NBSP + "mil";
    return brl(v);
  };
  const perReal = (v) => "R$" + NBSP + nf2.format(v);
  const pct = (v, signed) => {
    if (v == null || isNaN(v)) return "—";
    const r = Math.round(v * 1000) / 10;
    if (r === 0) return "0%";
    return (r < 0 ? MINUS : signed ? "+" : "") + nf1.format(Math.abs(r)).replace(",0", "") + "%";
  };
  const esc = (s) => String(s).replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
  const label = (c) => DATA.labels[c] || c;
  const MONTHS = ["jan", "fev", "mar", "abr", "mai", "jun", "jul", "ago", "set", "out", "nov", "dez"];
  const MONTHS_LONG = ["janeiro", "fevereiro", "março", "abril", "maio", "junho", "julho", "agosto", "setembro",
    "outubro", "novembro", "dezembro"];

  /* ------------------------------------------------------------ tokens do tema */
  const css = (name) => getComputedStyle(root).getPropertyValue(name).trim();
  // Meta e TikTok são os protagonistas; todo o resto fica cinza.
  const color = (c) => (c === "meta" ? css("--c-meta") : c === "tiktok" ? css("--c-tiktok") : css("--c-other"));
  const tokens = () => ({
    ink: css("--ink"), ink2: css("--ink-2"), ink3: css("--ink-3"), grid: css("--grid"), axis: css("--axis"),
    surface: css("--surface"), accent: css("--accent"), meta: css("--c-meta"), tiktok: css("--c-tiktok"),
    other: css("--c-other"), otherSoft: css("--c-other-soft"), accentSoft: css("--accent-soft"),
  });
  function axis(t, extra) {
    return Object.assign({ gridcolor: t.grid, gridwidth: 1, zeroline: false, linecolor: t.axis, tickcolor: t.axis,
      tickfont: { color: t.ink2 }, title: { font: { color: t.ink2, size: 12 } }, automargin: true, fixedrange: true }, extra || {});
  }
  function baseLayout(t, extra) {
    const m = mobile();
    return Object.assign({
      margin: { l: 8, r: m ? 8 : 16, t: 8, b: 8 }, paper_bgcolor: "rgba(0,0,0,0)", plot_bgcolor: "rgba(0,0,0,0)",
      font: { family: "Lato, Helvetica Neue, Arial, sans-serif", color: t.ink2, size: m ? 12 : 13 }, separators: ",.",
      hoverlabel: { font: { family: "Lato, sans-serif", size: 13, color: t.ink }, bgcolor: t.surface, bordercolor: t.axis },
      showlegend: false, xaxis: axis(t), yaxis: axis(t), dragmode: false,
    }, extra || {});
  }
  // Ticks em R$ legíveis ("R$ 20 mil", não "R$ 20k"), com passo redondo.
  function brlTicks(values, fromZero) {
    const v = values.filter((x) => x != null && isFinite(x));
    let lo = fromZero ? Math.min(0, ...v) : Math.min(...v), hi = Math.max(...v);
    if (hi === lo) hi = lo + 1;
    const raw = (hi - lo) / 5, mag = Math.pow(10, Math.floor(Math.log10(raw)));
    const step = [1, 2, 2.5, 5, 10].map((m) => m * mag).find((s) => s >= raw);
    lo = Math.floor(lo / step) * step; hi = Math.ceil(hi / step) * step;
    const vals = [];
    for (let x = lo; x <= hi + step / 2; x += step) vals.push(Math.round(x * 100) / 100);
    const txt = (x) => (x === 0 ? "R$" + NBSP + "0" : brlShort(x));
    return { tickvals: vals, ticktext: vals.map(txt), range: [lo, hi] };
  }
  const brlAxis = (t, extra, values, fromZero) => axis(t, Object.assign(values ? brlTicks(values, fromZero !== false) : { tickprefix: "R$" + NBSP, tickformat: "~s" }, extra || {}));
  // Afasta rótulos de ponta que caem um em cima do outro (mesma coluna x).
  function spread(anns, minGap) {
    const groups = {};
    anns.forEach((a) => { (groups[a.x + "|" + a.xanchor] = groups[a.x + "|" + a.xanchor] || []).push(a); });
    Object.values(groups).forEach((g) => {
      g.sort((a, b) => a.y - b.y);
      for (let i = 1; i < g.length; i++) if (g[i].y - g[i - 1].y < minGap) g[i].y = g[i - 1].y + minGap;
    });
    return anns;
  }
  const dateAxis = (t) => axis(t, { type: "date", tickformat: "%b\n%Y", showgrid: false });
  const endLabel = (x, y, text, c, extra) => Object.assign({ x, y, text, showarrow: false, xanchor: "left", xshift: 8,
    font: { color: c, size: 13 } }, extra || {});
  const config = { responsive: true, displayModeBar: false, scrollZoom: false, locale: "pt-BR" };

  /* ------------------------------------------------------------ gráficos */
  const CHARTS = {
    problem(t) {
      const s = DATA.spend, n = s.week.length - 1;
      return {
        data: [
          { type: "scatter", mode: "lines", x: s.week, y: s.tiktok, line: { color: t.tiktok, width: 2.2 },
            hovertemplate: "Semana de %{x|%d/%m/%Y}<br>TikTok: R$ %{y:,.0f}<extra></extra>" },
          { type: "scatter", mode: "lines", x: s.week, y: s.meta, line: { color: t.meta, width: 2.8 },
            hovertemplate: "Semana de %{x|%d/%m/%Y}<br>Meta: R$ %{y:,.0f}<extra></extra>" },
        ],
        layout: baseLayout(t, { margin: { l: 8, r: 70, t: 8, b: 8 }, xaxis: dateAxis(t), yaxis: brlAxis(t, {}, s.meta.concat(s.tiktok)),
          annotations: [endLabel(s.week[n], s.meta[n], "<b>Meta</b>", t.meta), endLabel(s.week[n], s.tiktok[n], "<b>TikTok</b>", t.tiktok)] }),
      };
    },

    geolift(t) {
      const s = DATA.geolift.series, x = s.week, n = x.length - 1, first = s.post.indexOf(true);
      const shapes = first >= 0 ? [{ type: "rect", xref: "x", yref: "paper", x0: x[first], x1: x[n], y0: 0, y1: 1,
        fillcolor: t.otherSoft, opacity: 0.55, line: { width: 0 }, layer: "below" }] : [];
      const ann = [endLabel(x[n], s.observed[n], "<b>Real</b>", t.meta), endLabel(x[n], s.synthetic[n], "Sem o teste", t.ink2)];
      if (first >= 0) ann.push({ x: x[first], y: 1, yref: "paper", text: "Meta desligada", showarrow: false, xanchor: "left",
        yanchor: "top", xshift: 4, font: { color: t.ink2, size: 12 } });
      return {
        data: [
          { type: "scatter", mode: "lines", x, y: s.synthetic_high, line: { width: 0 }, hoverinfo: "skip" },
          { type: "scatter", mode: "lines", x, y: s.synthetic_low, line: { width: 0 }, fill: "tonexty", fillcolor: t.otherSoft, hoverinfo: "skip" },
          { type: "scatter", mode: "lines", x, y: s.synthetic, line: { color: t.ink3, width: 2, dash: "dot" },
            hovertemplate: "Semana de %{x|%d/%m}<br>Sem o teste: R$ %{y:,.0f}<extra></extra>" },
          { type: "scatter", mode: "lines", x, y: s.observed, line: { color: t.meta, width: 2.8 },
            hovertemplate: "Semana de %{x|%d/%m}<br>Real: R$ %{y:,.0f}<extra></extra>" },
        ],
        layout: baseLayout(t, { margin: { l: 8, r: 92, t: 8, b: 8 }, xaxis: dateAxis(t),
          yaxis: brlAxis(t, {}, s.observed.concat(s.synthetic_low, s.synthetic_high), false),
          shapes, annotations: spread(ann, (Math.max(...s.synthetic_high) - Math.min(...s.observed)) * 0.06) }),
      };
    },

    calib(t) {
      const u = byChannel(DATA.roi.uncalibrated), c = byChannel(DATA.roi.calibrated || []), tr = byChannel(DATA.roi_vs_truth || []);
      const chs = Object.keys(u);
      const hasC = Object.keys(c).length > 0, hasT = Object.keys(tr).length > 0;
      const cols = [0].concat(hasC ? [1] : [], hasT ? [hasC ? 2 : 1] : []);
      const names = ["Só histórico"].concat(hasC ? ["Com o teste"] : [], hasT ? ["Verdade (simulador)"] : []);
      const data = [], ann = [];
      const last = cols[cols.length - 1];
      chs.forEach((ch) => {
        const ys = [u[ch].roi_mean].concat(hasC && c[ch] ? [c[ch].roi_mean] : [], hasT && tr[ch] ? [tr[ch].roi_true] : []);
        const xs = cols.slice(0, ys.length), col = color(ch), on = ch === "meta" || ch === "tiktok";
        data.push({ type: "scatter", mode: "lines+markers", x: xs.slice(0, hasC ? 2 : 1), y: ys.slice(0, hasC ? 2 : 1),
          line: { color: col, width: on ? 3 : 1.6 }, marker: { color: col, size: on ? 9 : 6 },
          hovertemplate: esc(label(ch)) + ": R$ %{y:.2f} por real<extra></extra>" });
        if (hasT && tr[ch]) data.push({ type: "scatter", mode: "lines+markers", x: [xs[xs.length - 2], last], y: [ys[ys.length - 2], ys[ys.length - 1]],
          line: { color: col, width: 1, dash: "dot" }, marker: { color: [col, col], size: [0, on ? 9 : 6], symbol: "diamond" },
          hovertemplate: esc(label(ch)) + " · verdade: R$ %{y:.2f}<extra></extra>" });
        ann.push({ x: 0, y: ys[0], text: (on ? "<b>" : "") + esc(label(ch)) + " " + nf2.format(ys[0]) + (on ? "</b>" : ""), showarrow: false,
          xanchor: "right", xshift: -12, font: { color: on ? col : t.ink2, size: 12 } });
        ann.push({ x: xs[xs.length - 1], y: ys[ys.length - 1], text: (on ? "<b>" : "") + nf2.format(ys[ys.length - 1]) + " " + esc(label(ch)) + (on ? "</b>" : ""),
          showarrow: false, xanchor: "left", xshift: 12, font: { color: on ? col : t.ink2, size: 12 } });
      });
      const m = mobile();
      const ys = ann.map((a) => a.y), gap = (Math.max(...ys) - Math.min(0, ...ys)) * 0.045;
      spread(ann, gap);
      return { data, layout: baseLayout(t, { margin: { l: m ? 120 : 175, r: m ? 120 : 175, t: 34, b: 8 },
        xaxis: axis(t, { range: [-0.08, last + 0.08], tickvals: cols, ticktext: names.map((n) => "<b>" + n + "</b>"), side: "top",
          showgrid: false, showline: false, tickfont: { color: t.ink, size: 13 } }),
        yaxis: axis(t, { visible: false, rangemode: "tozero" }), annotations: ann,
        shapes: [{ type: "line", xref: "paper", x0: 0, x1: 1, y0: 1, y1: 1, line: { color: t.axis, width: 1, dash: "dot" } }] }) };
    },

    alloc(t) {
      const a = mainAllocation();
      const rows = a.channels.map((r) => Object.assign({}, r, { delta: r.recommended_total - r.current_daily_at_budget * a.horizon_days }))
        .sort((x, y) => x.delta - y.delta);
      const m = Math.max(...rows.map((r) => Math.abs(r.delta))) || 1;
      return {
        data: [{ type: "bar", orientation: "h", y: rows.map((r) => label(r.channel)), x: rows.map((r) => r.delta),
          marker: { color: rows.map((r) => (r.delta > 0 ? t.accent : t.other)), cornerradius: 3 },
          text: rows.map((r) => (r.delta > 0 ? "+" : MINUS) + brlShort(Math.abs(r.delta)).replace(MINUS, "") + " (" + pct(r.change_pct, true) + ")" +
            (r.at_upper_bound ? " · teto" : r.at_lower_bound ? " · piso" : "")),
          textposition: "outside", textfont: { color: t.ink, size: 13 }, cliponaxis: false,
          hovertemplate: "%{y}: %{text}<extra></extra>" }],
        layout: baseLayout(t, { bargap: 0.4, margin: { l: 8, r: 8, t: 8, b: 8 },
          xaxis: axis(t, { visible: false, range: [-m * 1.9, m * 1.9] }),
          yaxis: axis(t, { showgrid: false, showline: false, tickfont: { color: t.ink, size: 14 } }),
          shapes: [{ type: "line", x0: 0, x1: 0, yref: "paper", y0: 0, y1: 1, line: { color: t.axis, width: 1 } }] }),
      };
    },

    gain(t) {
      const k = DATA.allocation.calibrated ? "calibrated" : "uncalibrated", d = DATA.gain_draws[k];
      const lo = Math.min(...d), hi = Math.max(...d), nb = 28, w = (hi - lo) / nb || 1;
      const mid = Array.from({ length: nb }, (_, i) => lo + (i + 0.5) * w), cnt = new Array(nb).fill(0);
      d.forEach((v) => { cnt[Math.min(nb - 1, Math.floor((v - lo) / w))] += 1; });
      return {
        data: [{ type: "bar", x: mid, y: cnt, width: w * 0.92, marker: { color: mid.map((b) => (b > 0 ? t.accent : t.other)) },
          hovertemplate: "Ganho ≈ R$ %{x:,.0f}<br>%{y} cenários<extra></extra>" }],
        layout: baseLayout(t, { bargap: 0, xaxis: brlAxis(t, { showgrid: false }, [lo, hi], false), yaxis: axis(t, { visible: false }),
          shapes: [{ type: "line", x0: 0, x1: 0, yref: "paper", y0: 0, y1: 1, line: { color: t.ink3, width: 1, dash: "dot" } }],
          annotations: [{ x: 0, y: 1, yref: "paper", text: "empata com a divisão atual", showarrow: false, xanchor: "right", xshift: -6,
            font: { color: t.ink2, size: 12 } }] }),
      };
    },

    power(t) {
      const run = Math.round(DATA.geolift.test_days / 7);
      const ex = DATA.geolift.power.filter((r) => r.design === "executado");
      const weeks = Array.from(new Set(ex.map((r) => r.test_weeks))).sort((a, b) => a - b);
      const data = [], ann = [];
      weeks.forEach((wk) => {
        const r = ex.filter((x) => x.test_weeks === wk).sort((a, b) => a.effect - b.effect), on = wk === run;
        data.push({ type: "scatter", mode: "lines+markers", x: r.map((v) => v.effect), y: r.map((v) => v.power),
          line: { color: on ? t.accent : t.other, width: on ? 3 : 1.5 }, marker: { size: on ? 7 : 5, color: on ? t.accent : t.other },
          hovertemplate: wk + " semanas · queda de %{x:.0%}: poder %{y:.0%}<extra></extra>" });
        const l = r[r.length - 1];
        ann.push(endLabel(l.effect, l.power, (on ? "<b>" : "") + wk + " semanas" + (on ? " (executado)</b>" : ""), on ? t.accent : t.ink2));
      });
      return { data, layout: baseLayout(t, { margin: { l: 8, r: 150, t: 8, b: 8 },
        xaxis: axis(t, { tickformat: ".0%", showgrid: false, title: { text: "Queda real de receita nos estados testados" } }),
        yaxis: axis(t, { tickformat: ".0%", range: [0, 1.05] }), annotations: ann,
        shapes: [{ type: "line", xref: "paper", x0: 0, x1: 1, y0: 0.8, y1: 0.8, line: { color: t.ink3, width: 1, dash: "dot" } }] }) };
    },

    curve(t, el) {
      const k = DATA.curves[mainKind()][el.dataset.channel], ch = el.dataset.channel;
      const j = k.spend.reduce((b, s, i) => (Math.abs(s - k.current) < Math.abs(k.spend[b] - k.current) ? i : b), 0);
      const col = ch === "meta" || ch === "tiktok" ? color(ch) : t.ink2;
      return {
        data: [
          { type: "scatter", mode: "lines", x: k.spend, y: k.high, line: { width: 0 }, hoverinfo: "skip" },
          { type: "scatter", mode: "lines", x: k.spend, y: k.low, line: { width: 0 }, fill: "tonexty", fillcolor: t.otherSoft, hoverinfo: "skip" },
          { type: "scatter", mode: "lines", x: k.spend, y: k.mean, line: { color: col, width: 2.2 },
            hovertemplate: "R$ %{x:,.0f}/dia → R$ %{y:,.0f}/dia<extra></extra>" },
          { type: "scatter", mode: "markers", x: [k.spend[j]], y: [k.mean[j]], marker: { color: t.ink, size: 9, line: { color: t.surface, width: 2 } },
            hovertemplate: "Hoje: R$ %{x:,.0f}/dia<extra></extra>" },
        ],
        layout: baseLayout(t, { xaxis: brlAxis(t, { showgrid: false }, k.spend), yaxis: brlAxis(t, {}, k.high) }),
      };
    },
  };
  function byChannel(rows) { const o = {}; (rows || []).forEach((r) => { o[r.channel] = r; }); return o; }
  function mainKind() { return DATA.allocation && DATA.allocation.calibrated ? "calibrated" : "uncalibrated"; }
  function mainAllocation() { return DATA.allocation[mainKind()]; }

  /* ------------------------------------------------------------ pequenos múltiplos */
  const multiples = document.getElementById("multiples");
  if (multiples && DATA.curves) {
    const order = JSON.parse(multiples.dataset.order || "[]");
    const cv = DATA.curves[mainKind()] || {};
    multiples.innerHTML = order.filter((c) => cv[c]).map((c) => {
      const k = cv[c];
      const j = k.spend.reduce((b, s, i) => (Math.abs(s - k.current) < Math.abs(k.spend[b] - k.current) ? i : b), 0);
      const cls = c === "meta" ? "name-meta" : c === "tiktok" ? "name-tiktok" : "";
      return '<figure class="card"><figcaption><h3 class="' + cls + '">' + esc(label(c)) + '</h3><p class="stat-note">próximo real rende <strong>' +
        perReal(k.marginal[j]) + "</strong> · hoje " + brl(k.current) + "/dia</p></figcaption>" +
        '<div class="chart" data-chart="curve" data-channel="' + esc(c) + '" role="img" aria-label="Curva de resposta de ' + esc(label(c)) + '"></div></figure>';
    }).join("");
  }

  /* ------------------------------------------------------------ plotly sob demanda */
  const SCRIPT = document.querySelector("script[data-plotly]");
  let plotlyState = window.Plotly ? "ready" : "idle";
  const waiting = [];
  function withPlotly(fn) {
    if (plotlyState === "ready") return fn();
    if (plotlyState === "failed") return;
    waiting.push(fn);
    if (plotlyState === "loading") return;
    plotlyState = "loading";
    const tag = document.createElement("script");
    tag.src = SCRIPT.dataset.plotly;
    tag.async = true;
    tag.onload = () => { plotlyState = "ready"; registerLocale(); waiting.splice(0).forEach((f) => f()); };
    tag.onerror = fail;
    document.head.appendChild(tag);
  }
  function fail() {
    plotlyState = "failed";
    document.querySelectorAll(".chart").forEach((c) => { c.hidden = true; });
    document.querySelectorAll("details.data-twin").forEach((d) => { d.open = true; });
  }
  function registerLocale() {
    if (registerLocale.done) return;
    Plotly.register({ moduleType: "locale", name: "pt-BR", dictionary: {},
      format: { days: ["domingo", "segunda", "terça", "quarta", "quinta", "sexta", "sábado"],
        shortDays: ["dom", "seg", "ter", "qua", "qui", "sex", "sáb"], months: MONTHS_LONG, shortMonths: MONTHS,
        date: "%d/%m/%Y", decimal: ",", thousands: "." } });
    registerLocale.done = true;
  }

  const rendered = new Set();
  function draw(el) {
    withPlotly(() => {
      const build = CHARTS[el.dataset.chart];
      if (!build) return;
      let spec;
      try { spec = build(tokens(), el); } catch (e) { el.hidden = true; return; }
      if (rendered.has(el)) { Plotly.react(el, spec.data, spec.layout, config); }
      else { el.textContent = ""; Plotly.newPlot(el, spec.data, spec.layout, config); rendered.add(el); }
    });
  }
  const charts = Array.from(document.querySelectorAll("[data-chart]"));
  if ("IntersectionObserver" in window) {
    const io = new IntersectionObserver((entries) => {
      entries.forEach((e) => { if (e.isIntersecting) { draw(e.target); io.unobserve(e.target); } });
    }, { rootMargin: "400px 0px" });
    charts.forEach((el) => io.observe(el));
  } else { charts.forEach(draw); }
  const redrawAll = () => { rendered.forEach((el) => draw(el)); drawMap(); };
  let resizeTimer, lastMobile = mobile();
  window.addEventListener("resize", () => {
    clearTimeout(resizeTimer);
    resizeTimer = setTimeout(() => { if (mobile() !== lastMobile) { lastMobile = mobile(); redrawAll(); } }, 200);
  });
  window.addEventListener("beforeprint", () => charts.forEach((el) => { if (!rendered.has(el)) draw(el); }));

  /* ------------------------------------------------------------ mapa por estado (SVG) */
  let layer = "grupo";
  const mix = (c1, c2, f) => {
    const h = (c) => [1, 3, 5].map((i) => parseInt(c.slice(i, i + 2), 16));
    const a = h(c1), b = h(c2); f = Math.max(0, Math.min(1, f));
    return "#" + a.map((v, i) => Math.round(v + (b[i] - v) * f).toString(16).padStart(2, "0")).join("");
  };
  function drawMap() {
    const el = document.getElementById("map");
    const rows = DATA.regional || [];
    if (!el || !rows.length) return;
    const t = tokens(), by = {};
    rows.forEach((r) => { by[r.uf] = r; });
    const k = Math.cos((-15 * Math.PI) / 180);
    const P = (pt) => [(pt[0] + 74.5) * k * 10, (6 - pt[1]) * 10];
    const W = (74.5 - 34) * k * 10, H = 405;
    let fill, tip, legend, note;
    if (layer === "grupo") {
      fill = (r) => (r && r.grupo === "tratamento" ? t.meta : t.otherSoft);
      tip = (r, n) => n + ": " + (r && r.grupo === "tratamento" ? "Meta desligada durante o teste" : "seguiu o plano (controle)");
      legend = '<span><span class="key" style="--sw:' + t.meta + '"></span>Meta desligada</span><span><span class="key" style="--sw:' + t.otherSoft + '"></span>Controle</span>';
      note = "SP, RJ e MG ficaram no controle: desligar a Meta nelas custaria caro demais.";
    } else if (layer === "variacao_teste") {
      fill = (r) => (r && r.variacao_teste != null ? (r.variacao_teste < 0 ? mix(t.otherSoft, t.meta, -r.variacao_teste / 0.2) : mix(t.otherSoft, t.other, r.variacao_teste / 0.2)) : t.otherSoft);
      tip = (r, n) => n + ": " + (r ? pct(r.variacao_teste, true) : "—") + " na receita, descontada a tendência dos estados de controle";
      legend = '<span>receita caiu<span class="ramp" style="background:linear-gradient(90deg,' + t.meta + "," + t.otherSoft + "," + t.other + ')"></span>subiu (até ±20%)</span>';
      note = "Estados pequenos oscilam muito por acaso; o efeito confiável é o agregado do gráfico ao lado.";
    } else {
      const mx = Math.max(...rows.map((r) => r.receita_12m || 0)) || 1;
      fill = (r) => mix(t.otherSoft, t.ink2, Math.sqrt((r ? r.receita_12m : 0) / mx));
      tip = (r, n) => n + ": " + brlShort(r ? r.receita_12m : 0) + " de receita nos últimos 12 meses";
      legend = '<span>menos<span class="ramp" style="background:linear-gradient(90deg,' + t.otherSoft + "," + t.ink2 + ')"></span>mais receita (máx. ' + brlShort(mx) + ")</span>";
      note = "Receita paga por estado de entrega nos últimos 12 meses.";
    }
    const paths = GEO.features.map((f) => {
      const d = f.geometry.coordinates.map((poly) => poly.map((ring) => "M" + ring.map((pt) => P(pt).map((v) => v.toFixed(1)).join(",")).join("L") + "Z").join("")).join("");
      const text = tip(by[f.id], f.properties.nome);
      return '<path tabindex="0" d="' + d + '" fill="' + fill(by[f.id]) + '" data-tip="' + esc(text) + '"><title>' + esc(text) + "</title></path>";
    }).join("");
    const labels = GEO.features.map((f) => {
      const ring = f.geometry.coordinates.reduce((b, poly) => (poly[0].length > b.length ? poly[0] : b), []);
      let sx = 0, sy = 0; ring.forEach((pt) => { const p = P(pt); sx += p[0]; sy += p[1]; });
      return '<text x="' + (sx / ring.length).toFixed(1) + '" y="' + (sy / ring.length).toFixed(1) + '" text-anchor="middle">' + f.id + "</text>";
    }).join("");
    el.innerHTML = '<svg class="map-svg" viewBox="0 0 ' + W.toFixed(0) + " " + H + '" role="img" aria-label="Mapa do Brasil por estado">' + paths + labels + "</svg>" +
      '<p class="map-legend">' + legend + "</p>";
    document.getElementById("map-note").textContent = note;
    const tipEl = document.getElementById("map-tip");
    el.querySelectorAll("path").forEach((p) => {
      const show = () => { tipEl.textContent = p.dataset.tip; };
      p.addEventListener("mouseenter", show); p.addEventListener("focus", show); p.addEventListener("click", show);
    });
  }
  const layers = document.getElementById("map-layers");
  if (layers) layers.addEventListener("click", (e) => {
    const b = e.target.closest("button"); if (!b) return;
    layer = b.dataset.layer;
    layers.querySelectorAll("button").forEach((x) => x.setAttribute("aria-pressed", String(x === b)));
    drawMap();
  });
  drawMap();

  /* ------------------------------------------------------------ tema */
  const toggle = document.getElementById("theme-toggle");
  const systemDark = window.matchMedia("(prefers-color-scheme: dark)");
  const isDark = () => (root.dataset.theme ? root.dataset.theme === "dark" : systemDark.matches);
  function syncToggle() { toggle.hidden = false; toggle.setAttribute("aria-pressed", String(isDark())); }
  toggle.addEventListener("click", () => {
    root.dataset.theme = isDark() ? "light" : "dark";
    try { localStorage.setItem("mmm-theme", root.dataset.theme); } catch (e) {}
    syncToggle(); redrawAll();
  });
  systemDark.addEventListener("change", () => { if (!root.dataset.theme) { syncToggle(); redrawAll(); } });
  syncToggle();

  /* ------------------------------------------------------------ seção atual na navegação */
  const links = Array.from(document.querySelectorAll(".toc a"));
  const sections = links.map((a) => document.querySelector(a.getAttribute("href"))).filter(Boolean);
  if ("IntersectionObserver" in window && sections.length) {
    const seen = new IntersectionObserver((entries) => {
      entries.forEach((e) => {
        if (!e.isIntersecting) return;
        links.forEach((a) => { if (a.getAttribute("href") === "#" + e.target.id) a.setAttribute("aria-current", "true"); else a.removeAttribute("aria-current"); });
      });
    }, { rootMargin: "-45% 0px -50% 0px" });
    sections.forEach((s) => seen.observe(s));
  }
})();
