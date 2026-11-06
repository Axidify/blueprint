/* Blueprint clickable mock-up engine.
 *
 * Renders a project's spec (window.SPEC, written by tools/mockup.py build) as a clickable app.
 * URL: index.html#/<screen>?role=<role>&record=<id>&page=<n>&dialog=<id>&clean=1
 *   clean=1 hides the feedback UI (used for screenshots).
 *
 * Filters and search boxes on lists work on the sample rows (Search applies, Clear Filters resets), and what
 * is typed into a form is kept while moving between its steps or opening a dialog.
 *
 * Feedback mode: press "Feedback" (or F2), click any element, type a comment. Comments are saved to the
 * mock-up server (tools/mockup.py serve) when the page is served over http, otherwise to localStorage
 * with an Export button. A comment the server does not take is kept in localStorage and sent again later.
 */
(function () {
  "use strict";
  const S = window.SPEC;
  const P = S.project;
  const app = document.getElementById("app");
  const byId = (list, id) => (list || []).find((x) => x.id === id);
  const esc = (v) => String(v == null ? "" : v).replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
  const slug = (v) => String(v).toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "");

  document.documentElement.style.setProperty("--primary", P.primary_color || "#1f6fb2");
  document.title = `${P.name} – Mock-up v${P.version}`;

  // ------------------------------------------------------------------ routing
  function route() {
    const [path, query] = (location.hash.replace(/^#\/?/, "") || "").split("?");
    const q = Object.fromEntries(new URLSearchParams(query || ""));
    if (q.role) sessionStorage.setItem("mock-role", q.role);
    const role = q.role || sessionStorage.getItem("mock-role");
    return { screen: path || (role ? firstScreen(role) : "login"), role, q };
  }
  function go(screen, extra) {
    const r = route();
    const q = new URLSearchParams({ ...(r.q.clean ? { clean: 1 } : {}), ...(extra || {}) });
    location.hash = `#/${screen}${q.toString() ? "?" + q : ""}`;
  }
  function firstScreen(role) {
    const s = S.screens.find((x) => x.menu && (x.roles || []).includes(role));
    return s ? s.id : "login";
  }
  const canSee = (s, role) => !s.roles || s.roles.includes(role);

  // ------------------------------------------------------------------ data helpers
  function rows(list) {
    let data = (S.data || {})[list.data] || [];
    if (list.where) data = data.filter((r) => matches(list.where, r));
    return data;
  }
  // `when`/`where` match: {field: value} or {field: [value, value]}.
  function matches(cond, row) {
    if (!cond) return true;
    return Object.entries(cond).every(([k, v]) => (Array.isArray(v) ? v.map(String).includes(String(row[k])) : String(row[k]) === String(v)));
  }
  function record(screen, q) {
    const data = (S.data || {})[screen.data] || [];
    const key = Object.keys(data[0] || {})[0];
    return data.find((r) => String(r[key]) === String(q.record || screen.record)) || data[0] || {};
  }
  function options(field) {
    if (field.options) return field.options;
    if (field.options_from) {
      const [list, key] = field.options_from.split(".");
      return ((S.data || {})[list] || []).map((r) => r[key]);
    }
    return [];
  }
  // A status chip takes the `color` of the status with that name (or id) in spec.statuses. Without one
  // the colour is guessed from the wording, the negative words first: "Inactive" must not match "active".
  const CHIP = { green: "ok", amber: "warn", red: "bad", grey: "neutral", gray: "neutral" };
  const statusColor = {};
  (S.statuses || []).forEach((st) => {
    const cls = CHIP[String(st.color || "").toLowerCase()];
    if (cls) [st.name, st.id].forEach((k) => { if (k != null) statusColor[String(k).trim().toLowerCase()] = cls; });
  });
  function statusClass(v) {
    const s = String(v).trim().toLowerCase();
    if (statusColor[s]) return statusColor[s];
    if (/(reject|cancel|overdue|fail|declin|expire|inactive|unavailable|incomplete|disapprov|\bnot (approved|completed|done|active|available))/.test(s)) return "bad";
    if (/(pending|waiting|due|submitted|progress)/.test(s)) return "warn";
    if (/(approved|completed|done|active|available)/.test(s)) return "ok";
    return "neutral";
  }

  // ------------------------------------------------------------------ renderers
  function shell(r, body) {
    const role = byId(S.roles, r.role) || { name: r.role };
    const menu = S.screens.filter((s) => s.menu && canSee(s, r.role))
      .map((s) => `<a class="menu-item ${s.id === r.screen ? "active" : ""}" data-el="menu:${esc(s.menu)}" href="#/${s.id}${r.q.clean ? "?clean=1" : ""}">${esc(s.menu)}</a>`).join("");
    return `
      <header class="topbar">
        <div class="brand"><span class="brand-mark">${esc(P.short_name || P.name[0])}</span><span>${esc(P.name)}</span></div>
        <div class="topbar-right">
          <span class="user" data-el="header:user">${role.user ? `${esc(role.user)} · ` : ""}${esc(role.name)}</span>
          <select class="role-switch fb-hide" title="Switch role (mock-up only)">${S.roles.map((x) => `<option value="${x.id}" ${x.id === r.role ? "selected" : ""}>${esc(x.name)}</option>`).join("")}</select>
          <a class="logout" href="#/login" data-el="header:logout">Logout</a>
        </div>
      </header>
      <div class="layout">
        <nav class="sidebar">${menu}</nav>
        <main class="content" id="content">${body}</main>
      </div>`;
  }

  function renderLogin(screen) {
    return `
      <div class="login-wrap">
        <div class="login-card" data-el="section:Login">
          <div class="login-brand"><span class="brand-mark big">${esc(P.short_name || P.name[0])}</span><h1>${esc(P.name)}</h1><p>${esc(P.client)}</p></div>
          <label class="f-label">Username</label><input class="f-input" data-el="field:username" placeholder="Network ID">
          <label class="f-label">Password</label><input class="f-input" type="password" data-el="field:password" placeholder="Password">
          <button class="btn primary block" data-el="button:Login" data-go="${firstScreen(S.roles[0].id)}" data-role="${S.roles[0].id}">Login</button>
          <div class="demo-roles fb-hide"><span>Mock-up: sign in as</span>${S.roles.map((x) => `<button class="btn small" data-role-login="${x.id}">${esc(x.name)}</button>`).join("")}</div>
        </div>
      </div>`;
  }

  function title(screen) {
    return `<div class="page-head"><h2 data-el="title:${esc(screen.title)}">${esc(screen.title)}</h2>${screen.subtitle ? `<p>${esc(screen.subtitle)}</p>` : ""}</div>`;
  }

  function renderStats(stats, list) {
    if (!stats) return "";
    const base = list ? rows(list) : [];
    const value = (s) => (s.count === undefined ? s.value : s.count === "all" ? base.length : base.filter((r) => matches(s.count, r)).length);
    return `<div class="stats">${stats.map((s) => `<div class="stat" data-el="stat:${esc(s.label)}"><div class="stat-value">${esc(value(s))}</div><div class="stat-label">${esc(s.label)}</div></div>`).join("")}</div>`;
  }

  function renderList(list, r) {
    if (!list) return "";
    const data = rows(list);
    const cols = list.columns || [];
    const filters = (list.filters || []).map((f) => {
      const col = cols.find((c) => c.field === f) || { label: String(f).replace(/_/g, " ").replace(/\b\w/g, (ch) => ch.toUpperCase()) };
      const vals = [...new Set(((S.data || {})[list.data] || []).map((x) => x[f]))];
      return `<div class="filter" data-el="filter:${esc(col.label)}"><label>${esc(col.label)}</label><select class="f-input" data-filter="${esc(f)}"><option>All</option>${vals.map((v) => `<option>${esc(v)}</option>`).join("")}</select></div>`;
    }).join("");
    const search = (list.search || []).map((f) => {
      const col = cols.find((c) => c.field === f) || { label: f };
      return `<div class="filter" data-el="search:${esc(col.label)}"><label>${esc(col.label)}</label><input class="f-input" placeholder="Search" data-search="${esc(f)}"></div>`;
    }).join("");
    const toolbar = (list.toolbar || []).map((b) => button(b, r)).join("");
    const key = Object.keys(data[0] || {})[0];
    // Each row carries the values its filters and search boxes look at (also fields that are not columns).
    const watched = [...(list.filters || []), ...(list.search || [])];
    const watchedValues = (row) => esc(JSON.stringify(Object.fromEntries(watched.map((f) => [f, row[f] == null ? "" : String(row[f])]))));
    const body = data.length ? data.map((row) => `<tr data-row="${watchedValues(row)}">${cols.map((c) => `<td>${c.chip ? `<span class="chip ${statusClass(row[c.field])}">${esc(row[c.field])}</span>` : esc(row[c.field])}</td>`).join("")}${(list.actions || []).length ? `<td class="actions">${list.actions.filter((a) => matches(a.when, row)).map((a) => `<a href="#" class="link" data-el="action:${esc(a.label)}" ${a.to ? `data-go="${a.to}" data-record="${esc(row[key])}"` : ""} ${a.toast ? `data-toast="${esc(a.toast)}"` : ""}>${esc(a.label)}</a>`).join(" ")}</td>` : ""}</tr>`).join("")
      : `<tr><td colspan="${cols.length + 1}" class="empty">${esc(list.empty || "No records found")}</td></tr>`;
    return `
      ${search || filters || toolbar ? `<div class="list-tools">${search || filters ? `<div class="filters">${search}${filters}<button class="btn small" data-el="button:Search" data-apply-filters>Search</button><button class="btn small" data-el="button:Clear Filters" data-clear-filters>Clear Filters</button></div>` : "<div></div>"}<div class="toolbar">${toolbar}</div></div>` : ""}
      <div class="table-wrap"><table class="datalist ${cols.length > 9 ? "dense" : ""}">
        <thead><tr>${cols.map((c) => `<th data-el="column:${esc(c.label)}">${esc(c.label)}</th>`).join("")}${(list.actions || []).length ? "<th>Action</th>" : ""}</tr></thead>
        <tbody>${body}${data.length ? `<tr class="none-match" hidden><td colspan="${cols.length + 1}" class="empty">${esc(list.empty || "No records found")}</td></tr>` : ""}</tbody>
      </table></div>
      <div class="pager" data-total="${data.length}">Showing ${data.length} of ${data.length} records</div>`;
  }

  function field(f, value, readonly) {
    const ro = readonly || f.readonly;
    const v = value != null && value !== "" ? value : f.default != null ? f.default : "";
    const req = f.required && !readonly ? '<span class="req">*</span>' : "";
    let input;
    if (ro && !["signature", "file"].includes(f.type)) {
      input = `<div class="f-value">${esc(v) || "-"}</div>`;
    } else switch (f.type) {
      case "textarea": input = `<textarea class="f-input" rows="3" placeholder="${esc(f.placeholder || "")}">${esc(v)}</textarea>`; break;
      case "select": input = `<select class="f-input"><option value="">-- Please Select --</option>${options(f).map((o) => `<option ${String(o) === String(v) ? "selected" : ""}>${esc(o)}</option>`).join("")}</select>`; break;
      case "radio": input = `<div class="choices">${options(f).map((o) => `<label><input type="radio" name="${f.id}" ${String(o) === String(v) ? "checked" : ""}> ${esc(o)}</label>`).join("")}</div>`; break;
      case "checkbox": input = `<div class="choices">${options(f).map((o) => `<label><input type="checkbox"> ${esc(o)}</label>`).join("")}</div>`; break;
      case "date": input = `<input class="f-input" type="date" value="${esc(v)}">`; break;
      case "datetime": input = `<input class="f-input" type="datetime-local" value="${esc(v)}">`; break;
      case "number": input = `<input class="f-input" type="number" value="${esc(v)}">`; break;
      case "file": input = ro ? `<div class="f-value">${esc(v) || "-"}</div>` : `<div class="file-drop">Drop file here or <span class="link">browse</span></div>`; break;
      case "signature": input = `<div class="signature">${ro && v ? `<span class="sig-ink">${esc(v)}</span>` : "Sign here"}</div>`; break;
      case "user": input = `<select class="f-input"><option>${esc(v || "-- Select user --")}</option></select>`; break;
      default: input = `<input class="f-input" value="${esc(v)}" placeholder="${esc(f.placeholder || "")}">`;
    }
    return `<div class="f-row ${f.type === "textarea" ? "wide" : ""}" data-el="field:${esc(f.id)}"><label class="f-label">${esc(f.label)}${req}</label><div class="f-control">${input}${f.help && !ro ? `<div class="f-help">${esc(f.help)}</div>` : ""}</div></div>`;
  }

  function sections(screen, rec, readonly, page) {
    const all = screen.sections || [];
    const pages = [...new Set(all.map((s) => s.page || 1))];
    const current = Number(page || pages[0]);
    const tabs = pages.length > 1 ? `<div class="tabs">${pages.map((p) => {
      const label = (all.find((s) => (s.page || 1) === p) || {}).page_title || `Step ${p}`;
      return `<a href="#" class="tab ${p === current ? "active" : ""}" data-page="${p}" data-el="tab:${esc(label)}">${esc(label)}</a>`;
    }).join("")}</div>` : "";
    const body = all.filter((s) => (s.page || 1) === current).map((s) => `
      <section class="form-section" data-el="section:${esc(s.title)}">
        <h3>${esc(s.title)}</h3>
        ${s.note ? `<p class="note">${esc(s.note)}</p>` : ""}
        <div class="f-grid">${(s.fields || []).map((f) => field(f, rec[f.id], readonly)).join("")}</div>
      </section>`).join("");
    return tabs + body;
  }

  // `attrs` is extra HTML attributes: a dialog's confirm button gets data-close, so it always closes it.
  function button(b, r, rec, attrs) {
    if (b.roles && !b.roles.includes(r.role)) return "";
    if (b.when && !matches(b.when, rec || {})) return "";
    return `<button class="btn ${b.style || ""} ${b.example ? "fb-hide" : ""}" data-el="button:${esc(b.label)}" ${b.to ? `data-go="${b.to}"` : ""} ${b.toast ? `data-toast="${esc(b.toast)}"` : ""} ${b.dialog ? `data-dialog="${b.dialog}"` : ""} ${attrs || ""}>${esc(b.label)}</button>`;
  }
  const buttons = (list, r, rec) => (list && list.length ? `<div class="form-buttons">${list.map((b) => button(b, r, rec)).join("")}</div>` : "");

  function renderTimeline(steps) {
    if (!steps) return "";
    const comments = steps.some((s) => s.comment);
    return `<section class="form-section" data-el="section:Approval Progress"><h3>Approval Progress</h3><table class="datalist compact"><thead><tr><th>Step</th><th>Handled By</th><th>Date &amp; Time</th><th>Status</th>${comments ? "<th>Comment</th>" : ""}</tr></thead><tbody>${steps.map((s) => `<tr><td>${esc(s.step)}</td><td>${esc(s.by) || "-"}</td><td>${esc(s.at) || "-"}</td><td><span class="chip ${statusClass(s.status)}">${esc(s.status)}</span></td>${comments ? `<td>${esc(s.comment) || "-"}</td>` : ""}</tr>`).join("")}</tbody></table></section>`;
  }

  // Process flow diagram, generated from spec.process_flow so it always matches the statuses.
  function renderFlow() {
    const f = S.process_flow;
    if (!f) return "<p>No process_flow in the spec.</p>";
    const steps = f.steps.map((s, i) => `
      ${i ? '<div class="flow-arrow">&#10140;</div>' : ""}
      <div class="flow-step ${s.optional ? "optional" : ""}">
        <div class="flow-num">${i + 1}</div>
        <div class="flow-name">${esc(s.name)}</div>
        <div class="flow-role">${esc(s.role || "")}${s.optional ? " · optional" : ""}</div>
        ${s.status ? `<div class="flow-status"><span class="chip ${statusClass(s.status)}">${esc(s.status)}</span></div>` : ""}
      </div>`).join("");
    return `<div class="flow">
      <h2>${esc(f.title || P.name + " process flow")}</h2>
      <div class="flow-row">${steps}</div>
      ${f.reject ? `<div class="flow-reject"><span class="flow-reject-line"></span><span>${esc(f.reject)}</span></div>` : ""}
      ${f.notes ? `<ul class="flow-notes">${f.notes.map((n) => `<li>${esc(n)}</li>`).join("")}</ul>` : ""}
    </div>`;
  }

  function renderScreen(screen, r) {
    switch (screen.type) {
      case "dashboard":
        return title(screen) + renderStats(screen.stats, screen.list) + renderList(screen.list, r) + buttons(screen.buttons, r);
      case "list":
        return title(screen) + renderList(screen.list, r) + buttons(screen.buttons, r);
      case "form": {
        const rec = r.q.record && screen.data ? record(screen, r.q) : {};
        return title(screen) + sections(screen, rec, false, r.q.page) + buttons(screen.buttons, r);
      }
      case "detail": {
        const rec = record(screen, r.q);
        const src = screen.fields_from ? byId(S.screens, screen.fields_from) : screen;
        const status = rec.status ? `<div class="status-bar">Status: <span class="chip ${statusClass(rec.status)}">${esc(rec.status)}</span></div>` : "";
        const notice = rec.notice ? `<div class="notice" data-el="section:Notice">${esc(rec.notice)}</div>` : "";
        return title(screen) + status + notice + renderTimeline(rec.timeline || screen.timeline) + sections({ sections: (screen.sections || src.sections || []) }, rec, true, r.q.page) + buttons(screen.buttons, r, rec);
      }
      case "custom":
        return title(screen) + (screen.html || "");
      default:
        return title(screen) + `<p>Unknown screen type: ${esc(screen.type)}</p>`;
    }
  }

  function renderDialog(id) {
    const d = byId(S.dialogs, id);
    if (!d) return "";
    return `<div class="modal-back"><div class="modal" data-el="dialog:${esc(d.title)}">
      <div class="modal-head">${esc(d.title)}<a href="#" class="modal-x" data-close>&times;</a></div>
      <div class="modal-body">${d.message ? `<p>${esc(d.message)}</p>` : ""}${(d.fields || []).map((f) => field(f, "", false)).join("")}${d.list ? renderList(d.list, route()) : ""}</div>
      <div class="modal-foot"><button class="btn" data-close>Cancel</button>${button(d.confirm || { label: "OK" }, route(), null, "data-close")}</div>
    </div></div>`;
  }

  // ------------------------------------------------------------------ filters and search
  // They work on the rows already on the page: Search (or Enter in a search box) applies them, Clear Filters
  // resets them. A filter picks one value; a search box matches part of the text, in any letter case.
  function applyFilters(scope) {
    if (!scope) return;
    const picks = [...scope.querySelectorAll("[data-filter]")].filter((s) => s.value !== "All").map((s) => [s.dataset.filter, s.value]);
    const words = [...scope.querySelectorAll("[data-search]")].filter((i) => i.value.trim()).map((i) => [i.dataset.search, i.value.trim().toLowerCase()]);
    const rowsOnPage = scope.querySelectorAll("tbody tr[data-row]");
    let shown = 0;
    rowsOnPage.forEach((tr) => {
      const row = JSON.parse(tr.dataset.row);
      const match = picks.every(([f, v]) => row[f] === v) && words.every(([f, w]) => String(row[f]).toLowerCase().includes(w));
      tr.hidden = !match;
      if (match) shown += 1;
    });
    const none = scope.querySelector("tr.none-match");
    if (none) none.hidden = shown > 0 || !rowsOnPage.length;
    const pager = scope.querySelector(".pager");
    if (pager) pager.textContent = `Showing ${shown} of ${pager.dataset.total} records`;
  }
  const listScope = (el) => el.closest(".modal-body") || document.getElementById("content");

  // ------------------------------------------------------------------ what was typed
  // The page is drawn again on every move (another step of a form, a dialog opening or closing). What the
  // presenter typed or picked is kept while they stay on the same screen and record, and put back after the
  // redraw. Moving to another screen starts clean, as a new form would.
  const typed = { key: null, values: {} };
  const TYPED = "[data-el^='field:'], [data-el^='filter:'], [data-el^='search:']";
  const typedId = (holder) => (holder.closest(".modal") ? "dialog " : "") + holder.dataset.el;
  const controls = (holder) => [...holder.querySelectorAll("input, textarea, select")];
  function rememberTyped() {
    if (!typed.key) return;
    document.querySelectorAll("#app " + TYPED.split(", ").join(", #app ")).forEach((holder) => {
      const found = controls(holder);
      if (found.length) typed.values[typedId(holder)] = found.map((c) => (c.type === "checkbox" || c.type === "radio" ? c.checked : c.value));
    });
  }
  function restoreTyped() {
    document.querySelectorAll("#app " + TYPED.split(", ").join(", #app ")).forEach((holder) => {
      const saved = typed.values[typedId(holder)];
      const found = controls(holder);
      if (!saved || saved.length !== found.length) return;
      found.forEach((c, i) => {
        if (c.type === "checkbox" || c.type === "radio") c.checked = saved[i];
        else if (c.type !== "file") c.value = saved[i];
      });
    });
    const content = document.getElementById("content");
    if (content && content.querySelector("[data-filter], [data-search]")) applyFilters(content);
  }

  // ------------------------------------------------------------------ main render
  function render() {
    const r = route();
    rememberTyped();  // the page still shows the previous view here
    const nowOn = `${r.screen}|${r.q.record || ""}|${r.role || ""}`;
    if (nowOn !== typed.key) Object.assign(typed, { key: nowOn, values: {} });
    document.body.classList.toggle("clean", !!r.q.clean);
    if (r.screen === "__flow") {
      app.innerHTML = renderFlow();
      app.dataset.screen = "__flow";
      return;
    }
    const screen = byId(S.screens, r.screen) || byId(S.screens, "login") || { type: "login" };
    if (screen.type === "login" || !r.role) {
      app.innerHTML = renderLogin(screen);
    } else if (!canSee(screen, r.role)) {
      app.innerHTML = shell(r, `<div class="denied">You do not have access to this page.</div>`);
    } else {
      app.innerHTML = shell(r, renderScreen(screen, r));
    }
    if (r.q.dialog) app.insertAdjacentHTML("beforeend", renderDialog(r.q.dialog));
    app.dataset.screen = screen.id || "login";
    restoreTyped();
    feedback.renderPins();
  }

  function toast(msg, error) {
    const t = document.createElement("div");
    t.className = error ? "toast error" : "toast";
    t.textContent = msg;
    document.body.appendChild(t);
    setTimeout(() => t.remove(), error ? 9000 : 2600);
  }

  document.addEventListener("click", (e) => {
    if (feedback.active) return; // feedback mode handles clicks itself
    const el = e.target.closest("[data-go],[data-toast],[data-dialog],[data-close],[data-page],[data-role-login],[data-apply-filters],[data-clear-filters]");
    if (!el) return;
    e.preventDefault();
    if (el.dataset.applyFilters !== undefined || el.dataset.clearFilters !== undefined) {
      const scope = listScope(el);
      if (el.dataset.clearFilters !== undefined) {
        scope.querySelectorAll("[data-filter]").forEach((s) => { s.value = "All"; });
        scope.querySelectorAll("[data-search]").forEach((i) => { i.value = ""; });
      }
      return applyFilters(scope);
    }
    const r = route();
    if (el.dataset.roleLogin) { sessionStorage.setItem("mock-role", el.dataset.roleLogin); return go(firstScreen(el.dataset.roleLogin)); }
    if (el.dataset.role && el.dataset.go) sessionStorage.setItem("mock-role", el.dataset.role);
    if (el.dataset.toast) toast(el.dataset.toast);
    if (el.dataset.page) return go(r.screen, { page: el.dataset.page, ...(r.q.record ? { record: r.q.record } : {}) });
    if (el.dataset.dialog) return go(r.screen, { dialog: el.dataset.dialog, ...(r.q.record ? { record: r.q.record } : {}) });
    // A dialog's confirm button has both: it goes where it says, and only closes when it goes nowhere.
    if (el.dataset.go) return go(el.dataset.go, el.dataset.record ? { record: el.dataset.record } : {});
    if (el.dataset.close !== undefined) return go(r.screen, r.q.record ? { record: r.q.record } : {});
  });
  document.addEventListener("change", (e) => {
    if (e.target.classList.contains("role-switch")) {
      sessionStorage.setItem("mock-role", e.target.value);
      go(firstScreen(e.target.value));
    }
  });

  // ------------------------------------------------------------------ feedback
  const feedback = {
    active: false,
    items: [],
    remote: location.protocol.startsWith("http"),
    key: `mock-feedback:${P.name}`,
    // Comments the server did not take (it was closed, or the network dropped). They stay in this browser,
    // also across a reload, and are sent again with the next comment, on the next load or with "Try again".
    unsent: [],
    unsentKey: `mock-feedback-unsent:${P.name}`,
    stored(key) {
      try { return JSON.parse(localStorage.getItem(key) || "[]"); } catch (e) { return []; }
    },
    store(key, list) {
      try { localStorage.setItem(key, JSON.stringify(list)); } catch (e) { /* storage full or switched off */ }
    },
    async load() {
      if (this.remote) {
        try {
          const res = await fetch("api/feedback");
          if (!res.ok) throw new Error(res.status);
          this.items = await res.json();
        } catch (e) { this.remote = false; }
      }
      if (!this.remote) { this.items = this.stored(this.key); return; }
      this.unsent = this.stored(this.unsentKey);
      this.items = this.items.concat(this.unsent);
      if (this.unsent.length) await this.resend();
    },
    // Send the unsent comments, oldest first. True when none are left.
    async resend() {
      while (this.unsent.length) {
        try {
          const res = await fetch("api/feedback", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(this.unsent[0]) });
          if (!res.ok) throw new Error(res.status);
        } catch (e) { break; }
        this.unsent.shift();
        this.store(this.unsentKey, this.unsent);
      }
      return !this.unsent.length;
    },
    async save(item) {
      this.items.push(item);
      if (this.remote) {
        this.unsent.push(item);
        this.store(this.unsentKey, this.unsent);
        if (!(await this.resend())) toast("Comment NOT saved to the project: the mock-up server is not answering. It is kept in this browser. Open Feedback to try again or export it.", true);
      } else {
        this.store(this.key, this.items);
      }
      this.refresh();
    },
    refresh() {
      const n = this.unsent.length;
      const btn = document.getElementById("fb-toggle");
      btn.textContent = (this.active ? "Feedback: ON (click an element)" : "Feedback") + (n ? ` · ${n} not saved` : "");
      btn.classList.toggle("fb-unsent", !!n);
      this.renderPins();
      this.renderPanel();
    },
    toggle() {
      this.active = !this.active;
      document.body.classList.toggle("fb-active", this.active);
      this.refresh();
    },
    forScreen() {
      const screen = app.dataset.screen;
      return this.items.filter((c) => c.screen === screen);
    },
    renderPins() {
      document.querySelectorAll(".fb-pin").forEach((p) => p.remove());
      if (document.body.classList.contains("clean")) return;
      this.forScreen().forEach((c) => {
        const target = c.element ? document.querySelector(`[data-el="${CSS.escape(c.element)}"]`) : null;
        const pin = document.createElement("div");
        const unsent = this.unsent.includes(c);
        pin.className = unsent ? "fb-pin unsent" : "fb-pin";
        pin.textContent = this.items.indexOf(c) + 1;
        pin.title = (unsent ? "NOT SAVED YET: " : "") + c.text;
        const rect = target ? target.getBoundingClientRect() : { right: c.x, top: c.y };
        pin.style.left = `${rect.right + window.scrollX - 12}px`;
        pin.style.top = `${rect.top + window.scrollY - 8}px`;
        document.body.appendChild(pin);
      });
    },
    renderPanel() {
      const panel = document.getElementById("fb-panel");
      if (!this.active) { panel.hidden = true; return; }
      panel.hidden = false;
      const list = this.forScreen();
      panel.innerHTML = `<div class="fb-panel-head">Feedback on this screen (${list.length})</div>
        ${list.map((c) => `<div class="fb-item"><b>#${this.items.indexOf(c) + 1}</b> <span class="fb-el">${esc(c.element || "screen")}</span><div>${esc(c.text)}</div><div class="fb-meta">${esc(c.author || "")} ${esc(c.role || "")} · ${esc(c.time.slice(0, 16).replace("T", " "))}</div></div>`).join("") || "<p>No feedback yet. Click any element to add a comment.</p>"}
        ${!this.remote ? `<button class="btn small" id="fb-export">Export feedback (${this.items.length})</button>`
          : !this.unsent.length ? `<p class="fb-meta">Saved to the project folder.</p>`
          : `<div class="fb-warn"><b>${this.unsent.length} comment${this.unsent.length > 1 ? "s" : ""} not saved to the project yet.</b> The mock-up server is not answering. Check that the window that started the mock-up is still open, then try again. The comments are kept in this browser until then.</div>
             <div class="fb-warn-buttons"><button class="btn small primary" id="fb-retry">Try again</button><button class="btn small" id="fb-export">Export unsaved (${this.unsent.length})</button></div>`}`;
      const exp = document.getElementById("fb-export");
      if (exp) exp.onclick = () => {
        const a = document.createElement("a");
        a.href = URL.createObjectURL(new Blob([JSON.stringify(this.remote ? this.unsent : this.items, null, 2)], { type: "application/json" }));
        a.download = `feedback-${new Date().toISOString().slice(0, 10)}.json`;
        a.click();
      };
      const retry = document.getElementById("fb-retry");
      if (retry) retry.onclick = async () => {
        retry.disabled = true;
        const ok = await this.resend();
        this.refresh();
        toast(ok ? "All comments are now saved to the project." : "Still not saved: the mock-up server is not answering.", !ok);
      };
    },
    capture(e) {
      if (!this.active || e.target.closest("#fb-panel,#fb-toggle,.fb-dialog")) return;
      e.preventDefault();
      e.stopPropagation();
      const target = e.target.closest("[data-el]");
      const element = target ? target.dataset.el : "";
      const r = route();
      const box = document.createElement("div");
      box.className = "fb-dialog";
      box.innerHTML = `<div class="fb-dialog-inner"><div class="fb-panel-head">Comment on: ${esc(element || "this screen")}</div>
        <input class="f-input" id="fb-author" placeholder="Your name (optional)" value="${esc(localStorage.getItem("mock-author") || "")}">
        <textarea class="f-input" id="fb-text" rows="4" placeholder="What should change?"></textarea>
        <div class="form-buttons"><button class="btn" id="fb-cancel">Cancel</button><button class="btn primary" id="fb-save">Save comment</button></div></div>`;
      document.body.appendChild(box);
      box.querySelector("#fb-text").focus();
      box.querySelector("#fb-cancel").onclick = () => box.remove();
      box.querySelector("#fb-save").onclick = () => {
        const text = box.querySelector("#fb-text").value.trim();
        const author = box.querySelector("#fb-author").value.trim();
        localStorage.setItem("mock-author", author);
        box.remove();
        if (!text) return;
        this.save({ screen: app.dataset.screen, role: r.role || "", element, text, author, x: e.pageX, y: e.pageY, time: new Date().toISOString(), version: P.version });
      };
    },
  };

  document.addEventListener("click", (e) => feedback.capture(e), true);
  document.addEventListener("keydown", (e) => {
    if (e.key === "F2") feedback.toggle();
    if (e.key === "Enter" && e.target.matches && e.target.matches("[data-search]")) applyFilters(listScope(e.target));
  });
  window.addEventListener("hashchange", render);
  window.addEventListener("resize", () => feedback.renderPins());

  const tools = document.createElement("div");
  tools.className = "fb-tools";
  tools.innerHTML = `<button id="fb-toggle" class="btn small">Feedback</button><div id="fb-panel" hidden></div>`;
  document.body.appendChild(tools);
  document.getElementById("fb-toggle").onclick = () => feedback.toggle();

  feedback.load().then(() => { render(); feedback.refresh(); });
})();
