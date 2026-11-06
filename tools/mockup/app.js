/* Blueprint clickable mock-up engine.
 *
 * Renders a project's spec (window.SPEC, written by tools/mockup.py build) as a clickable app.
 * URL: index.html#/<screen>?role=<role>&record=<id>&page=<n>&dialog=<id>&clean=1
 *   clean=1 hides the feedback UI (used for screenshots).
 *
 * Filters and search boxes on lists work on the sample rows (Search applies, Clear Filters resets), and what
 * is typed into a form is kept while moving between its steps or opening a dialog.
 *
 * The main button of a form and a dialog's confirm button point out required fields left empty; pressing
 * the button again goes on without them, so a presenter need not fill in a whole form. A file field takes a
 * sample file and a signature field signs when clicked. Dialogs close with Esc or a click outside them.
 *
 * The presenter's tools sit together at the bottom right, dark so nobody takes them for the client's system,
 * and never appear in screenshots: the mock-up's version, "View as" to switch role, and Feedback. The bar
 * folds away to one small button (remembered), and while the Feedback panel is open the page makes room for it.
 *
 * A form in steps shows its main button on the last step only, with Next and Previous before it. A detail
 * screen may show a related list (the records that name the one shown: `where_record`), and a drop-down may
 * offer only the records a filter lets through (`options_from: {list, field, where}`), following the walk-through.
 * The theme the build drew in is window.MOCKUP_BUILD.theme; the desk theme speaks in sentence case and keeps
 * one primary button per screen.
 *
 * In feedback mode every part of a screen can be commented on: the header, the side menu, the page
 * background, a row, a single cell, as well as the named fields, columns and buttons.
 *
 * A project may add code of its own (spec/mockup.js and spec/mockup.css), for what the spec cannot describe.
 * It is loaded after this engine and works through window.Mockup (see "the project's own code" below).
 *
 * Served by tools/mockup.py, the mock-up follows its spec: it asks every few seconds which build is being
 * served, and when that changed the bar offers "Update ready". Nothing reloads by itself: a presenter in the
 * middle of a walk-through picks the moment, and comes back on the same screen, with feedback mode off. In a live session the bar
 * also says "Live" while the assistant is listening, and each comment shows what became of it.
 *
 * A button with `set_status` moves the record it acts on to that status, so a process can be acted out:
 * approve a request and it leaves the approver's list, shows its new status and loses its Approve button.
 * The main button of a new, empty form adds a record to the list the form fills in (the build says which:
 * window.MOCKUP_BUILD.creates), so a submitted request lands in the next person's list.
 *
 * The walk-through is kept: records added and moved stay for the browser tab's session (sessionStorage),
 * through a reload and through Update ready. Served by tools/mockup.py, the changes are shared: each one is sent
 * to the server and every browser showing the mock-up picks it up within a few seconds (each keeps its own
 * role). "Reset sample data" on the presenter's bar puts the sample data back, for everyone. When a new build
 * changes the sample data, the changes that still fit are kept and the rest are dropped. Screenshots (clean=1)
 * always show the sample data.
 *
 * What is custom development on the project's platform (from the spec's platform_fit, and what the project's own
 * code adds) carries a small tag while presenting; "Custom work" on the bar hides the tags. Never in screenshots.
 *
 * Feedback mode: press "Feedback" (or F2), click any element, type a comment. Comments saved by other
 * people in the room appear within a few seconds, and each shows the number it was saved under. A comment can
 * be edited or deleted from the Feedback panel while it waits (Received), by the browser that wrote it or by
 * the presenter on the machine running the server; once it is being worked on it is locked.
 *
 * In short: press "Feedback" (or F2), click any element, type a comment. Comments are saved to the
 * mock-up server (tools/mockup.py serve) when the page is served over http, otherwise to localStorage
 * with an Export button. A comment the server does not take is kept in localStorage and sent again later.
 */
