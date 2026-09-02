/* =========================================================================
   Ebola (Bundibugyo) Evidence Dashboard — application logic
   Pure vanilla JS, no build step. Reads data/evidence.json (or an injected
   window.__EVIDENCE__ for the standalone preview).
   ========================================================================= */
(function () {
  "use strict";

  // ---- config / labels --------------------------------------------------
  const INTERVENTIONS = [
    { key: "vaccine", label: "Vaccine", cls: "vaccine", varc: "--c-vaccine" },
    { key: "monoclonal", label: "Monoclonal antibody", cls: "monoclonal", varc: "--c-mab" },
    { key: "other_therapeutic", label: "Other therapeutic", cls: "other_therapeutic", varc: "--c-other" },
  ];
  const TYPES = [
    { key: "journal_article", label: "Journal article", varc: "--t-journal" },
    { key: "preprint", label: "Preprint", varc: "--t-preprint" },
    { key: "clinical_trial", label: "Clinical trial", varc: "--t-trial" },
    { key: "news", label: "News story", varc: "--t-news" },
    { key: "outbreak_report", label: "Outbreak report", varc: "--t-outbreak" },
    { key: "guideline", label: "Guideline / NITAG", varc: "--t-guideline" },
    { key: "press_release", label: "Press release", varc: "--t-press" },
  ];
  const SPECIES = [
    { key: "human", label: "Human / clinical" },
    { key: "animal", label: "Animal (vaccine)" },
    { key: "na", label: "Not applicable" },
  ];
  const TYPE_LABEL = Object.fromEntries(TYPES.map(t => [t.key, t.label]));
  const TYPE_VAR = Object.fromEntries(TYPES.map(t => [t.key, t.varc]));

  // ---- state ------------------------------------------------------------
  const state = {
    interventions: new Set(),
    types: new Set(),
    species: new Set(),
    dateDays: "all",
    bundibugyo: false,
    canadian: false,
    isnew: false,
    search: "",
    sort: "date-desc",
  };
  let DATA = [];
  let META = {};

  const $ = (s, r = document) => r.querySelector(s);
  const $$ = (s, r = document) => Array.from(r.querySelectorAll(s));
  const el = (tag, cls, html) => { const e = document.createElement(tag); if (cls) e.className = cls; if (html != null) e.innerHTML = html; return e; };
  const esc = s => String(s == null ? "" : s).replace(/[&<>"]/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
  const fmtDate = s => { const d = new Date(s + "T00:00:00"); return isNaN(d) ? s : d.toLocaleDateString("en-CA", { year: "numeric", month: "short", day: "numeric" }); };
  const daysAgo = n => { const d = new Date(); d.setDate(d.getDate() - n); return d.toISOString().slice(0, 10); };

  // ---- storage (guarded) ------------------------------------------------
  const store = {
    get(k) { try { return localStorage.getItem(k); } catch (e) { return null; } },
    set(k, v) { try { localStorage.setItem(k, v); } catch (e) {} },
  };

  // ---- theme ------------------------------------------------------------
  function initTheme() {
    const saved = store.get("eew-theme");
    if (saved) document.documentElement.setAttribute("data-theme", saved);
    $("#theme-toggle").addEventListener("click", () => {
      const cur = document.documentElement.getAttribute("data-theme");
      const isDark = cur === "dark" || (!cur && matchMedia("(prefers-color-scheme: dark)").matches);
      const next = isDark ? "light" : "dark";
      document.documentElement.setAttribute("data-theme", next);
      store.set("eew-theme", next);
    });
  }

  // ---- URL state (shareable filtered views) -----------------------------
  function readURL() {
    const p = new URLSearchParams(location.search);
    if (p.get("iv")) p.get("iv").split(",").forEach(v => state.interventions.add(v));
    if (p.get("type")) p.get("type").split(",").forEach(v => state.types.add(v));
    if (p.get("sp")) p.get("sp").split(",").forEach(v => state.species.add(v));
    if (p.get("date")) state.dateDays = p.get("date");
    if (p.get("q")) state.search = p.get("q");
    if (p.get("sort")) state.sort = p.get("sort");
    state.bundibugyo = p.get("bdbv") === "1";
    state.canadian = p.get("ca") === "1";
    state.isnew = p.get("new") === "1";
  }
  function writeURL() {
    const p = new URLSearchParams();
    if (state.interventions.size) p.set("iv", [...state.interventions].join(","));
    if (state.types.size) p.set("type", [...state.types].join(","));
    if (state.species.size) p.set("sp", [...state.species].join(","));
    if (state.dateDays !== "all") p.set("date", state.dateDays);
    if (state.search) p.set("q", state.search);
    if (state.sort !== "date-desc") p.set("sort", state.sort);
    if (state.bundibugyo) p.set("bdbv", "1");
    if (state.canadian) p.set("ca", "1");
    if (state.isnew) p.set("new", "1");
    const qs = p.toString();
    history.replaceState(null, "", qs ? "?" + qs : location.pathname);
  }

  // ---- matchers ---------------------------------------------------------
  function makeMatchers() {
    const cutoff = state.dateDays === "all" ? null : daysAgo(+state.dateDays);
    const q = state.search.trim().toLowerCase();
    const tokens = q ? q.split(/\s+/) : [];
    return {
      intervention: r => !state.interventions.size || r.intervention.some(i => state.interventions.has(i)),
      type: r => !state.types.size || state.types.has(r.source_type),
      species: r => !state.species.size || state.species.has(r.species),
      date: r => !cutoff || (r.published_date && r.published_date >= cutoff),
      bundibugyo: r => !state.bundibugyo || r.bundibugyo,
      canadian: r => !state.canadian || r.canadian,
      isnew: r => !state.isnew || r.is_new,
      search: r => {
        if (!tokens.length) return true;
        const hay = (r._hay || (r._hay = [r.title, r.summary, r.authors, r.journal, r.source, (r.keywords_matched || []).join(" "), (r.extra && r.extra.nct_id) || ""].join(" ").toLowerCase()));
        return tokens.every(t => hay.includes(t));
      },
    };
  }
  function filtered(exceptKey) {
    const m = makeMatchers();
    const keys = Object.keys(m).filter(k => k !== exceptKey);
    return DATA.filter(r => keys.every(k => m[k](r)));
  }

  // ---- rendering: KPIs --------------------------------------------------
  function renderKPIs() {
    const total = DATA.length;
    const isNew = DATA.filter(r => r.is_new).length;
    const bdbv = DATA.filter(r => r.bundibugyo).length;
    const canada = DATA.filter(r => r.canadian).length;
    const recruiting = DATA.filter(r => r.source_type === "clinical_trial" && /RECRUIT/i.test((r.extra && r.extra.status) || "")).length;
    const tiles = [
      { label: "Evidence items", value: total, sub: "across all sources", dot: "--brand" },
      { label: "New / unreviewed", value: isNew, sub: "in the last 3 weeks", cls: "accent-new", dot: "--new" },
      { label: "Bundibugyo-specific", value: bdbv, sub: "BDBV-focused evidence", cls: "accent-bdbv", dot: "--bdbv" },
      { label: "Canadian evidence", value: canada, sub: "Canada-linked items", cls: "accent-canada", dot: "--canada" },
      { label: "Recruiting trials", value: recruiting, sub: "actively enrolling", dot: "--c-other" },
    ];
    const host = $("#kpis"); host.innerHTML = "";
    tiles.forEach(t => {
      const k = el("div", "kpi" + (t.cls ? " " + t.cls : ""));
      k.innerHTML = `<div class="label"><span class="dot" style="background:var(${t.dot})"></span>${t.label}</div>
        <div class="value">${t.value}</div><div class="sub">${t.sub}</div>`;
      host.appendChild(k);
    });
  }

  // ---- rendering: situation banner --------------------------------------
  function renderSituation() {
    const reports = DATA.filter(r => r.source_type === "outbreak_report")
      .sort((a, b) => (b.published_date || "").localeCompare(a.published_date || ""));
    const slot = $("#situation-slot");
    if (!reports.length) { slot.innerHTML = ""; return; }
    const r = reports[0];
    slot.innerHTML = `<div class="situation">
      <span class="pulse" aria-hidden="true"></span>
      <div class="body">
        <span class="tag">Current situation</span>
        <h3><a href="${esc(r.url)}" target="_blank" rel="noopener">${esc(r.title)}</a></h3>
        <p>${esc(r.summary)}</p>
        <div class="meta">${esc(r.source)} · ${fmtDate(r.published_date)}</div>
      </div></div>`;
  }

  // ---- rendering: source coverage --------------------------------------
  function renderCoverage() {
    const slot = $("#coverage-slot");
    const cov = META.coverage;
    if (!cov || !cov.channels) { slot.innerHTML = ""; return; }
    const byChan = (META.counts && META.counts.by_channel) || {};
    const runCounts = cov.run_counts || {};
    const empties = cov.channels.filter(c => (byChan[c] || 0) === 0);
    const errs = cov.fetcher_errors || [];

    const rows = cov.channels.map(c => {
      const corpus = byChan[c] || 0;
      const run = runCounts[c] || 0;
      const cls = corpus === 0 ? "watch" : "ok";
      const runTxt = run > 0 ? `<span class="cov-run">+${run} this refresh</span>` : "";
      return `<div class="cov-item ${cls}">
        <span class="cov-dot"></span>
        <span class="cov-name">${esc(c)}</span>
        <span class="cov-nums">${corpus} item${corpus === 1 ? "" : "s"} ${runTxt}</span>
      </div>`;
    }).join("");

    const status = errs.length
      ? `<span class="cov-badge err">⚠ ${errs.length} fetch error${errs.length === 1 ? "" : "s"} last run</span>`
      : empties.length
        ? `<span class="cov-badge warn">${empties.length} channel${empties.length === 1 ? "" : "s"} with no items yet</span>`
        : `<span class="cov-badge ok">All ${cov.channels.length} channels active</span>`;

    slot.innerHTML = `<details class="coverage">
      <summary>
        <svg class="cov-ic" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M3 12h4l3 8 4-16 3 8h4"/></svg>
        <span class="cov-title">Source coverage</span>
        ${status}
        <span class="cov-hint">last refresh ${META.generated_at ? new Date(META.generated_at).toLocaleDateString("en-CA", { month: "short", day: "numeric", year: "numeric" }) : "—"}</span>
        <svg class="cov-chev" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="m6 9 6 6 6-6"/></svg>
      </summary>
      <div class="cov-grid">${rows}</div>
      ${errs.length ? `<div class="cov-errline">Fetch errors last run: ${errs.map(esc).join(", ")}. These sources kept their previously-collected items; the next run retries them.</div>` : ""}
      <div class="cov-foot">A channel showing <strong>0 items</strong> means nothing has been captured from it yet — the signal to check that source. Counts reflect the whole corpus; “this refresh” shows what the last pipeline run added.</div>
    </details>`;
  }

  // ---- rendering: filters ----------------------------------------------
  function checkSVG() { return '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"><path d="M20 6 9 17l-5-5"/></svg>'; }

  function renderFilters() {
    // intervention
    const ivCounts = countFacet("intervention", r => r.intervention);
    const ivHost = $("#f-intervention"); ivHost.innerHTML = "";
    INTERVENTIONS.forEach(o => ivHost.appendChild(choiceRow("intervention", o.key, o.label, ivCounts[o.key] || 0, o.varc)));
    // type
    const tyCounts = countFacet("type", r => [r.source_type]);
    const tyHost = $("#f-type"); tyHost.innerHTML = "";
    TYPES.forEach(o => { if ((tyCounts[o.key] || 0) > 0 || state.types.has(o.key)) tyHost.appendChild(choiceRow("type", o.key, o.label, tyCounts[o.key] || 0, o.varc)); });
    // species
    const spCounts = countFacet("species", r => [r.species]);
    const spHost = $("#f-species"); spHost.innerHTML = "";
    SPECIES.forEach(o => spHost.appendChild(choiceRow("species", o.key, o.label, spCounts[o.key] || 0, null)));
    // toggles + date + reset button visual
    $$(".toggle-row").forEach(t => t.classList.toggle("on", state[t.dataset.toggle]));
    $$("#f-date button").forEach(b => b.classList.toggle("on", b.dataset.days === state.dateDays));
    const anyActive = state.interventions.size || state.types.size || state.species.size || state.dateDays !== "all" || state.bundibugyo || state.canadian || state.isnew || state.search;
    $("#clear-filters").disabled = !anyActive;
    const fc = [state.interventions.size, state.types.size, state.species.size, state.bundibugyo, state.canadian, state.isnew, state.dateDays !== "all", !!state.search].reduce((a, b) => a + (b ? 1 : 0), 0);
    const mfc = $("#mobile-fcount"); if (mfc) { mfc.hidden = !fc; mfc.textContent = fc; }
  }
  function countFacet(setKey, getVals) {
    const base = filtered(setKey);
    const counts = {};
    base.forEach(r => getVals(r).forEach(v => { counts[v] = (counts[v] || 0) + 1; }));
    return counts;
  }
  function setFor(group) { return state[group === "intervention" ? "interventions" : group === "type" ? "types" : "species"]; }
  function choiceRow(group, key, label, count, varc) {
    const on = setFor(group).has(key);
    const row = el("label", "choice" + (on ? " on" : ""));
    const dot = varc ? `<span class="cdot" style="background:var(${varc})"></span>` : "";
    row.innerHTML = `<span class="box">${checkSVG()}</span>${dot}<span>${label}</span><span class="count">${count}</span>`;
    row.addEventListener("click", e => {
      e.preventDefault();
      const set = setFor(group);
      set.has(key) ? set.delete(key) : set.add(key);
      update();
    });
    return row;
  }

  // ---- rendering: timeline ---------------------------------------------
  function renderTimeline(rows) {
    const box = $("#timeline");
    const withDate = rows.filter(r => /^\d{4}/.test(r.published_date || ""));
    if (withDate.length < 3) { box.hidden = true; return; }
    box.hidden = false;
    const years = withDate.map(r => +r.published_date.slice(0, 4));
    const min = Math.min(...years), max = Math.max(...years);
    const span = max - min;
    // bucket by year if span<=12 else keep years
    const buckets = {};
    for (let y = min; y <= max; y++) buckets[y] = 0;
    withDate.forEach(r => buckets[+r.published_date.slice(0, 4)]++);
    const entries = Object.entries(buckets);
    const peak = Math.max(...entries.map(e => e[1]), 1);
    const chart = $("#tl-chart"); chart.innerHTML = "";
    entries.forEach(([y, c]) => {
      const bar = el("div", "tl-bar");
      bar.style.height = Math.max(2, (c / peak) * 100) + "%";
      bar.innerHTML = `<span class="tip">${y}: ${c} item${c === 1 ? "" : "s"}</span>`;
      if (c === 0) bar.style.opacity = ".25";
      chart.appendChild(bar);
    });
    const axis = $("#tl-axis"); axis.innerHTML = "";
    const labelYears = span > 8 ? [min, min + Math.round(span / 2), max] : entries.map(e => +e[0]);
    entries.forEach(([y]) => { const s = el("span"); s.textContent = (span <= 8 || labelYears.includes(+y)) ? y : ""; axis.appendChild(s); });
    $("#tl-note").textContent = `${withDate.length} dated items · ${min}–${max}`;
  }

  // ---- rendering: cards -------------------------------------------------
  function badge(cls, label, dotVar) {
    return `<span class="badge ${cls}">${dotVar ? `<span class="bdot" style="background:var(${dotVar})"></span>` : ""}${label}</span>`;
  }
  function altmetricEl(r) {
    if (!r.altmetric_score) return "";
    const p = Math.min(100, r.altmetric_score);
    return `<a class="altmetric" href="${esc(r.altmetric_url || r.url)}" target="_blank" rel="noopener" title="Altmetric attention score">
      <span class="donut" style="--p:${p}"><span>${Math.round(r.altmetric_score)}</span></span>
      <span class="amlabel"><b>Altmetric</b>attention</span></a>`;
  }
  function card(r) {
    const c = el("article", "card");
    c.id = "rec-" + r.id;
    const typeBadge = badge("type", esc(r.source_type_label), TYPE_VAR[r.source_type]);
    const ivBadges = (r.intervention || []).filter(i => i !== "unspecified")
      .map((i, idx) => badge("iv-" + i, esc(r.intervention_labels[idx] || i))).join("");
    let flags = "";
    if (r.bundibugyo) flags += badge("flag-bdbv", "Bundibugyo");
    if (r.canadian) flags += badge("flag-canada", "🇨🇦 Canada");
    if (r.species === "animal") flags += badge("flag-animal", "Animal study");
    if (r.is_new && !r.reviewed) flags += badge("flag-new", "New / unreviewed");
    let statusBadge = "";
    if (r.source_type === "clinical_trial" && r.extra) {
      const st = (r.extra.status || "").toUpperCase();
      const cls = /RECRUIT/.test(st) ? "status-recruiting" : "status-completed";
      const ph = (r.extra.phase || []).join("/").replace(/PHASE/gi, "Ph ");
      statusBadge = badge("status " + cls, esc((st.charAt(0) + st.slice(1).toLowerCase()).replace(/_/g, " ")) + (ph ? " · " + esc(ph) : ""));
    }
    const meta = [];
    if (r.source) meta.push(`<span class="src">${esc(r.source)}</span>`);
    if (r.journal) meta.push(`<span class="jrnl">${esc(r.journal)}</span>`);
    if (r.authors) meta.push(esc(trunc(r.authors, 90)));
    if (r.extra && r.extra.nct_id) meta.push(esc(r.extra.nct_id));

    const needMore = (r.summary || "").length > 180;
    c.innerHTML = `
      <div class="row1">${typeBadge}${ivBadges}${statusBadge}${flags}<span class="spacer-x"></span><span class="date">${r.published_date ? fmtDate(r.published_date) : ""}</span></div>
      <h3 class="title"><a href="${esc(r.url)}" target="_blank" rel="noopener">${esc(r.title)}</a></h3>
      <div class="meta">${meta.join('<span aria-hidden="true">·</span>')}</div>
      ${r.summary ? `<p class="summary">${esc(r.summary)}</p>` : ""}
      <div class="foot">
        ${altmetricEl(r)}
        ${needMore ? `<button class="more">Show more</button>` : ""}
        <a class="link-out" href="${esc(r.url)}" target="_blank" rel="noopener">Open source
          <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><path d="M7 17 17 7M8 7h9v9"/></svg></a>
      </div>`;
    const moreBtn = c.querySelector(".more");
    if (moreBtn) moreBtn.addEventListener("click", () => {
      c.classList.toggle("expanded");
      moreBtn.textContent = c.classList.contains("expanded") ? "Show less" : "Show more";
    });
    return c;
  }
  function trunc(s, n) { s = String(s); return s.length > n ? s.slice(0, n - 1) + "…" : s; }

  // ---- sorting ----------------------------------------------------------
  function sortRows(rows) {
    const s = state.sort;
    const by = {
      "date-desc": (a, b) => (b.published_date || "").localeCompare(a.published_date || ""),
      "date-asc": (a, b) => (a.published_date || "").localeCompare(b.published_date || ""),
      "altmetric-desc": (a, b) => (b.altmetric_score || 0) - (a.altmetric_score || 0) || (b.published_date || "").localeCompare(a.published_date || ""),
      "type": (a, b) => (a.source_type_label || "").localeCompare(b.source_type_label || "") || (b.published_date || "").localeCompare(a.published_date || ""),
    };
    return rows.slice().sort(by[s] || by["date-desc"]);
  }

  // ---- main update ------------------------------------------------------
  function update() {
    renderFilters();
    const rows = sortRows(filtered(null));
    renderTimeline(rows);
    const host = $("#cards"); host.innerHTML = "";
    if (!rows.length) {
      host.appendChild(el("div", "empty", `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6"><circle cx="11" cy="11" r="7"/><path d="m21 21-4.3-4.3"/></svg><h3>No matching evidence</h3><p>Try widening the date range or clearing some filters.</p>`));
    } else {
      const frag = document.createDocumentFragment();
      rows.forEach(r => frag.appendChild(card(r)));
      host.appendChild(frag);
    }
    $("#count-line").innerHTML = `Showing <b>${rows.length}</b> of ${DATA.length} evidence items`;
    writeURL();
  }

  // ---- events -----------------------------------------------------------
  function wireEvents() {
    let t;
    $("#search").addEventListener("input", e => { clearTimeout(t); t = setTimeout(() => { state.search = e.target.value; update(); }, 180); });
    $("#sort").addEventListener("change", e => { state.sort = e.target.value; update(); });
    $$("#f-date button").forEach(b => b.addEventListener("click", () => { state.dateDays = b.dataset.days; update(); }));
    $$(".toggle-row").forEach(tr => tr.addEventListener("click", () => { state[tr.dataset.toggle] = !state[tr.dataset.toggle]; update(); }));
    $("#clear-filters").addEventListener("click", () => {
      state.interventions.clear(); state.types.clear(); state.species.clear();
      state.dateDays = "all"; state.bundibugyo = state.canadian = state.isnew = false;
      state.search = ""; $("#search").value = "";
      update();
    });
    // mobile filters
    const open = () => { $("#filters").classList.add("open"); $("#filters-backdrop").classList.add("open"); };
    const close = () => { $("#filters").classList.remove("open"); $("#filters-backdrop").classList.remove("open"); };
    $("#open-filters").addEventListener("click", open);
    $("#close-filters").addEventListener("click", close);
    $("#filters-backdrop").addEventListener("click", close);
  }

  // ---- footer sources ---------------------------------------------------
  function renderFooter() {
    const srcs = {};
    DATA.forEach(r => { srcs[r.source] = (srcs[r.source] || 0) + 1; });
    const top = Object.entries(srcs).sort((a, b) => b[1] - a[1]);
    $("#foot-chips").innerHTML = top.map(([s, n]) => `<span class="chip">${esc(s)} · ${n}</span>`).join("");
    $("#foot-sources").innerHTML = `<strong>Sources monitored:</strong> Europe PMC (PubMed/MEDLINE + preprints), ClinicalTrials.gov, WHO Disease Outbreak News, CIDRAP, Africa CDC, CDC EID, and news search across CBC, STAT, Reuters and others, plus pharma press releases.`;
  }

  // ---- boot -------------------------------------------------------------
  function boot(payload) {
    DATA = payload.records || [];
    META = payload;
    const gen = payload.generated_at ? new Date(payload.generated_at) : null;
    $("#updated-stamp").innerHTML = gen
      ? `Updated <b>${gen.toLocaleDateString("en-CA", { month: "short", day: "numeric", year: "numeric" })}</b><br>${DATA.length} items · daily refresh`
      : `${DATA.length} items`;
    initTheme();
    readURL();
    $("#search").value = state.search;
    $("#sort").value = state.sort;
    renderKPIs();
    renderSituation();
    renderCoverage();
    renderFooter();
    wireEvents();
    update();
  }

  function loadError(msg) {
    $("#cards").innerHTML = `<div class="empty"><h3>Could not load evidence data</h3><p>${esc(msg)}</p></div>`;
  }

  if (window.__EVIDENCE__) {
    boot(window.__EVIDENCE__);
  } else {
    fetch("data/evidence.json", { cache: "no-cache" })
      .then(r => { if (!r.ok) throw new Error("HTTP " + r.status); return r.json(); })
      .then(boot)
      .catch(e => loadError("The data file (data/evidence.json) has not been generated yet, or failed to load. Run the pipeline, then reload. (" + e.message + ")"));
  }
})();