(function () {
  "use strict";
  const S = window.SPEC;
  const P = S.project;
  S.data = S.data || {};
  // What the build worked out for the engine: the buttons that add a record, and what to tag as custom work.
  const BUILD = window.MOCKUP_BUILD || {};
  const clone = (v) => JSON.parse(JSON.stringify(v === undefined ? null : v));
  const app = document.getElementById("app");
  const byId = (list, id) => (list || []).find((x) => x.id === id);
  const esc = (v) => String(v == null ? "" : v).replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
  const slug = (v) => String(v).toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "");

  // The look the build drew it in (project.theme; a spec without one keeps joget). The desk theme speaks in
  // sentence case and follows the design language's button tiers; its accent is Cobalt when the spec sets none.
  const THEME = String(BUILD.theme || P.theme || "joget");
  const DESK = THEME === "desk";
  document.documentElement.dataset.theme = THEME;
  document.documentElement.style.setProperty("--primary", P.primary_color || (DESK ? "#1F5FBF" : "#1f6fb2"));
  // The engine's own words on the client's screens (the spec's words are drawn as the spec writes them).
  const W = DESK
    ? { select: "Select…", selectUser: "Select a person…", logout: "Sign out", login: "Sign in", clear: "Clear filters", status: "Status", progress: "Approval progress",
        by: "Handled by", at: "Date and time", comment: "Comment", step: "Step", action: "Actions", waiting: "Waiting",
        showing: (n, total) => (Number(n) === Number(total) ? `${total} record${Number(total) === 1 ? "" : "s"}` : `${n} of ${total} records`) }
    : { select: "-- Please Select --", selectUser: "-- Select user --", logout: "Logout", login: "Login", clear: "Clear Filters", status: "Status:", progress: "Approval Progress",
        by: "Handled By", at: "Date &amp; Time", comment: "Comment", step: "Step", action: "Action", waiting: "Waiting",
        showing: (n, total) => `Showing ${n} of ${total} records` };
  // project.text_size: larger text on the client's screens (the presenter's tools keep their size).
  document.documentElement.style.setProperty("--ts", { large: 1.12, larger: 1.25 }[String(P.text_size || "").toLowerCase()] || 1);
  // The client's own look on top of the theme (assets/look.css): only what the spec sets, so a spec without
  // these is drawn as its theme draws it. The build checked the values.
  for (const key of ["corners", "menu", "header"]) {
    if (P[key]) document.documentElement.dataset[key] = String(P[key]).toLowerCase();
  }
  // project.font: the client's font first, then the theme's own as the fallback.
  if (P.font) {
    const root = document.documentElement;
    root.style.setProperty("--font", `"${String(P.font).replace(/["\\]/g, "")}", ${getComputedStyle(root).getPropertyValue("--font").trim() || "sans-serif"}`);
  }
  // project.logo: the client's logo in place of the letters (the build copied it into assets/).
  const LOGO = BUILD.logo || "";
  if (LOGO) document.documentElement.classList.add("has-logo");
  // project.data_colors: the complementary pair for data (people's initials), as the desk design
  // language spends extra colour only on data. The desk theme sets teal and pink when the spec names none.
  if (Array.isArray(P.data_colors)) P.data_colors.slice(0, 2).forEach((c, i) => document.documentElement.style.setProperty(`--data-${i + 1}`, String(c)));
  const brandMark = (big) => (LOGO
    ? `<img class="brand-logo${big ? " big" : ""}" src="${esc(LOGO)}" alt="${esc(P.client || P.name)}">`
    : `<span class="brand-mark${big ? " big" : ""}">${esc(P.short_name || P.name[0])}</span>`);
  // With a red brand colour the main button and a danger button would be two reds side by side (Approve
  // next to Reject). The danger button is then drawn as an outline, so the two cannot be mistaken.
  (function () {
    const m = /^#?([0-9a-f]{3}|[0-9a-f]{6})$/i.exec(String(P.primary_color || "").trim());
    if (!m) return;
    const hex = m[1].length === 3 ? m[1].replace(/./g, "$&$&") : m[1];
    const [red, green, blue] = [0, 2, 4].map((i) => parseInt(hex.slice(i, i + 2), 16) / 255);
    const max = Math.max(red, green, blue), min = Math.min(red, green, blue), light = (max + min) / 2, d = max - min;
    if (!d) return;
    const sat = d / (1 - Math.abs(2 * light - 1));
    const hue = 60 * (max === red ? ((green - blue) / d + 6) % 6 : max === green ? (blue - red) / d + 2 : (red - green) / d + 4);
    if ((hue < 25 || hue > 335) && sat > 0.45 && light > 0.25 && light < 0.65) document.documentElement.classList.add("danger-outline");
  })();
  document.title = `${P.name} – Mock-up v${P.version}`;

  // ------------------------------------------------------------------ routing
  function address() {
    const [path, query] = (location.hash.replace(/^#\/?/, "") || "").split("?");
    return { path, q: Object.fromEntries(new URLSearchParams(query || "")) };
  }
  function route() {
    const { path, q } = address();
    if (q.role) sessionStorage.setItem("mock-role", q.role);  // a link that names the role signs in as it
    const role = q.role || sessionStorage.getItem("mock-role");
    return { screen: path || (role ? firstScreen(role) : "login"), role, q };
  }
  // `replace`: take the place of the current address in the browser's history. Dialogs open and close that
  // way, so the Back button goes to the screen before and never reopens a dialog that was closed.
  function go(screen, extra, replace) {
    // Only reads the address: `route` would sign in again as the role the address names, undoing a switch of role.
    const q = new URLSearchParams({ ...(address().q.clean ? { clean: 1 } : {}), ...(extra || {}) });
    const hash = `#/${screen}${q.toString() ? "?" + q : ""}`;
    if (replace) location.replace(hash);
    else location.hash = hash;
  }
  const stay = (q) => ({ ...(q.record ? { record: q.record } : {}), ...(q.page ? { page: q.page } : {}) });  // same record, same step
  function closeDialog() {
    const r = route();
    if (r.q.dialog) go(r.screen, stay(r.q), true);
  }
  function firstScreen(role) {
    const s = S.screens.find((x) => x.menu && (x.roles || []).includes(role));
    return s ? s.id : "login";
  }
  const canSee = (s, role) => !s.roles || s.roles.includes(role);

  // ------------------------------------------------------------------ data helpers
  // A list shows the rows its `where` lets through. `where_by_role` gives a role a filter of its own, so
  // a task list can show each role the records waiting for it; a role it does not name gets `where`.
  // A list on a detail screen can show the records that name the one shown (a car's loans): `where_record:
  // {field of the list's rows: field of the record shown}`; `shown` is that record.
  function rows(list, shown) {
    let data = (S.data || {})[list.data] || [];
    const where = (list.where_by_role || {})[route().role] || list.where;
    if (where) data = data.filter((r) => matches(where, r));
    if (list.where_record && typeof list.where_record === "object") {
      const link = Object.entries(list.where_record);
      data = data.filter((r) => link.every(([mine, theirs]) => shown && shown[theirs] != null && String(r[mine]) === String(shown[theirs])));
    }
    return data;
  }
  // The step a record is waiting at: the first line of its own progress with no date that is not skipped.
  const SKIPPED = /skip|not required|not applicable|n\/a/i;
  const waitingStep = (rec) => (rec.timeline || []).find((s) => !s.at && !SKIPPED.test(String(s.status || "")));
  // Is that step handled by whoever is signed in? The step names the person (`by`): the role's `user`.
  function waitingForMe(rec) {
    const role = byId(S.roles, route().role) || {};
    const step = waitingStep(rec);
    return !!step && !!step.by && [role.user, role.name].some((n) => n != null && String(n).trim().toLowerCase() === String(step.by).trim().toLowerCase());
  }
  // `when`/`where` match: {field: value} or {field: [value, value]}; `waiting_for_me: true` asks the above.
  function matches(cond, row) {
    if (!cond) return true;
    return Object.entries(cond).every(([k, v]) => (k === "waiting_for_me" ? waitingForMe(row) === (v !== false && v !== "false")
      : Array.isArray(v) ? v.map(String).includes(String(row[k])) : String(row[k]) === String(v)));
  }
  function record(screen, q) {
    const data = (S.data || {})[screen.data] || [];
    const key = Object.keys(data[0] || {})[0];
    return data.find((r) => String(r[key]) === String(q.record || screen.record)) || data[0] || {};
  }
  // A form is filled in from a record when it is opened on one (?record=) or names one of its own (`record`,
  // as a detail screen does); otherwise it starts empty.
  const formOnRecord = (screen, q) => !!screen.data && (!!q.record || (screen.record != null && screen.record !== ""));
  // `options_from: cars.reg_no`, or with a filter `{list: cars, field: reg_no, where: {status: Available}}`: the
  // choices follow the walk-through (a car put on loan leaves the drop-down).
  // The people a user field offers: the `user` of each of its roles, or everyone the spec names.
  function peopleFor(field) {
    const wanted = field.roles == null ? null : [].concat(field.roles);
    const fromRoles = (S.roles || []).filter((r) => !wanted || wanted.includes(r.id)).map((r) => r.user).filter(Boolean);
    const listed = wanted ? [] : ((S.data || {}).users || []).map((u) => u && (u.full_name || u.name || u.username)).filter(Boolean);
    return [...new Set([...fromRoles, ...listed])];
  }
  function options(field) {
    if (field.options) return field.options;
    const from = field.options_from;
    if (from && typeof from === "object") {
      return ((S.data || {})[from.list] || []).filter((r) => matches(from.where, r)).map((r) => r[from.field]).filter((v) => v != null && v !== "");
    }
    if (from) {
      const [list, key] = String(from).split(".");
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
    // Waiting for someone, or being worked on: drawn as amber, except in the desk theme (the accent).
    if (/(pending|waiting|submitted|progress|review|processing)/.test(s)) return "prog";
    if (/\bdue\b/.test(s)) return "warn";
    if (/(approved|completed|done|active|available)/.test(s)) return "ok";
    return "neutral";
  }

  // ------------------------------------------------------------------ status moves
  // A button with `set_status` moves the record it acts on to that status: the record of the detail screen
  // (or of a form opened on a record), also from a dialog opened there, or the row of a list action. Lists,
  // counts, the status shown and the buttons that depend on the status follow, because all are drawn from
  // that record. Nothing is saved: reloading the page puts the sample data back.
  // `set_status` is one status, or {where the record is: status it moves to} for a button that serves
  // several steps (one Approve for every approver in a chain). "Where it is" is the step it is waiting at,
  // by the step's name in its progress, or else the status it is in. With `also_move` a record it names in
  // another list moves along (approving a loan puts its courtesy car on loan).
  const same = (a, b) => a != null && b != null && String(a).trim().toLowerCase() === String(b).trim().toLowerCase();
  const findStatus = (v) => (S.statuses || []).find((st) => same(st.id, v) || same(st.name, v));
  const two = (n) => String(n).padStart(2, "0");
  function now() {
    const d = new Date();
    return `${d.getFullYear()}-${two(d.getMonth() + 1)}-${two(d.getDate())} ${two(d.getHours())}:${two(d.getMinutes())}`;
  }
  function recordToMove(el, r) {
    if (el.dataset.list) {  // an action on a row: that row's record
      const data = (S.data || {})[el.dataset.list] || [];
      const key = Object.keys(data[0] || {})[0];
      return { name: el.dataset.list, rec: data.find((x) => String(x[key]) === el.dataset.record) };
    }
    const screen = byId(S.screens, r.screen);
    if (!screen || !screen.data || !(screen.type === "detail" || (screen.type === "form" && formOnRecord(screen, r.q)))) return {};
    const rec = record(screen, r.q);
    return { name: screen.data, rec: Object.keys(rec).length ? rec : null, timeline: screen.timeline };
  }
  // The attributes of a button that moves a record: where to, and the linked records it moves along (`also_move`).
  function moveAttr(b) {
    const v = b.set_status;
    if (v == null) return "";
    const also = b.also_move ? ` data-also="${esc(JSON.stringify([].concat(b.also_move)))}"` : "";
    return (typeof v === "object" ? `data-status-by="${esc(JSON.stringify(v))}"` : `data-status="${esc(v)}"`) + also;
  }
  // The sample data names a status by its name or by its id: a record keeps whichever it uses.
  function setStatus(rec, to) {
    const was = findStatus(rec.status);
    rec.status = was && same(was.id, rec.status) && !same(was.name, rec.status) ? to.id : to.name;
  }
  // `also_move`: a record of another list that this one names (a loan's `car`) moves along with it, to its
  // own status, and may take values across (`copy: {field there: field here}`).
  // Returns the linked records it moved, as {list: [ids]}, for the walk-through to keep and share.
  function moveLinked(links, rec) {
    const moved = {};
    links.forEach((l) => {
      const list = (S.data || {})[l.data] || [];
      const key = l.key || Object.keys(list[0] || {})[0];
      const other = rec[l.link] == null ? null : list.find((x) => String(x[key]) === String(rec[l.link]));
      const to = findStatus(l.set_status);
      if (!other || !to) return;
      setStatus(other, to);
      Object.entries(l.copy || {}).forEach(([there, here]) => { other[there] = rec[here]; });
      (moved[l.data] = moved[l.data] || []).push(String(other[Object.keys(list[0] || {})[0]]));
    });
    return moved;
  }
  function targetStatus(el, rec) {
    if (el.dataset.status !== undefined) return findStatus(el.dataset.status);
    const by = JSON.parse(el.dataset.statusBy);
    const at = findStatus(rec.status);
    const step = waitingStep(rec);
    const keys = Object.keys(by);
    let from = step ? keys.find((k) => same(k, step.step)) : undefined;
    if (from === undefined) from = keys.find((k) => (at ? findStatus(k) === at : same(k, rec.status)));
    return from === undefined ? undefined : findStatus(by[from]);  // a record the button says nothing about stays
  }
  // Returns the record it moved (or false), after keeping the change for the walk-through.
  function moveStatus(el, r) {
    const { name, rec, timeline } = recordToMove(el, r);
    const to = rec && targetStatus(el, rec);
    if (!to) return false;
    setStatus(rec, to);
    const touched = el.dataset.also ? moveLinked(JSON.parse(el.dataset.also), rec) : {};
    (touched[name] = touched[name] || []).push(String(rec[Object.keys(rec)[0]]));
    try { recordProgress(el, r, name, rec, timeline, to); } finally { demo.save(touched); }
    return rec;
  }
  function recordProgress(el, r, name, rec, timeline, to) {
    // Its progress: the step that was waiting is now handled, by whoever is signed in. A record without
    // progress of its own takes that of the detail screen that shows it.
    const shown = rec.timeline || timeline || (S.screens.find((s) => s.type === "detail" && s.data === name && s.timeline) || {}).timeline;
    if (shown) {
      const role = byId(S.roles, r.role) || {};
      const modal = el.closest(".modal");
      const typedIn = modal ? [...modal.querySelectorAll(".modal-body textarea, .modal-body input.f-input")].map((c) => c.value.trim()).find(Boolean) : "";
      const opener = modal && ((byId(S.screens, r.screen) || {}).buttons || []).find((b) => b.dialog === r.q.dialog);
      const lines = shown.map((s) => ({ ...s }));
      const waiting = lines.findIndex((s) => !s.at && !SKIPPED.test(String(s.status || "")));
      const entry = { by: role.user || role.name || "", at: now(), status: to.name, ...(typedIn ? { comment: typedIn } : {}) };
      if (waiting >= 0) Object.assign(lines[waiting], entry);
      else lines.push({ step: (opener || {}).label || el.textContent.trim(), ...entry });
      // After a final status nothing is waiting any more.
      rec.timeline = Array.isArray(to.next) && !to.next.length ? lines.filter((s) => s.at || SKIPPED.test(String(s.status || ""))) : lines;
    }
    return true;
  }

  // ------------------------------------------------------------------ new records
  // The main button of a new, empty form adds a record to the list the form fills in (the build says which
  // buttons do, to which list and in which status: BUILD.creates). It is filled in as a real system would:
  // what was typed; for anything left empty a sample value (the field's default, a choice, or the value of a
  // sample record in the same status); a new id after the list's own; the signed-in person and the time for
  // fields such as submitted_by and submitted; and, where the list's records show their progress, a first step
  // done by whoever is signed in now and the next one waiting. It then shows in every list and count it matches.
  // People in the desk theme: initials on a soft tint of one of the data colours, the same one for the same
  // person everywhere. A person is anyone a role signs in as or a step of a record's progress names. The
  // initials are drawn by CSS, so the cell's text stays the name.
  const PEOPLE = new Set([...S.roles.map((x) => x.user),
    ...Object.values(S.data || {}).flatMap((rows) => (Array.isArray(rows) ? rows : []).flatMap((x) => (x && Array.isArray(x.timeline) ? x.timeline.map((s) => s && s.by) : [])))]
    .filter((n) => n != null && String(n).trim()).map((n) => String(n).trim().toLowerCase()));
  // `column`: the value is in a list column that holds people, so it is a person even if no role signs in as it.
  const person = (name, column) => {
    const text = String(name == null ? "" : name).trim();
    if (!DESK || !text || !(column || PEOPLE.has(text.toLowerCase()))) return esc(name);
    const initials = text.split(/\s+/).slice(0, 2).map((w) => w[0]).join("").toUpperCase();
    const tone = ([...text.toLowerCase()].reduce((h, c) => (h * 31 + c.charCodeAt(0)) >>> 0, 7) % 2) + 1;
    return `<span class="person" data-initials="${esc(initials)}" data-tone="${tone}">${esc(text)}</span>`;
  };
  // A value kept on one line in a list: one word of up to 20 letters (always), or two words of up to 18
  // together (while the list fits: fitLists).
  const ONE_WORD = /^\S{1,20}$/;
  const TWO_WORDS = /^(?=.{1,18}$)\S+ \S+$/;
  const shortClass = (v) => (ONE_WORD.test(v) ? 'class="nb" ' : TWO_WORDS.test(v) ? 'class="nb2" ' : "");
  // Two short words stay on one line only while their list fits its card: in a list too wide for the screen
  // they wrap again, so the screen (and its screenshot) keeps its width.
  function fitLists() {
    app.querySelectorAll(".table-wrap").forEach((wrap) => {
      const cells = wrap.querySelectorAll("td.nb2, td.nb2-off");
      cells.forEach((td) => td.classList.replace("nb2-off", "nb2"));
      if (wrap.scrollWidth > wrap.clientWidth + 1) cells.forEach((td) => td.classList.replace("nb2", "nb2-off"));
    });
  }
  window.addEventListener("resize", () => fitLists());
  const WHO = /^(submitted_by|created_by|requested_by|raised_by|applied_by|prepared_by|reported_by|requester|requestor|applicant|employee|staff|initiator|submitter|owner)$/i;
  const WHEN = /^(submitted|created|requested|raised|applied|applied_on|date_submitted|date_created|date_requested|submission_date|request_date|application_date|(submitted|created|requested|raised)_(at|on|date|time))$/i;
  function creatingEntry(r, label, dialog) {
    const screen = byId(S.screens, r.screen);
    if (!screen || screen.type !== "form" || formOnRecord(screen, r.q)) return null;
    return (BUILD.creates || []).find((n) => n.screen === screen.id && (dialog ? n.dialog === dialog && n.confirm === label : !n.dialog && n.label === label)) || null;
  }
  const createAttr = (n) => (n ? ` data-create="${esc(n.data)}" data-create-status="${esc(n.status == null ? "" : n.status)}"` : "");
  // A date or time in the format the sample data already uses for that field.
  function dateLike(sample, d) {
    const s = String(sample == null ? "" : sample);
    const ymd = `${d.getFullYear()}-${two(d.getMonth() + 1)}-${two(d.getDate())}`, hm = `${two(d.getHours())}:${two(d.getMinutes())}`;
    const months = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
    let m;
    if ((m = /^\d{4}-\d{2}-\d{2}([ T])\d{2}:\d{2}(:\d{2})?$/.exec(s))) return `${ymd}${m[1]}${hm}${m[2] ? ":00" : ""}`;
    if (/^\d{4}-\d{2}-\d{2}$/.test(s)) return ymd;
    if ((m = /^\d{1,2}\/\d{1,2}\/\d{4}( \d{1,2}:\d{2})?$/.exec(s))) return `${two(d.getDate())}/${two(d.getMonth() + 1)}/${d.getFullYear()}${m[1] ? " " + hm : ""}`;
    if ((m = /^\d{1,2} [A-Za-z]{3,} \d{4}(,? \d{1,2}:\d{2})?$/.exec(s))) return `${d.getDate()} ${months[d.getMonth()]} ${d.getFullYear()}${m[1] ? " " + hm : ""}`;
    return `${ymd} ${hm}`;
  }
  // The next id after the list's own: LN-2026-00142 is followed by LN-2026-00143, 7 by 8.
  function nextId(list, key) {
    const ids = list.map((x) => x[key]).filter((v) => v != null && v !== "");
    const taken = new Set(ids.map(String));
    if (ids.length && ids.every((v) => typeof v === "number")) return Math.max(...ids) + 1;
    const parts = ids.map((v) => /^(.*?)(\d+)(\D*)$/.exec(String(v))).filter(Boolean);
    let made;
    if (parts.length) {
      const [, prefix, , suffix] = parts[0];
      const same = parts.filter((p) => p[1] === prefix && p[3] === suffix);
      const width = Math.max(...same.map((p) => p[2].length));
      let n = Math.max(...same.map((p) => parseInt(p[2], 10)));
      do { n += 1; made = `${prefix}${String(n).padStart(width, "0")}${suffix}`; } while (taken.has(made));
      return made;
    }
    let n = list.length + 1;
    const stem = ids.length ? String(ids[0]) : "NEW";
    do { made = `${stem}-${n}`; n += 1; } while (taken.has(made));
    return made;
  }
  // What was typed into a field of the form, in the record's own terms; "" when nothing was.
  function typedValue(f) {
    const saved = typed.values["field:" + f.id];
    if (!saved || !saved.length) return "";
    const opts = options(f);
    if (f.type === "radio") return opts[saved.indexOf(true)] == null ? "" : opts[saved.indexOf(true)];
    if (f.type === "checkbox") return opts.length ? opts.filter((o, i) => saved[i] === true).join(", ") : saved[0] === true ? true : "";
    const v = saved[0];
    if (typeof v !== "string" || !v.trim()) return "";
    return f.type === "datetime" ? v.replace("T", " ") : v.trim();
  }
  // The first step of a new record's progress is done by whoever submits it; the next one waits.
  function newProgress(name, who) {
    const own = (S.data[name] || []).filter((x) => Array.isArray(x.timeline) && x.timeline.length).sort((a, b) => b.timeline.length - a.timeline.length)[0];
    const steps = ((own && own.timeline) || (S.screens.find((s) => s.type === "detail" && s.data === name && s.timeline) || {}).timeline || [])
      .filter((s) => !SKIPPED.test(String(s.status || "")));
    if (!steps.length) return null;
    const waitWord = (steps.find((s) => !s.at) || {}).status || W.waiting;
    return steps.map((s, i) => (i === 0 ? { step: s.step, by: who, at: now(), status: s.at ? s.status : "Done" }
      : { step: s.step, by: s.by || "", at: "", status: waitWord }));
  }
  let created = 0;  // records added in this page: each new one borrows from a different finished sample record
  function createRecord(el, r) {
    rememberTyped();
    const name = el.dataset.create;
    const list = S.data[name] || (S.data[name] = []);
    const key = Object.keys(list[0] || {})[0] || "id";
    const screen = byId(S.screens, r.screen) || {};
    const fields = (screen.sections || []).flatMap((s) => s.fields || []);
    const role = byId(S.roles, r.role) || {};
    const status = el.dataset.createStatus ? findStatus(el.dataset.createStatus) : null;
    const statusName = status ? status.name : el.dataset.createStatus || "";
    // A sample record at the same stage: its dates and stage fields are the most likely for a record just submitted.
    const peer = list.find((x) => statusName && same(x.status, statusName) || (status && same(x.status, status.id))) || null;
    // Whose details a new record borrows for what was left empty: a finished sample record (its status moves
    // nowhere), a different one each time, so a new request is never the twin of one still open.
    const isOpen = (x) => { const st = findStatus(x.status); return !st || (st.next || []).length > 0; };
    const finished = list.filter((x) => !isOpen(x));
    const atStage = (x) => (statusName && same(x.status, statusName)) || (status && same(x.status, status.id));
    const elsewhere = list.filter((x) => !atStage(x));  // at another stage: not a twin of what waits beside it
    const others = list.filter((x) => x !== peer);
    const pool = finished.length ? finished : elsewhere.length ? elsewhere : others.length ? others : [peer];
    const persona = pool[created % pool.length] || peer;
    created += 1;
    const isDate = (f) => { const fd = fields.find((x) => x.id === f); return fd ? fd.type === "date" || fd.type === "datetime" : WHEN.test(f); };
    const fromSample = (f) => (isDate(f) ? [peer, ...list] : [persona, peer, ...list]).map((x) => x && x[f]).find((v) => v != null && v !== "");
    // A choice that points at things with a life of their own (a car, an asset: their records have a status)
    // takes one no open record holds, where there is one. A category (a leave type) is shared, as before.
    const freeChoice = (field, opts, like) => {
      const from = field.options_from;
      const target = from ? (S.data[typeof from === "object" ? from.list : String(from).split(".")[0]] || []) : [];
      if (!target.some((x) => x && x.status != null)) return like != null && opts.map(String).includes(String(like)) ? like : opts[0];
      const held = new Set(list.filter(isOpen).map((x) => String(x[field.id])));
      const free = opts.find((o) => !held.has(String(o)));
      return free != null ? free : like != null && opts.map(String).includes(String(like)) ? like : opts[0];
    };
    const names = [...new Set([...list.flatMap((x) => Object.keys(x)), ...fields.map((f) => f.id)])].filter((f) => f !== key && f !== "status" && f !== "timeline");
    const rec = { [key]: null };
    const copied = [];  // date fields filled from the sample, moved along with a date that was typed (below)
    names.forEach((f) => {
      const field = fields.find((x) => x.id === f);
      const like = fromSample(f);
      let v = field ? typedValue(field) : "";
      if (v === "" && WHO.test(f) && role.user) v = role.user;
      if (v === "" && WHEN.test(f)) v = dateLike(like, new Date());
      if (v === "" && field) {
        const opts = options(field);
        if (field.default != null && field.default !== "") v = field.default;
        else if (field.type === "file") v = "sample-document.pdf";
        else if (field.type === "signature") v = role.user || role.name || "";
        else if (opts.length) v = field.type === "checkbox" ? (like != null && opts.map(String).includes(String(like)) ? like : "") : freeChoice(field, opts, like);
        else if (like != null) {
          v = like;
          if (field.type === "date") copied.push(f);
        } else if (/^(e\.?g\.?|example)[:,]?\s+/i.test(field.placeholder || "")) v = field.placeholder.replace(/^(e\.?g\.?|example)[:,]?\s+/i, "");
        else if (field.type === "date" || field.type === "datetime") v = dateLike(field.type === "date" ? "2000-01-01" : "", new Date());
      } else if (v === "" && !field && peer && peer[f] != null) v = clone(peer[f]);  // not on the form: as at the same stage
      if (v === "" && WHO.test(f)) v = role.name || "";
      if (typeof like === "number" && v !== "" && !isNaN(Number(v))) v = Number(v);
      if (typeof like === "boolean" && typeof v === "string" && v !== "") v = /^(true|yes|y|1)$/i.test(v);
      if (v !== "" || list.some((x) => f in x)) rec[f] = v;
    });
    // A From typed in and a To from the sample would be days apart the wrong way: the copied dates keep the
    // distance they have in the sample record, from the date that was typed.
    const DAY = 86400000, asDate = (v) => (/^\d{4}-\d{2}-\d{2}$/.test(String(v)) ? Date.parse(`${v}T00:00:00Z`) : NaN);
    const anchor = fields.find((x) => x.type === "date" && !copied.includes(x.id) && typedValue(x) !== "" && !isNaN(asDate(typedValue(x))) && !isNaN(asDate(fromSample(x.id))));
    if (anchor) {
      const shift = Math.round((asDate(typedValue(anchor)) - asDate(fromSample(anchor.id))) / DAY);
      copied.forEach((f) => {
        if (!isNaN(asDate(rec[f]))) rec[f] = new Date(asDate(rec[f]) + shift * DAY).toISOString().slice(0, 10);
      });
    }
    // What belongs to a chosen record follows it: the loan of car VFE 1290 gets that car's model, not another's.
    // Only fields that are not on the form, so what the form shows (typed or looked up) is never overwritten.
    fields.filter((f) => f.options_from && rec[f.id] != null && rec[f.id] !== "").forEach((f) => {
      const from = typeof f.options_from === "object" ? f.options_from : { list: String(f.options_from).split(".")[0], field: String(f.options_from).split(".")[1] };
      const chosen = (S.data[from.list] || []).find((x) => String(x[from.field]) === String(rec[f.id]));
      if (!chosen) return;
      Object.keys(rec).forEach((g) => {
        if (g === key || g === "status" || g === "timeline" || g === f.id || fields.some((x) => x.id === g) || WHO.test(g) || WHEN.test(g)) return;
        if (chosen[g] != null && chosen[g] !== "" && chosen[g] !== "-") rec[g] = clone(chosen[g]);
      });
    });
    const keyField = fields.find((x) => x.id === key);
    const typedKey = keyField ? typedValue(keyField) : "";
    rec[key] = typedKey !== "" && !list.some((x) => String(x[key]) === String(typedKey)) ? typedKey : nextId(list, key);
    if (status) {
      const byIdNotName = list.some((x) => { const st = findStatus(x.status); return st && same(st.id, x.status) && !same(st.name, x.status); });
      rec.status = byIdNotName ? status.id : status.name;
    } else if (statusName) rec.status = statusName;
    const progress = newProgress(name, role.user || role.name || "");
    if (progress) rec.timeline = progress;
    list.unshift(rec);
    const touched = el.dataset.also ? moveLinked(JSON.parse(el.dataset.also), rec) : {};
    (touched[name] = touched[name] || []).push(String(rec[key]));
    demo.save(touched);
    return rec;
  }

  // ------------------------------------------------------------------ renderers
  function shell(r, body) {
    const role = byId(S.roles, r.role) || { name: r.role };
    const menu = S.screens.filter((s) => s.menu && canSee(s, r.role))
      .map((s) => `<a class="menu-item ${s.id === r.screen ? "active" : ""}" data-el="menu:${esc(s.menu)}" href="#/${s.id}${r.q.clean ? "?clean=1" : ""}">${esc(s.menu)}</a>`).join("");
    return `
      <header class="topbar" data-el="region:header">
        <div class="brand" data-el="region:system name">${brandMark(false)}<span>${esc(P.name)}</span></div>
        <div class="topbar-right">
          <span class="user" data-el="header:user">${role.user ? `${person(role.user)} · ` : ""}${esc(role.name)}</span>
          <a class="logout" href="#/login" data-el="header:logout">${W.logout}</a>
        </div>
      </header>
      <div class="layout">
        <nav class="sidebar" data-el="region:side menu">${menu}</nav>
        <main class="content" id="content" data-el="region:page background">${body}</main>
      </div>`;
  }

  function renderLogin(screen) {
    return `
      <div class="login-wrap" data-el="region:sign-in page">
        <div class="login-card" data-el="section:Login">
          <div class="login-brand">${brandMark(true)}<h1>${esc(P.name)}</h1><p>${esc(P.client)}</p></div>
          <label class="f-label">Username</label><input class="f-input" data-el="field:username" placeholder="Network ID">
          <label class="f-label">Password</label><input class="f-input" type="password" data-el="field:password" placeholder="Password">
          <button class="btn primary block" data-el="button:Login" data-go="${firstScreen(S.roles[0].id)}" data-role="${S.roles[0].id}">${W.login}</button>
          <div class="demo-roles fb-hide"><span>Mock-up: sign in as</span>${S.roles.map((x) => `<button class="btn small" data-role-login="${x.id}">${esc(x.name)}</button>`).join("")}</div>
        </div>
      </div>`;
  }

  function title(screen) {
    return `<div class="page-head" data-el="region:page heading"><h2 data-el="title:${esc(screen.title)}">${esc(screen.title)}</h2>${screen.subtitle ? `<p>${esc(screen.subtitle)}</p>` : ""}</div>`;
  }

  function renderStats(stats, list) {
    if (!stats) return "";
    const base = list ? rows(list) : [];
    const value = (s) => (s.count === undefined ? s.value : s.count === "all" ? base.length : base.filter((r) => matches(s.count, r)).length);
    return `<div class="stats" data-el="region:summary figures">${stats.map((s) => `<div class="stat" data-el="stat:${esc(s.label)}"><div class="stat-value">${esc(value(s))}</div><div class="stat-label">${esc(s.label)}</div></div>`).join("")}</div>`;
  }

  // `shown`: the record of the detail screen a related list is drawn on (see `where_record` in rows()).
  function renderList(list, r, shown) {
    if (!list) return "";
    const data = rows(list, shown);
    const cols = list.columns || [];
    const filters = (list.filters || []).map((f) => {
      const col = cols.find((c) => c.field === f) || { label: String(f).replace(/_/g, " ").replace(/\b\w/g, (ch) => ch.toUpperCase()) };
      const vals = [...new Set(((S.data || {})[list.data] || []).map((x) => x[f]))];
      return `<div class="filter" data-el="filter:${esc(col.label)}"><label>${esc(col.label)}</label><select class="f-input" data-filter="${esc(f)}"><option value="All">All</option>${vals.map((v) => `<option>${esc(v)}</option>`).join("")}</select></div>`;
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
    // A column holds people when any of its values is a person: then every name in it gets its initials.
    const peopleCols = new Set(cols.filter((c) => !c.chip && data.some((row) => PEOPLE.has(String(row[c.field] == null ? "" : row[c.field]).trim().toLowerCase()))).map((c) => c.field));
    const body = data.length ? data.map((row) => `<tr data-row="${watchedValues(row)}" data-el="row:${esc(row[key])}">${cols.map((c) => `<td ${shortClass(String(row[c.field] == null ? "" : row[c.field]))}data-el="cell:${esc(c.label)}|${esc(row[key])}">${c.chip ? `<span class="chip ${statusClass(row[c.field])}">${esc(row[c.field])}</span>` : person(row[c.field], peopleCols.has(c.field))}</td>`).join("")}${(list.actions || []).length ? `<td class="actions" data-el="cell:Action|${esc(row[key])}">${list.actions.filter((a) => matches(a.when, row) && (!a.roles || a.roles.includes(r.role))).map((a) => `<a href="#" class="link" data-el="action:${esc(a.label)}" ${a.to ? `data-go="${a.to}"` : ""} ${a.to || a.set_status != null ? `data-record="${esc(row[key])}"` : ""} ${a.set_status != null ? `${moveAttr(a)} data-list="${esc(list.data)}"` : ""} ${a.toast ? `data-toast="${esc(a.toast)}"` : ""}>${esc(a.label)}</a>`).join(" ")}</td>` : ""}</tr>`).join("")
      : `<tr><td colspan="${cols.length + 1}" class="empty">${esc(list.empty || "No records found")}</td></tr>`;
    // One block for the list: its toolbar row, the table and the count (the desk theme draws it as one card).
    return `<div class="list-block">
      ${search || filters || toolbar ? `<div class="list-tools" data-el="region:area above the list">${search || filters ? `<div class="filters" data-el="region:filters">${search}${filters}<button class="btn small" data-el="button:Search" data-apply-filters>Search</button><button class="btn small" data-el="button:Clear Filters" data-clear-filters>${W.clear}</button></div>` : "<div></div>"}<div class="toolbar" data-el="region:list buttons">${toolbar}</div></div>` : ""}
      <div class="table-wrap" data-el="region:list"><table class="datalist ${cols.length > 9 ? "dense" : ""}">
        <thead><tr>${cols.map((c) => `<th data-el="column:${esc(c.label)}">${esc(c.label)}</th>`).join("")}${(list.actions || []).length ? `<th>${W.action}</th>` : ""}</tr></thead>
        <tbody>${body}${data.length ? `<tr class="none-match" hidden><td colspan="${cols.length + 1}" class="empty">${esc(list.empty || "No records found")}</td></tr>` : ""}</tbody>
      </table></div>
      <div class="pager" data-el="region:record count" data-total="${data.length}">${W.showing(data.length, data.length)}</div></div>`;
  }

  function field(f, value, readonly) {
    const ro = readonly || f.readonly;
    const v = value != null && value !== "" ? value : f.default != null ? f.default : "";
    const req = f.required && !ro ? '<span class="req">*</span>' : "";
    let input;
    if (ro && !["signature", "file"].includes(f.type)) {
      const tick = f.type === "checkbox" && !options(f).length && typeof v === "boolean" ? (v ? "Yes" : "No") : v;
      input = `<div class="f-value">${esc(tick) || "-"}</div>`;
    } else switch (f.type) {
      case "textarea": input = `<textarea class="f-input" rows="3" placeholder="${esc(f.placeholder || "")}">${esc(v)}</textarea>`; break;
      // A value the choices no longer offer (a filtered options_from) is still shown on a record that holds it.
      case "select": {
        const opts = options(f);
        const all = v !== "" && !opts.map(String).includes(String(v)) ? [v, ...opts] : opts;
        input = `<select class="f-input"><option value="">${W.select}</option>${all.map((o) => `<option ${String(o) === String(v) ? "selected" : ""}>${esc(o)}</option>`).join("")}</select>`;
        break;
      }
      case "radio": input = `<div class="choices">${options(f).map((o) => `<label><input type="radio" name="${f.id}" ${String(o) === String(v) ? "checked" : ""}> ${esc(o)}</label>`).join("")}</div>`; break;
      // Without options a checkbox is one tick box (I agree, Urgent), ticked when the record's value is.
      case "checkbox": input = options(f).length ? `<div class="choices">${options(f).map((o) => `<label><input type="checkbox"> ${esc(o)}</label>`).join("")}</div>`
        : `<div class="choices"><label class="tick"><input type="checkbox" ${v === true || /^(true|yes|y|1)$/i.test(String(v)) ? "checked" : ""}></label></div>`; break;
      case "date": input = `<input class="f-input" type="date" value="${esc(v)}">`; break;
      case "datetime": input = `<input class="f-input" type="datetime-local" value="${esc(v)}">`; break;
      case "number": input = `<input class="f-input" type="number" value="${esc(v)}">`; break;
      // A file field and a signature field answer a click: a sample file is attached, the signed-in person signs.
      case "file": input = ro ? `<div class="f-value">${esc(v) || "-"}</div>` : `<div class="file-drop" data-fake="file"><input type="hidden"><span class="fake-view">Drop file here or <span class="link">browse</span></span></div>`; break;
      case "signature": input = ro ? `<div class="signature">${v ? `<span class="sig-ink">${esc(v)}</span>` : "Sign here"}</div>` : `<div class="signature" data-fake="signature"><input type="hidden"><span class="fake-view">Sign here</span></div>`; break;
      // A user field offers people: those of its `roles` (each role's `user`), or, without roles, everyone the
      // spec names (the roles' users and a `users` list in the data); `options` or `options_from` win.
      case "user": {
        const people = options(f).length ? options(f) : peopleFor(f);
        const all = v !== "" && !people.map(String).includes(String(v)) ? [v, ...people] : people;
        input = `<select class="f-input"><option value="">${W.selectUser}</option>${all.map((o) => `<option ${String(o) === String(v) ? "selected" : ""}>${esc(o)}</option>`).join("")}</select>`;
        break;
      }
      default: input = `<input class="f-input" value="${esc(v)}" placeholder="${esc(f.placeholder || "")}">`;
    }
    return `<div class="f-row ${f.type === "textarea" ? "wide" : ""}" data-el="field:${esc(f.id)}" ${f.required && !ro ? "data-required" : ""}><label class="f-label">${esc(f.label)}${req}</label><div class="f-control">${input}${f.help && !ro ? `<div class="f-help">${esc(f.help)}</div>` : ""}</div></div>`;
  }

  // The steps of a form (sections with a `page`), as [{page, label}].
  function stepsOf(all) {
    return [...new Set(all.map((s) => s.page || 1))].map((p) => ({ page: p, label: (all.find((s) => (s.page || 1) === p) || {}).page_title || `${W.step} ${p}` }));
  }
  function sections(screen, rec, readonly, page) {
    const all = screen.sections || [];
    const steps = stepsOf(all);
    const current = Number(page || (steps[0] || {}).page);
    // A step that still holds required fields left empty, once the main button has pointed them out, says so.
    const missing = typed.required === "page" ? typed.missingPages || [] : [];
    const tabs = steps.length > 1 ? `<div class="tabs" data-el="region:form steps">${steps.map(({ page: p, label }) =>
      `<a href="#" class="tab ${p === current ? "active" : ""} ${p !== current && missing.includes(p) ? "missing" : ""}" data-page="${p}" data-el="tab:${esc(label)}">${esc(label)}</a>`).join("")}</div>` : "";
    const body = all.filter((s) => (s.page || 1) === current).map((s) => `
      <section class="form-section" data-el="section:${esc(s.title)}">
        <h3>${esc(s.title)}</h3>
        ${s.note ? `<p class="note">${esc(s.note)}</p>` : ""}
        <div class="f-grid">${(s.fields || []).map((f) => field(f, rec[f.id], readonly)).join("")}</div>
      </section>`).join("");
    return tabs + body;
  }

  // The tier of a button in the desk theme. Reject, Decline, Return and Send back are normal choices: never
  // red words on the screen, and the main action (not solid red) in their dialog.
  const NORMAL_CHOICE = /^(confirm\s+)?(reject|decline|return|send back|refuse|not approve|disapprove)/i;
  // `attrs` is extra HTML attributes: a dialog's confirm button gets data-close, so it always closes it.
  // `dialog`: the id of the dialog whose confirm button this is (it may add a record when opened on a new form).
  function button(b, r, rec, attrs, dialog) {
    if (b.roles && !b.roles.includes(r.role)) return "";
    if (b.when && !matches(b.when, rec || {})) return "";
    const creates = b.dialog ? "" : createAttr(creatingEntry(r, b.label, dialog));
    const choice = b.style === "danger" && NORMAL_CHOICE.test(String(b.label).trim()) ? " normal-choice" : "";
    return `<button class="btn ${b.style || ""}${choice} ${b.example ? "fb-hide" : ""}" data-el="button:${esc(b.label)}" ${b.to ? `data-go="${b.to}"` : ""} ${b.toast ? `data-toast="${esc(b.toast)}"` : ""} ${b.dialog ? `data-dialog="${b.dialog}"` : ""} ${moveAttr(b)}${creates} ${attrs || ""}>${esc(b.label)}</button>`;
  }
  const buttons = (list, r, rec) => (list && list.length ? `<div class="form-buttons" data-el="region:buttons">${list.map((b) => button(b, r, rec)).join("")}</div>` : "");
  // A form in steps: its main button (style primary) only on the last step, Next in its place on the others,
  // and Previous from the second step on. The other buttons (Cancel, Save as Draft) are on every step.
  function stepButtons(screen, r, rec) {
    const steps = stepsOf(screen.sections || []);
    const list = screen.buttons || [];
    if (steps.length < 2) return buttons(list, r, rec);
    const at = Math.max(0, steps.findIndex((s) => s.page === Number(r.q.page || steps[0].page)));
    const last = at === steps.length - 1;
    const prev = at > 0 ? `<button class="btn" data-el="button:Previous" data-page="${steps[at - 1].page}">Previous</button>` : "";
    const next = last ? "" : `<button class="btn primary" data-el="button:Next" data-page="${steps[at + 1].page}">Next</button>`;
    const main = list.findIndex((b) => b.style === "primary");
    let html = list.map((b, i) => {
      if (b.style === "primary" && !last) return i === main ? prev + next : "";
      return (i === main ? prev : "") + button(b, r, rec);
    }).join("");
    if (main < 0) html += prev + next;
    return html ? `<div class="form-buttons" data-el="region:buttons">${html}</div>` : "";
  }

  // Approval progress. A step still to come that the spec gives no word for reads "Waiting"; the spec's own
  // word (Pending, Not required) is kept.
  function renderTimeline(steps) {
    if (!steps) return "";
    const comments = steps.some((s) => s.comment);
    const word = (s) => (s.status != null && s.status !== "" ? s.status : s.at ? "Done" : W.waiting);
    return `<section class="form-section" data-el="section:Approval Progress"><h3>${W.progress}</h3><table class="datalist compact"><thead><tr><th>${W.step}</th><th>${W.by}</th><th>${W.at}</th><th>Status</th>${comments ? `<th>${W.comment}</th>` : ""}</tr></thead><tbody>${steps.map((s) => {
      const cell = (head) => `data-el="cell:${head}|${esc(s.step)}"`;
      return `<tr data-el="row:${esc(s.step)}"><td ${cell("Step")}>${esc(s.step)}</td><td ${cell("Handled By")}>${s.by ? person(s.by) : "-"}</td><td ${cell("Date & Time")}>${esc(s.at) || "-"}</td><td ${cell("Status")}><span class="chip ${statusClass(word(s))}">${esc(word(s))}</span></td>${comments ? `<td ${cell("Comment")}>${esc(s.comment) || "-"}</td>` : ""}</tr>`;
    }).join("")}</tbody></table></section>`;
  }

  // A list on a detail screen of the records that name the one shown (a car's loans), under its own heading.
  function relatedList(list, r, rec) {
    if (!list) return "";
    const heading = list.title || "Related records";
    return `<section class="related-list" data-el="section:${esc(heading)}"><h3>${esc(heading)}</h3>${renderList(list, r, rec)}</section>`;
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
        // On a record, its buttons follow it (`when`) as a detail screen's do; an empty form has no record to match.
        const rec = formOnRecord(screen, r.q) ? record(screen, r.q) : null;
        return title(screen) + sections(screen, rec || {}, false, r.q.page) + stepButtons(screen, r, rec || undefined);
      }
      case "detail": {
        const rec = record(screen, r.q);
        const src = screen.fields_from ? byId(S.screens, screen.fields_from) : screen;
        const status = rec.status ? `<div class="status-bar" data-el="region:status">${W.status} <span class="chip ${statusClass(rec.status)}">${esc(rec.status)}</span></div>` : "";
        const notice = rec.notice ? `<div class="notice" data-el="section:Notice">${esc(rec.notice)}</div>` : "";
        return title(screen) + status + notice + renderTimeline(rec.timeline || screen.timeline) + sections({ sections: (screen.sections || src.sections || []) }, rec, true, r.q.page)
          + relatedList(screen.list, r, rec) + buttons(screen.buttons, r, rec);
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
    return `<div class="modal-back"><div class="modal" role="dialog" aria-modal="true" aria-label="${esc(d.title)}" data-el="dialog:${esc(d.title)}">
      <div class="modal-head">${esc(d.title)}<a href="#" class="modal-x" data-close>&times;</a></div>
      <div class="modal-body">${d.message ? `<p>${esc(d.message)}</p>` : ""}${(d.fields || []).map((f) => field(f, "", false)).join("")}${d.list ? renderList(d.list, route()) : ""}</div>
      <div class="modal-foot"><button class="btn" data-close>Cancel</button>${button(d.confirm || { label: "OK" }, route(), null, "data-close", d.id)}</div>
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
    if (pager) pager.textContent = W.showing(shown, pager.dataset.total);
    if (demo.base) custom.draw();  // rows came and went: the tags follow
  }
  const listScope = (el) => el.closest(".modal-body") || document.getElementById("content");

  // ------------------------------------------------------------------ what was typed
  // The page is drawn again on every move (another step of a form, a dialog opening or closing). What the
  // presenter typed or picked is kept while they stay on the same screen and record, and put back after the
  // redraw. Moving to another screen starts clean, as a new form would. The filters and search boxes of a
  // list are kept for the whole visit: opening a record and coming back finds the list as it was left.
  const typed = { key: null, values: {}, required: null, warned: null };
  const listInputs = {};  // {screen|record|role: {filter or search box: its values}}
  const TYPED = "[data-el^='field:'], [data-el^='filter:'], [data-el^='search:']";
  const typedId = (holder) => (holder.closest(".modal") ? "dialog " : "") + holder.dataset.el;
  const controls = (holder) => [...holder.querySelectorAll("input, textarea, select")];
  const store = (holder) => (!holder.closest(".modal") && /^(filter|search):/.test(holder.dataset.el)
    ? (listInputs[typed.key] = listInputs[typed.key] || {}) : typed.values);
  function rememberTyped() {
    if (!typed.key) return;
    document.querySelectorAll("#app " + TYPED.split(", ").join(", #app ")).forEach((holder) => {
      const found = controls(holder);
      if (found.length) store(holder)[typedId(holder)] = found.map((c) => (c.type === "checkbox" || c.type === "radio" ? c.checked : c.value));
    });
  }
  function restoreTyped() {
    document.querySelectorAll("#app " + TYPED.split(", ").join(", #app ")).forEach((holder) => {
      const saved = store(holder)[typedId(holder)];
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

  // ------------------------------------------------------------------ file and signature fields
  // Each keeps what it holds in a hidden input, so it survives a redraw like anything typed.
  function syncFakes() {
    app.querySelectorAll("[data-fake]").forEach((box) => {
      const value = box.querySelector("input[type=hidden]").value;
      box.querySelector(".fake-view").innerHTML = box.dataset.fake === "file"
        ? (value ? `<span class="file-name">${esc(value)}</span> <a href="#" class="link" data-fake-clear>Remove</a>` : 'Drop file here or <span class="link">browse</span>')
        : (value ? `<span class="sig-ink">${esc(value)}</span>` : "Sign here");
    });
  }

  // ------------------------------------------------------------------ required fields
  // The main button of a form, and a dialog's confirm button, first point out the required fields left
  // empty. A presenter is not made to fill in a whole form: pressing the button again goes on without them.
  const noValue = (values) => !values.some((v) => (typeof v === "boolean" ? v : String(v).trim() !== ""));
  const holderEmpty = (holder) => {
    const found = controls(holder);
    return found.length > 0 && noValue(found.map((c) => (c.type === "checkbox" || c.type === "radio" ? c.checked : c.value)));
  };
  function markRequired() {
    const scope = typed.required === "dialog" ? app.querySelector(".modal") : document.getElementById("content");
    if (!scope) return;
    scope.querySelectorAll("[data-required]").forEach((holder) => {
      const bad = holderEmpty(holder);
      holder.classList.toggle("invalid", bad);
      const note = holder.querySelector(".f-error");
      if (bad && !note) holder.querySelector(".f-control").insertAdjacentHTML("beforeend", '<div class="f-error">This field is required</div>');
      if (!bad && note) note.remove();
    });
  }
  // The required fields still empty, as [{page, id}]: those on screen, and those on the other steps of a form.
  function missingRequired(el, r) {
    if (el.closest(".modal")) return [...app.querySelectorAll(".modal [data-required]")].filter(holderEmpty).map((h) => ({ id: h.dataset.el }));
    const screen = byId(S.screens, r.screen) || {};
    const rec = formOnRecord(screen, r.q) ? record(screen, r.q) : {};
    const all = screen.sections || [];
    const current = Number(r.q.page || (all[0] || {}).page || 1);
    const missing = [];
    all.forEach((s) => (s.fields || []).forEach((f) => {
      if (!f.required || f.readonly) return;
      const page = s.page || 1;
      const holder = page === current ? document.querySelector(`#content [data-el="${CSS.escape("field:" + f.id)}"]`) : null;
      const saved = typed.values["field:" + f.id];
      const given = rec[f.id] != null && rec[f.id] !== "" ? rec[f.id] : f.default != null ? f.default : "";
      if (holder ? holderEmpty(holder) : saved ? noValue(saved) : String(given).trim() === "") missing.push({ page, id: f.id });
    }));
    return missing;
  }
  // May this button go ahead? False the first time required fields are empty: they are then marked.
  function passRequired(el, r) {
    const inDialog = !!el.closest(".modal");
    const checks = inDialog ? !!el.closest(".modal-foot") && !!el.dataset.el
      : (byId(S.screens, r.screen) || {}).type === "form" && el.classList.contains("primary") && !el.dataset.dialog && el.dataset.page === undefined && !!el.closest(".form-buttons");
    if (!checks) return true;
    const missing = missingRequired(el, r);
    const label = el.textContent.trim();
    if (!missing.length || typed.warned === label) {
      // Going on with required fields still empty is the mock-up's allowance, not the system's: say so, so
      // nobody in the room takes it for the real behaviour.
      if (missing.length) toast(`Only the mock-up goes on with ${missing.length === 1 ? "a required field" : "required fields"} empty: the real system will not ${inDialog ? "accept it" : "send the form"} until ${missing.length === 1 ? "it is" : "they are"} filled in.`, "warn");
      Object.assign(typed, { required: null, warned: null });
      return true;
    }
    // On a form in steps the main button is on the last step: it stays there, and the steps that hold the
    // empty fields are named and marked, so the presenter can go back to them or press again.
    const pages = [...new Set(missing.map((m) => m.page).filter((p) => p != null))];
    Object.assign(typed, { required: inDialog ? "dialog" : "page", warned: label, missingPages: pages });
    const one = missing.length === 1;
    const current = Number(r.q.page || ((byId(S.screens, r.screen) || {}).sections || [{}])[0].page || 1);
    const steps = inDialog ? [] : stepsOf((byId(S.screens, r.screen) || {}).sections || []);
    const elsewhere = steps.length > 1 ? steps.filter((s) => pages.includes(s.page) && s.page !== current).map((s) => s.label) : [];
    const where = elsewhere.length ? `, on ${elsewhere.join(" and ")}` : "";
    toast(`${one ? "A required field is" : missing.length + " required fields are"} empty${where}. Mock-up: press ${label} again to go on without ${one ? "it" : "them"}.`, "warn");
    if (elsewhere.length) render();  // the steps that hold them are marked
    else markRequired();
    return false;
  }

  // ------------------------------------------------------------------ main render
  function render() {
    const r = route();
    rememberTyped();  // the page still shows the previous view here
    const nowOn = `${r.screen}|${r.q.record || ""}|${r.role || ""}`;
    const elsewhere = nowOn !== typed.key;
    if (elsewhere) Object.assign(typed, { key: nowOn, values: {}, required: null, warned: null });
    if (!r.q.dialog && typed.required === "dialog") Object.assign(typed, { required: null, warned: null });
    document.body.classList.toggle("clean", !!r.q.clean);
    if (r.screen === "__flow") {
      app.innerHTML = renderFlow();
      app.dataset.screen = "__flow";
      runHooks({ screen: "__flow", role: r.role, q: r.q, root: app });
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
    fitLists();
    restoreTyped();
    syncFakes();
    if (typed.required) markRequired();
    syncTools(r, screen);
    // At most one primary button per screen in the desk theme: the first is the screen's main action, the
    // others take the secondary tier (the main button of a form keeps what it does: only its look changes).
    if (DESK) [document.getElementById("content"), app.querySelector(".modal")].forEach((scope) => {
      if (scope) [...scope.querySelectorAll(".btn.primary")].slice(1).forEach((b) => b.classList.add("tier-secondary"));
    });
    if (elsewhere) window.scrollTo(0, 0);  // a new screen starts at its top
    // A dialog takes the cursor: its first field, or its confirm button. Not in a screenshot, which would show it.
    const modal = r.q.dialog && !r.q.clean ? app.querySelector(".modal") : null;
    const first = modal && (modal.querySelector(".modal-body input:not([type=hidden]), .modal-body textarea, .modal-body select") || modal.querySelector(".modal-foot .btn:last-child"));
    if (first) first.focus();
    runHooks({ screen: app.dataset.screen, role: r.role, q: r.q, root: app });
    feedback.renderPins();
    custom.draw();
  }

  // Messages stack above one another, and a longer one stays longer. `kind`: nothing for something done,
  // "warn" for something to look at, true or "error" for something that went wrong.
  function toast(msg, kind) {
    const error = kind === true || kind === "error";
    let box = document.getElementById("toasts");
    if (!box) {
      box = document.createElement("div");
      box.id = "toasts";
      box.setAttribute("role", "status");
      box.setAttribute("aria-live", "polite");
      document.body.appendChild(box);
    }
    const t = document.createElement("div");
    t.className = error ? "toast error" : kind === "warn" ? "toast warn" : "toast";
    t.textContent = msg;
    box.appendChild(t);
    setTimeout(() => t.remove(), error ? 9000 : Math.min(8000, 2600 + String(msg).length * 35));
  }

  document.addEventListener("click", (e) => {
    if (feedback.active) return; // feedback mode handles clicks itself
    if (e.target.classList.contains("modal-back")) return closeDialog();  // a click outside the dialog
    const fake = e.target.closest("[data-fake]");
    if (fake) {  // attach a sample file or remove it; sign as whoever is signed in, or clear the signature
      e.preventDefault();
      const input = fake.querySelector("input[type=hidden]");
      const role = byId(S.roles, route().role) || {};
      const clear = e.target.closest("[data-fake-clear]") || (fake.dataset.fake === "signature" && input.value);
      input.value = clear ? "" : fake.dataset.fake === "file" ? "sample-document.pdf" : role.user || role.name || "Signed";
      syncFakes();
      if (typed.required) markRequired();
      return;
    }
    const el = e.target.closest("[data-go],[data-toast],[data-dialog],[data-close],[data-page],[data-role-login],[data-apply-filters],[data-clear-filters],[data-status],[data-status-by],[data-create]");
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
    if (!passRequired(el, r)) return;
    // A button that opens a dialog moves nothing itself: the dialog's confirm button does. On a new form the
    // main button adds a record instead, in the status the button names.
    const made = el.dataset.create !== undefined && !el.dataset.dialog ? createRecord(el, r) : null;
    const moved = !made && (el.dataset.status !== undefined || el.dataset.statusBy !== undefined) && !el.dataset.dialog && moveStatus(el, r);
    const acted = made || moved;
    // "{id}" in a message is the id of the record the button added or moved.
    if (el.dataset.toast) toast(el.dataset.toast.replace(/\{id\}/g, acted ? String(acted[Object.keys(acted)[0]]) : ""));
    if (made) typed.key = null;  // what was typed went into the record: drawn again, the form starts empty
    const before = location.hash;
    if (el.dataset.page) go(r.screen, { ...stay(r.q), page: el.dataset.page });
    else if (el.dataset.dialog) go(r.screen, { ...stay(r.q), dialog: el.dataset.dialog }, true);
    // A dialog's confirm button has both: it goes where it says, and only closes when it goes nowhere.
    else if (el.dataset.go) go(el.dataset.go, el.dataset.record ? { record: el.dataset.record } : {}, !!r.q.dialog);
    else if (el.dataset.close !== undefined) closeDialog();
    if (acted && location.hash === before) render();  // it stayed on the page: show the record as it is now
  });
  document.addEventListener("input", () => { if (typed.required) markRequired(); });
  document.addEventListener("change", (e) => {
    if (typed.required) markRequired();
    if (e.target.classList.contains("role-switch")) {
      sessionStorage.setItem("mock-role", e.target.value);
      const before = location.hash;
      go(firstScreen(e.target.value));
      // Two roles may start on the same screen: the address is then the same, and only a redraw shows the new role.
      if (location.hash === before) render();
    }
  });

  // Which build of the mock-up this page shows, and whether an assistant is listening for comments (a live session).
  const live = { stamp: null, listening: false };

  // ------------------------------------------------------------------ feedback
  // What a comment is about, in words a client reads: "the Status column", not "column:Status".
  function nameOf(element) {
    if (!element) return "this screen";
    const [kind, ...rest] = String(element).split(":");
    const name = rest.join(":");
    if (kind === "field") {
      const fields = [...S.screens.flatMap((s) => (s.sections || []).flatMap((x) => x.fields || [])), ...(S.dialogs || []).flatMap((d) => d.fields || [])];
      return `the ${(fields.find((f) => f.id === name) || {}).label || name} field`;
    }
    if (kind === "title") return "the page title";
    if (kind === "header") return name === "user" ? "the signed-in user" : "the Logout link";
    if (kind === "region") return `the ${name}`;
    if (kind === "row") return `the row ${name}`;
    if (kind === "cell") {
      const [column, ...row] = name.split("|");
      return `the ${column} cell of ${row.join("|")}`;
    }
    const what = { column: "column", button: "button", action: "action", menu: "menu item", stat: "figure", section: "section", filter: "filter", search: "search box", tab: "tab", dialog: "dialog" }[kind];
    return what ? `the ${name} ${what}` : name || "this screen";
  }
  const capital = (text) => text.charAt(0).toUpperCase() + text.slice(1);
  // "6 Nov, 17:37", or nothing for a comment that carries no time.
  function when(c) {
    const d = new Date(c.time || c.received || "");
    return isNaN(d) ? "" : `${d.getDate()} ${["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"][d.getMonth()]}, ${two(d.getHours())}:${two(d.getMinutes())}`;
  }
  const feedback = {
    active: false,
    items: [],
    remote: location.protocol.startsWith("http"),
    key: `mock-feedback:${P.name}`,
    // Comments the server did not take (it was closed, or the network dropped). They stay in this browser,
    // also across a reload, and are sent again with the next comment, on the next load or with "Try again".
    unsent: [],
    unsentKey: `mock-feedback-unsent:${P.name}`,
    // The comments this browser wrote (their ids), and the private mark it saves them with: with it the server
    // lets this browser edit or delete them. The presenter, on the machine running the server, may change any.
    mineKey: `mock-feedback-mine:${P.name}`,
    presenter: false,
    owner() {
      let id = "";
      try {
        id = localStorage.getItem("mock-owner") || "";
        if (!id) {
          id = Array.from({ length: 4 }, () => Math.random().toString(36).slice(2, 10)).join("");
          localStorage.setItem("mock-owner", id);
        }
      } catch (e) { /* storage switched off: comments can still be saved, and the presenter can change them */ }
      return id;
    },
    mine(c) { return !!c.id && this.stored(this.mineKey).includes(c.id); },
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
        let saved;
        try {
          const res = await fetch("api/feedback", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(this.unsent[0]) });
          if (!res.ok) throw new Error(res.status);
          saved = await res.json();
        } catch (e) { break; }
        // The comment as the server saved it carries its number (FB-007): show that from now on.
        const at = this.items.indexOf(this.unsent[0]);
        if (at >= 0 && saved && saved.id) this.items[at] = saved;
        if (saved && saved.id) this.store(this.mineKey, [...this.stored(this.mineKey), saved.id].slice(-500));
        this.unsent.shift();
        this.store(this.unsentKey, this.unsent);
      }
      return !this.unsent.length;
    },
    // The number shown on a pin and in the panel: the one the server gave the comment (FB-007 is 7), so
    // everyone in the room sees the same number for the same comment. Not yet saved: a dot.
    number(c) {
      if (c.id) return String(parseInt(String(c.id).replace(/\D/g, ""), 10) || c.id);
      return this.remote ? "\u2022" : String(this.items.indexOf(c) + 1);
    },
    // Comments other people saved since this page was loaded: asked for every few seconds while presenting.
    async sync() {
      if (!this.remote || document.body.classList.contains("clean")) return;
      let list;
      try {
        const res = await fetch("api/feedback");
        if (!res.ok) return;
        list = await res.json();
      } catch (e) { return; }
      const mark = (items) => items.map((c) => `${c.id || ""}:${c.state || ""}:${c.text}`).join(",");
      const before = mark(this.items);
      this.items = list.concat(this.unsent);
      if (mark(this.items) !== before) this.refresh();
    },
    async save(item) {
      item.owner = this.owner();
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
      btn.textContent = (this.active ? "Feedback on · click anything" : "Feedback") + (n ? ` · ${n} not saved` : "");
      btn.classList.toggle("fb-unsent", !!n);
      this.renderPanel();  // first: an open panel makes room beside the page, which moves the pins and tags
      this.renderPins();
      custom.draw();
    },
    toggle() {
      this.active = !this.active;
      document.body.classList.toggle("fb-active", this.active);
      this.refresh();
    },
    forScreen() {
      const screen = app.dataset.screen;
      return this.items.filter((c) => c.screen === screen && !c.withdrawn);
    },
    // May this browser change the comment, and if not now, why not ("" when it may).
    changeable(c) {
      if (this.unsent.includes(c) || !this.remote) return { may: true, why: "" };
      if (!this.presenter && !this.mine(c)) return { may: false, why: "" };
      if (c.state === "working") return { may: false, why: "Being worked on, so it can no longer be changed. Add a new comment instead." };
      if (c.state && c.state !== "received") return { may: false, why: "Already dealt with, so it can no longer be changed. Add a new comment instead." };
      return { may: true, why: "" };
    },
    async edit(c) {
      const text = await this.openBox({ title: `Edit the comment on ${nameOf(c.element)}`, text: c.text, save: "Save changes" });
      if (text == null || text === c.text) return;
      if (!text) return this.remove(c);
      if (this.unsent.includes(c) || !this.remote) {
        if (!this.unsent.includes(c)) (c.history = c.history || []).push({ text: c.text, until: new Date().toISOString() }), c.edited = new Date().toISOString();
        c.text = text;
        this.store(this.unsent.includes(c) ? this.unsentKey : this.key, this.unsent.includes(c) ? this.unsent : this.items);
        return this.refresh();
      }
      const answer = await this.ask("edit", { id: c.id, text, owner: this.owner() });
      if (answer.ok) Object.assign(c, answer.body);
      else toast(answer.body.error || "Not changed: the mock-up server is not answering.", "warn");
      this.refresh();
      if (!answer.ok) this.sync();
    },
    async remove(c) {
      if (!(await ask("Remove this comment?", `"${String(c.text).slice(0, 140)}"${String(c.text).length > 140 ? "…" : ""}`, "Remove"))) return;
      if (this.unsent.includes(c)) {
        this.unsent = this.unsent.filter((x) => x !== c);
        this.items = this.items.filter((x) => x !== c);
        this.store(this.unsentKey, this.unsent);
        return this.refresh();
      }
      if (!this.remote) {  // kept, marked as taken back: an export still shows it was there
        c.withdrawn = new Date().toISOString();
        this.store(this.key, this.items);
        return this.refresh();
      }
      const answer = await this.ask("withdraw", { id: c.id, owner: this.owner(), by: localStorage.getItem("mock-author") || "" });
      if (answer.ok || answer.status === 404) this.items = this.items.filter((x) => x !== c);
      else toast(answer.body.error || "Not removed: the mock-up server is not answering.", "warn");
      this.refresh();
      if (!answer.ok) this.sync();
    },
    async ask(action, body) {
      try {
        const res = await fetch(`api/feedback/${action}`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
        return { ok: res.ok, status: res.status, body: await res.json().catch(() => ({})) };
      } catch (e) { return { ok: false, status: 0, body: {} }; }
    },
    renderPins() {
      document.querySelectorAll(".fb-pin").forEach((p) => p.remove());
      if (document.body.classList.contains("clean")) return;
      const onSame = {};  // several comments on one thing: their pins sit side by side, not on top of each other
      this.forScreen().forEach((c, i) => {
        const target = c.element ? document.querySelector(`[data-el="${CSS.escape(c.element)}"]`) : null;
        const pin = document.createElement("div");
        pin.onclick = () => {  // show the comment this pin stands for
          if (!this.active) this.toggle();
          const row = document.querySelector(`#fb-panel [data-fb="${i}"]`);
          if (!row) return;
          row.scrollIntoView({ block: "nearest" });
          row.classList.remove("flash");
          void row.offsetWidth;  // lets the highlight play again on a second click
          row.classList.add("flash");
        };
        const unsent = this.unsent.includes(c);
        pin.className = unsent ? "fb-pin unsent" : "fb-pin";
        pin.textContent = this.number(c);
        pin.title = (unsent ? "NOT SAVED YET: " : "") + c.text;
        const rect = target ? target.getBoundingClientRect() : { right: c.x, top: c.y };
        const place = target ? c.element : `${c.x},${c.y}`;
        onSame[place] = (onSame[place] || 0) + 1;
        pin.style.left = `${rect.right + window.scrollX - 12 - (onSame[place] - 1) * 18}px`;
        pin.style.top = `${rect.top + window.scrollY - 8}px`;
        document.body.appendChild(pin);
      });
    },
    renderPanel() {
      const panel = document.getElementById("fb-panel");
      // While the panel is open the page makes room for it on a wide screen, so it never covers the last columns.
      document.body.classList.toggle("fb-panel-open", this.active);
      if (!this.active) { panel.hidden = true; return; }
      panel.hidden = false;
      const list = this.forScreen();
      const about = (c) => [c.author, (byId(S.roles, c.role) || {}).name || c.role, when(c)].filter(Boolean).join(" · ");
      // What became of a comment, in a word the client may read. "Received" only while an assistant is listening.
      const words = { received: "Received", working: "Working on it", applied: "Applied", noted: "Noted for follow-up" };
      const state = (c) => (words[c.state] && (c.state !== "received" || live.listening) ? `<div class="fb-st ${c.state}">${words[c.state]}</div>` : "");
      // Edit and Delete for a comment this browser may change while it waits; once it is taken, why not.
      const LOCK = '<svg viewBox="0 0 24 24" width="13" height="13" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><rect x="4" y="11" width="16" height="10" rx="2"/><path d="M8 11V7a4 4 0 0 1 8 0v4"/></svg>';
      const actions = (c, i) => {
        const can = this.changeable(c);
        if (can.may) return `<div class="fb-acts"><button class="fb-act" data-fb-edit="${i}">Edit</button><button class="fb-act destroy" data-fb-remove="${i}">Delete</button></div>`;
        return can.why ? `<div class="fb-locked" title="${esc(can.why)}">${LOCK}<span>${esc(can.why)}</span></div>` : "";
      };
      panel.innerHTML = `<div class="fb-panel-head">Feedback on this screen <span class="fb-count">${list.length}</span></div>
        ${list.map((c, i) => `<div class="fb-item" data-fb="${i}"><span class="fb-num${this.unsent.includes(c) ? " unsent" : ""}">${esc(this.number(c))}</span><div class="fb-body"><div class="fb-el">${esc(capital(nameOf(c.element)))}</div><div class="fb-text">${esc(c.text)}</div><div class="fb-meta">${esc(about(c))}${c.edited ? " · edited" : ""}</div>${state(c)}${actions(c, i)}</div></div>`).join("") || '<p class="fb-empty">No feedback yet. Click anything on the screen to comment on it.</p>'}
        ${!this.remote ? `<button class="fb-btn quiet" id="fb-export">Export feedback (${this.items.filter((c) => !c.withdrawn).length})</button>`
          : !this.unsent.length ? `<p class="fb-state ok">Saved to the project folder.</p>`
          : `<div class="fb-warn"><b>${this.unsent.length} comment${this.unsent.length > 1 ? "s" : ""} not saved to the project yet.</b> The mock-up server is not answering. Check that the window that started the mock-up is still open, then try again. The comments are kept in this browser until then.</div>
             <div class="fb-warn-buttons"><button class="fb-btn solid" id="fb-retry">Try again</button><button class="fb-btn quiet" id="fb-export">Export unsaved (${this.unsent.length})</button></div>`}`;
      panel.onclick = (e) => {
        const ed = e.target.closest("[data-fb-edit]"), rm = e.target.closest("[data-fb-remove]");
        if (ed) this.edit(list[Number(ed.dataset.fbEdit)]);
        if (rm) this.remove(list[Number(rm.dataset.fbRemove)]);
      };
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
      if (!this.active || e.target.closest(".fb-tools,.fb-dialog,.fb-pin,.cw-tag")) return;
      e.preventDefault();
      e.stopPropagation();
      const target = e.target.closest("[data-el]");
      const element = target ? target.dataset.el : "";
      const r = route();
      this.openBox({ title: `Comment on ${nameOf(element)}`, author: true, target }).then((text) => {
        if (!text) return;
        this.save({ screen: app.dataset.screen, role: r.role || "", element, text, author: localStorage.getItem("mock-author") || "", x: e.pageX, y: e.pageY,
          time: new Date().toISOString(), version: P.version, ...(live.stamp ? { build: live.stamp } : {}) });  // the build it was made on, when changes are made during the session
      });
    },
    // The comment box: a new comment (with the writer's name), or an earlier one to edit. Resolves to the text,
    // or null when it was closed without saving.
    openBox({ title, text, author, target, save }) {
      return new Promise((done) => {
        const box = document.createElement("div");
        box.className = "fb-dialog";
        box.innerHTML = `<div class="fb-dialog-inner" role="dialog" aria-modal="true" aria-labelledby="fb-title"><div class="fb-title" id="fb-title">${esc(title)}</div>
          <label class="fb-label" for="fb-text">What should change?</label>
          <textarea class="fb-field" id="fb-text" rows="4">${esc(text || "")}</textarea>
          ${author ? `<label class="fb-label" for="fb-author">Your name <span>(optional)</span></label>
          <input class="fb-field" id="fb-author" value="${esc(localStorage.getItem("mock-author") || "")}">` : ""}
          <div class="fb-actions"><span class="fb-hint">Ctrl + Enter saves</span><button class="fb-btn quiet" id="fb-cancel">Cancel</button><button class="fb-btn solid" id="fb-save">${esc(save || "Save comment")}</button></div></div>`;
        document.body.appendChild(box);
        if (target) target.classList.add("fb-target");  // what the comment is about stays marked while it is typed
        const close = (value) => {
          if (target) target.classList.remove("fb-target");
          box.remove();
          this.closeBox = null;
          done(value);
        };
        this.closeBox = () => close(null);
        const field = box.querySelector("#fb-text");
        field.focus();
        field.setSelectionRange(field.value.length, field.value.length);
        box.onclick = (click) => { if (click.target === box) close(null); };  // a click outside the box
        box.onkeydown = (key) => { if (key.key === "Enter" && (key.ctrlKey || key.metaKey)) box.querySelector("#fb-save").click(); };
        box.querySelector("#fb-cancel").onclick = () => close(null);
        box.querySelector("#fb-save").onclick = () => {
          if (author) localStorage.setItem("mock-author", box.querySelector("#fb-author").value.trim());
          close(field.value.trim());
        };
      });
    },
  };

  document.addEventListener("click", (e) => feedback.capture(e), true);
  document.addEventListener("keydown", (e) => {
    if (e.key === "F2") {
      if (fold.folded) fold.toggle();  // the bar comes back with the panel
      feedback.toggle();
    }
    if (e.key === "Escape") {  // closes the comment box, or else the dialog
      if (document.querySelector(".fb-dialog") && feedback.closeBox) feedback.closeBox();
      else closeDialog();
    }
    if (e.key === "Enter" && e.target.matches && e.target.matches("[data-search]")) applyFilters(listScope(e.target));
  });
  window.addEventListener("hashchange", render);
  window.addEventListener("resize", () => { feedback.renderPins(); custom.draw(); });

  const tools = document.createElement("div");
  tools.className = "fb-tools";
  // The presenter's tools, together and in their own colour so nobody takes them for part of the system:
  // which mock-up this is, the role to view it as, and Feedback. Hidden in screenshots.
  // Opened from the page that lists every mock-up (its address is then /p/<project>/): a way back to it.
  const fromHome = /^\/p\/[^/]+\//.test(location.pathname);
  const homeLink = fromHome ? `<a class="fb-home" href="/" title="All mock-ups" aria-label="All mock-ups"><svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><rect x="3" y="3" width="7" height="7" rx="1.5"/><rect x="14" y="3" width="7" height="7" rx="1.5"/><rect x="3" y="14" width="7" height="7" rx="1.5"/><rect x="14" y="14" width="7" height="7" rx="1.5"/></svg></a>` : "";
  // The bar folds away to one small button (remembered), so nothing on a page is covered for long.
  const FOLD = '<svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="m13 17 5-5-5-5"/><path d="m6 17 5-5-5-5"/></svg>';
  const UNFOLD = '<svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="m11 17-5-5 5-5"/><path d="m18 17-5-5 5-5"/></svg>';
  tools.innerHTML = `<div class="fb-bar"><button class="fb-fold" id="fb-fold" type="button" title="Fold the bar away" aria-label="Fold the presenter's bar away" aria-expanded="true">${FOLD}</button>${homeLink}<span class="fb-badge" title="A mock-up with sample data: nothing is saved">Mock-up${P.version != null ? ` v${esc(P.version)}` : ""}</span>`
    + `<label class="fb-viewas" hidden>View as <select class="role-switch" title="Switch role (mock-up only)">${S.roles.map((x) => `<option value="${esc(x.id)}">${esc(x.name)}</option>`).join("")}</select></label>`
    + `<span class="fb-live" hidden title="A live session: comments reach the assistant as they are saved">Live</span>`
    + `<label class="fb-custom" hidden title="Show custom work: tag what the platform does not give as standard"><input type="checkbox" id="fb-custom" role="switch" aria-label="Show custom work"><span class="fb-switch" aria-hidden="true"></span>Custom work</label>`
    + `<button id="fb-reset" hidden title="Put the sample data back and start the walk-through again"><svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M 3 12a9 9 0 1 0 9-9 9.75 9.75 0 0 0-6.74 2.74L3 8"/><path d="M 3 3v5h5"/></svg>Reset sample data</button>`
    + `<button id="fb-update" hidden title="The mock-up was changed. Press when you are ready: you stay on this screen.">Update ready</button>`
    + `<button id="fb-toggle">Feedback</button></div><div id="fb-panel" hidden></div>`;
  document.body.appendChild(tools);
  function syncTools(r, screen) {
    tools.querySelector(".fb-viewas").hidden = !r.role || screen.type === "login";
    tools.querySelector(".role-switch").value = r.role || "";
  }
  document.getElementById("fb-toggle").onclick = () => feedback.toggle();
  const fold = {
    folded: (() => { try { return localStorage.getItem("mock-bar") === "folded"; } catch (e) { return false; } })(),
    show() {
      tools.classList.toggle("folded", this.folded);
      const b = document.getElementById("fb-fold");
      b.innerHTML = this.folded ? UNFOLD : FOLD;
      b.title = this.folded ? "Show the presenter's bar" : "Fold the bar away";
      b.setAttribute("aria-label", this.folded ? "Show the presenter's bar" : "Fold the presenter's bar away");
      b.setAttribute("aria-expanded", String(!this.folded));
    },
    toggle() {
      this.folded = !this.folded;
      if (this.folded && feedback.active) feedback.toggle();  // folded away, the panel goes too
      try { localStorage.setItem("mock-bar", this.folded ? "folded" : "open"); } catch (e) { /* not remembered */ }
      this.show();
    },
  };
  fold.show();
  document.getElementById("fb-fold").onclick = () => fold.toggle();

  // ------------------------------------------------------------------ a question before something is undone
  // A small box in the presenter's own look: the title says what happens, then Cancel and the action (in red
  // when it takes something away). Resolves true when the action is pressed.
  function ask(title, body, action) {
    return new Promise((done) => {
      const box = document.createElement("div");
      box.className = "fb-dialog fb-ask";
      box.innerHTML = `<div class="fb-dialog-inner" role="alertdialog" aria-modal="true" aria-labelledby="fb-ask-title"><div class="fb-title" id="fb-ask-title">${esc(title)}</div>
        ${body ? `<p class="fb-ask-body">${esc(body)}</p>` : ""}
        <div class="fb-actions"><span class="fb-hint"></span><button class="fb-btn quiet" data-ask="no">Cancel</button><button class="fb-btn destroy" data-ask="yes">${esc(action)}</button></div></div>`;
      document.body.appendChild(box);
      const close = (yes) => { box.remove(); feedback.closeBox = null; done(yes); };
      feedback.closeBox = () => close(false);  // Esc
      box.onclick = (e) => {
        const b = e.target.closest("[data-ask]");
        if (b) close(b.dataset.ask === "yes");
        else if (e.target === box) close(false);
      };
      box.querySelector('[data-ask="yes"]').focus();
    });
  }

  // ------------------------------------------------------------------ the walk-through
  // What a walk-through changed in the sample data is kept as the difference from it, list by list: the
  // records added, the fields changed on sample records, the records taken out. Kept per browser tab
  // (sessionStorage), so a reload or Update ready does not lose it; served, it is also sent to the server and
  // every browser showing this mock-up picks it up within a few seconds. When a new build changes the sample
  // data, the difference is laid over the new data: what still fits is kept (records added, changed fields the
  // new records still have, statuses that still exist), the rest is dropped. Screenshots always show the
  // sample data: nothing is read or kept with clean=1.
  const demo = {
    base: null,
    version: null,
    shared: false,
    ticket: 0,
    key: `mock-demo:${location.pathname}`,  // the page that lists every mock-up serves each at its own address
    off: () => !!address().q.clean,
    keyOf(name) {
      return Object.keys(((this.base || {})[name] || [])[0] || (S.data[name] || [])[0] || {})[0];
    },
    diff() {
      const lists = {};
      Object.keys(S.data).forEach((name) => {
        const key = this.keyOf(name);
        if (!key) return;
        const before = (this.base || {})[name] || [], now = S.data[name] || [];
        const old = new Map(before.map((x) => [String(x[key]), x]));
        const seen = new Set(now.map((x) => String(x[key])));
        const created = now.filter((x) => !old.has(String(x[key])));
        const changed = {};
        now.forEach((x) => {
          const o = old.get(String(x[key]));
          if (!o) return;
          const fields = {};
          Object.keys(x).forEach((f) => { if (JSON.stringify(x[f]) !== JSON.stringify(o[f])) fields[f] = x[f]; });
          if (Object.keys(fields).length) changed[String(x[key])] = fields;
        });
        const removed = before.filter((x) => !seen.has(String(x[key]))).map((x) => String(x[key]));
        if (created.length || Object.keys(changed).length || removed.length) lists[name] = clone({ key, created, changed, removed });
      });
      return lists;
    },
    // The sample data with `lists` laid over it, in place: Mockup.data and its lists stay the same objects.
    apply(lists) {
      Object.keys(this.base).forEach((name) => {
        const d = (lists || {})[name];
        const key = this.keyOf(name);
        let out = clone(this.base[name]);
        if (d && key) {
          const removed = new Set((d.removed || []).map(String));
          out = out.filter((x) => !removed.has(String(x[key])));
          out.forEach((x) => {
            Object.entries((d.changed || {})[String(x[key])] || {}).forEach(([f, v]) => {
              if (!(f in x) && f !== "timeline" && f !== "status") return;  // a field the new sample data no longer has
              if (f === "status" && (S.statuses || []).length && !findStatus(v)) return;  // a status that is gone
              x[f] = v;
            });
          });
          const have = new Set(out.map((x) => String(x[key])));
          out = (d.created || []).filter((x) => x && typeof x === "object" && !have.has(String(x[key]))).map(clone).concat(out);
        }
        const list = S.data[name] || (S.data[name] = []);
        list.splice(0, list.length, ...out);
      });
    },
    keep(lists) {
      try {
        if (Object.keys(lists).length) sessionStorage.setItem(this.key, JSON.stringify({ lists }));
        else sessionStorage.removeItem(this.key);
      } catch (e) { /* storage full or switched off: the walk-through still works until a reload */ }
      tools.querySelector("#fb-reset").hidden = !Object.keys(lists).length || this.off();
    },
    async load() {
      this.base = clone(S.data);  // after the project's own code, which may add to the sample data
      if (this.off()) return;
      let lists = null;
      if (location.protocol.startsWith("http")) {
        try {
          const res = await fetch("api/state", { cache: "no-store" });
          const got = res.ok ? await res.json() : null;
          if (got && got.lists && typeof got.lists === "object") Object.assign(this, { shared: true, version: got.version }), lists = got.lists;
        } catch (e) { /* no server to share with: this tab keeps its own */ }
      }
      if (!this.shared) {
        try { lists = (JSON.parse(sessionStorage.getItem(this.key) || "null") || {}).lists; } catch (e) { lists = null; }
      }
      if (lists) this.apply(lists);
      this.keep(this.diff());
    },
    // After the engine (or the project's own code) changed the data. `touched`: {list: [ids]} of the records it
    // changed; only those are taken from this browser, so a change another browser made meanwhile is not undone.
    save(touched) {
      if (this.off() || !this.base) return;
      const lists = this.diff();
      this.keep(lists);
      if (!this.shared) return;
      const ticket = ++this.ticket;
      fetch("api/state", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ lists, touched: touched || {} }) })
        .then((res) => (res.ok ? res.json() : null))
        .then((got) => { if (got && ticket === this.ticket) this.take(got); })
        .catch(() => { /* the server is not answering: kept in this tab, and sent with the next change */ });
    },
    // What the server holds, drawn when it differs from what this page shows.
    take(got) {
      this.version = got.version;
      if (JSON.stringify(got.lists || {}) === JSON.stringify(this.diff())) return;
      this.apply(got.lists || {});
      this.keep(this.diff());
      render();
    },
    // Asked every few seconds: a change made in another browser. Not while someone is typing on the page.
    async poll() {
      if (!this.shared || this.off()) return;
      const ticket = this.ticket;
      let got;
      try {
        const res = await fetch("api/state", { cache: "no-store" });
        if (!res.ok) return;
        got = await res.json();
      } catch (e) { return; }
      if (ticket !== this.ticket || !got || got.version === this.version) return;
      const at = document.activeElement;
      const typing = at && app.contains(at) && (at.tagName === "TEXTAREA" || (at.tagName === "INPUT" && !/^(checkbox|radio|hidden|file)$/.test(at.type)));
      if (typing || document.querySelector(".fb-dialog")) return;  // drawn at the next ask, once they are done
      this.take(got);
    },
    async reset() {
      const shared = this.shared;
      if (!(await ask("Reset the sample data?", `Records added or moved in this walk-through go back to the sample data${shared ? ", for everyone viewing this mock-up" : ""}. Comments are not affected.`, "Reset"))) return;
      this.apply({});
      this.keep({});
      if (shared) {
        const ticket = ++this.ticket;
        try {
          const res = await fetch("api/state", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ reset: true }) });
          const got = res.ok ? await res.json() : null;
          if (got && ticket === this.ticket) this.version = got.version;
        } catch (e) { /* the others keep theirs until the server answers */ }
      }
      render();
      toast("The sample data is back: the walk-through starts again.");
    },
  };

  // ------------------------------------------------------------------ custom work
  // What the project's platform does not give as standard carries a small tag while presenting, so nobody
  // takes it for standard: the parts the platform check names (BUILD.custom, from the spec's platform_fit) and
  // what the project's own code adds (BUILD.custom_code). Hovering it says what it takes. "Custom work" on the
  // bar hides the tags, and the choice is remembered. Never in a screenshot.
  const LABEL_CUSTOM = "Custom development";
  const CUSTOM_DEFAULT = { label: LABEL_CUSTOM, title: "Built in the project's own mock-up code: needs custom work on the platform" };
  const TAG_ICON = '<svg viewBox="0 0 24 24" width="12" height="12" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="m18 16 4-4-4-4"/><path d="m6 8-4 4 4 4"/><path d="m14.5 4-5 16"/></svg>';
  const custom = {
    shown: (() => { try { return localStorage.getItem("mock-show-custom") !== "off"; } catch (e) { return true; } })(),
    visible: (el) => !!el && el.getClientRects().length > 0 && !el.closest("[hidden]"),
    draw() {
      document.querySelectorAll(".cw-tag").forEach((t) => t.remove());
      const r = route();
      const content = document.getElementById("content"), modal = app.querySelector(".modal");
      const marks = new Map();  // element: [label, titles]
      const mark = (el, label, title) => {
        if (!el || !this.visible(el)) return;
        const m = marks.get(el) || [label, []];
        if (title && !m[1].includes(title)) m[1].push(title);
        marks.set(el, m);
      };
      (BUILD.custom || []).forEach((t) => {
        const scope = t.dialog ? (modal && r.q.dialog === t.dialog ? modal : null) : (content && t.screen === app.dataset.screen ? content : null);
        if (!scope) return;
        const sel = `[data-el="${CSS.escape(t.element)}"]`;
        mark(scope.matches(sel) ? scope : [...scope.querySelectorAll(sel)].find((el) => this.visible(el)), t.label, t.title);
      });
      const code = BUILD.custom_code || null;
      app.querySelectorAll("[data-custom]").forEach((el) => {
        const how = el.dataset.custom;
        if (how === "no" || (how === "auto" && !code)) return;
        mark(el, (code || CUSTOM_DEFAULT).label, el.dataset.customNote || (code || CUSTOM_DEFAULT).title);
      });
      tools.querySelector(".fb-custom").hidden = !marks.size && !(BUILD.custom || []).length && !code;
      if (document.body.classList.contains("clean") || !this.shown) return;
      marks.forEach(([label, titles], el) => {
        const rect = el.getBoundingClientRect();
        const tag = document.createElement("div");
        tag.className = label === LABEL_CUSTOM ? "cw-tag" : "cw-tag warn";  // not supported at all: the word says so in amber
        tag.innerHTML = `${TAG_ICON}<span>${esc(label)}</span>`;
        tag.title = titles.join("\n") || label;
        tag.style.left = `${Math.max(0, rect.left + window.scrollX + 6)}px`;
        tag.style.top = `${Math.max(0, rect.top + window.scrollY - 10)}px`;
        if (el.closest(".modal")) tag.style.position = "fixed", tag.style.left = `${rect.left + 6}px`, tag.style.top = `${rect.top - 10}px`;
        document.body.appendChild(tag);
      });
    },
    toggle(on) {
      this.shown = on;
      try { localStorage.setItem("mock-show-custom", on ? "on" : "off"); } catch (e) { /* not remembered */ }
      this.draw();
    },
  };

  // ------------------------------------------------------------------ the project's own code
  // spec/mockup.js in a project is loaded after this engine, for what the spec cannot describe. It works
  // through window.Mockup:
  //   Mockup.onRender(fn)   fn({screen, role, q, root}) after every screen is drawn (at once if one already is):
  //                         screen is the screen's id ("__flow" for the process flow), role the role's id, q the
  //                         address's settings ({record, page, dialog}) and root the element the mock-up is drawn in
  //   Mockup.go(screen, {record, page})   Mockup.render()   Mockup.route()   Mockup.toast(text)
  //   Mockup.spec, Mockup.data   the spec and its sample data (kept for the walk-through, like the engine's changes)
  //   Mockup.changed()      after changing Mockup.data: keeps the change for the walk-through and shares it
  //   Mockup.matches(condition, record)   the engine's own test for `when` and `where`
  //   Mockup.custom(el, note)   tags el "Custom development" while presenting (note: what it takes, on hover);
  //                         Mockup.custom(el, false) says el is standard on the platform and is never tagged
  // Give what it adds a data-el ("region:<name>") and it can be commented on like the rest. What it adds to a
  // screen is tagged as custom development, unless the platform check found the project's code standard or
  // configuration, or it says otherwise with Mockup.custom(el, false). An error in it is written to the
  // browser's console and never stops the engine.
  const renderHooks = [];
  let lastView = null;
  const callHook = (fn, view) => {
    try { fn(view); } catch (e) { console.error("The project's own mock-up code failed:", e); }
  };
  function runHooks(view) {
    lastView = view;
    if (!renderHooks.length) return;
    // What the hooks add to the screen is the project's own work: marked, so it can be tagged as custom.
    const watch = typeof MutationObserver === "function" ? new MutationObserver(() => {}) : null;
    if (watch) watch.observe(app, { childList: true, subtree: true });
    renderHooks.forEach((fn) => callHook(fn, view));
    if (!watch) return;
    const added = watch.takeRecords().flatMap((m) => [...m.addedNodes]).filter((n) => n.nodeType === 1 && n.isConnected);
    watch.disconnect();
    added.filter((n) => !added.some((o) => o !== n && o.contains(n))).forEach((n) => { if (!n.dataset.custom) n.dataset.custom = "auto"; });
  }
  window.Mockup = {
    spec: S, data: S.data, route, go, toast, matches, render: () => render(),
    onRender(fn) {
      renderHooks.push(fn);
      if (lastView) callHook(fn, lastView);
    },
    changed() {  // everything differs from the sample data as this browser has it now
      const touched = {};
      Object.keys(S.data).forEach((name) => {
        const key = demo.keyOf(name);
        if (key) touched[name] = [...(S.data[name] || []), ...((demo.base || {})[name] || [])].map((x) => String(x[key]));
      });
      demo.save(touched);
    },
    custom(el, note) {
      if (!el || !el.dataset) return;
      el.dataset.custom = note === false ? "no" : "yes";
      if (typeof note === "string" && note.trim()) el.dataset.customNote = note.trim();
      if (lastView) custom.draw();
    },
  };

  // ------------------------------------------------------------------ following the spec
  // The server builds the mock-up again when its spec changes; a page that is open then reloads itself.
  // A spec with a mistake in it never shows here: the server keeps the last good build, and the mistake is
  // the assistant's to see, not the room's.
  async function follow() {
    if (!location.protocol.startsWith("http") || document.body.classList.contains("clean")) return;
    let now;
    try {
      const res = await fetch("api/build", { cache: "no-store" });
      if (!res.ok) return;
      now = await res.json();
    } catch (e) { return; }  // the server is not answering: nothing to follow
    if (live.listening !== !!now.live) {
      live.listening = !!now.live;
      tools.querySelector(".fb-live").hidden = !live.listening;
      feedback.renderPanel();  // "Received" is only said while someone is there to receive
    }
    if (live.stamp === null) live.stamp = now.stamp;
    else if (now.stamp) tools.querySelector("#fb-update").hidden = now.stamp === live.stamp;
    if (feedback.presenter !== !!now.presenter) {  // on the machine running the server: may edit or delete any comment
      feedback.presenter = !!now.presenter;
      feedback.renderPanel();
    }
  }
  // After an update feedback mode is off, whatever it was: the presenter's next click (Approve, say) does what
  // it says instead of opening a comment box.
  document.getElementById("fb-update").onclick = () => {
    sessionStorage.setItem("mock-updated", "1");
    location.reload();
  };
  const updated = sessionStorage.getItem("mock-updated");
  sessionStorage.removeItem("mock-updated");
  if (updated) setTimeout(() => toast("Updated: this is the mock-up as the spec is now."), 300);

  document.getElementById("fb-reset").onclick = () => demo.reset();
  document.getElementById("fb-custom").checked = custom.shown;
  document.getElementById("fb-custom").onchange = (e) => custom.toggle(e.target.checked);

  Promise.all([feedback.load(), demo.load()]).then(() => {
    render();
    feedback.refresh();
    follow();
  });
  setInterval(() => feedback.sync(), 5000);
  setInterval(follow, 2500);
  setInterval(() => demo.poll(), 2500);
})();
