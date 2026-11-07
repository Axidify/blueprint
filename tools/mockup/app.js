/* Blueprint clickable mock-up engine.
 *
 * Renders a project's spec (window.SPEC, written by tools/mockup.py build) as a clickable app.
 * URL: index.html#/<screen>?role=<role>&record=<id>&page=<n>&dialog=<id>&clean=1
 *   clean=1 hides the feedback UI (used for screenshots); menu=0 hides the side menu (the document's pictures).
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
  // The spec as this page was opened, before the walk-through changes its sample data: compared with the new one
  // after Update ready, to say what changed.
  const SPEC_AS_OPENED = JSON.stringify(window.SPEC);
  const P = S.project;
  S.data = S.data || {};
  // What the build worked out for the engine: the buttons that add a record, and what to tag as custom work.
  const BUILD = window.MOCKUP_BUILD || {};
  const clone = (v) => JSON.parse(JSON.stringify(v === undefined ? null : v));
  const app = document.getElementById("app");
  const byId = (list, id) => (list || []).find((x) => x.id === id);
  const esc = (v) => String(v == null ? "" : v).replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
  const slug = (v) => String(v).toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "");

  // The look the build drew it in (project.theme, or the one its platform suggests). The desk theme speaks in
  // sentence case and follows the design language's button tiers; its accent is Cobalt when the spec sets none.
  const THEME = String(BUILD.theme || P.theme || "desk");
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
    if (el.closest(".modal") && r.q.row != null && r.q.list) {  // in a dialog a row action opened: that row's record
      const data = (S.data || {})[r.q.list] || [];
      const key = Object.keys(data[0] || {})[0];
      return { name: r.q.list, rec: data.find((x) => String(x[key]) === r.q.row) || null };
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
  // With `named_by` it is the other way round: every record of the other list that names this one (a plan's
  // tasks, by their `plan_no`) moves, those its `where` lets through (the tasks not yet done); `match` is the
  // field of this record they name, its identifier when left out.
  function moveLinked(links, rec) {
    const moved = {};
    links.forEach((l) => {
      const list = (S.data || {})[l.data] || [];
      const id = Object.keys(list[0] || {})[0];
      const to = findStatus(l.set_status);
      if (!to) return;
      let others;
      if (l.named_by != null && l.named_by !== "") {
        const mine = rec[l.match != null ? l.match : Object.keys(rec)[0]];
        others = mine == null ? [] : list.filter((x) => String(x[l.named_by]) === String(mine) && matches(l.where, x));
      } else {
        const key = l.key || id;
        others = rec[l.link] == null ? [] : list.filter((x) => String(x[key]) === String(rec[l.link])).slice(0, 1);
      }
      others.forEach((other) => {
        setStatus(other, to);
        Object.entries(l.copy || {}).forEach(([there, here]) => { other[there] = rec[here]; });
        (moved[l.data] = moved[l.data] || []).push(String(other[id]));
      });
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
      const at = byId(S.screens, r.screen) || {};
      const opener = modal && [...(at.buttons || []), ...((at.list || {}).actions || [])].find((b) => b.dialog === r.q.dialog);
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
  window.addEventListener("resize", () => { fitLists(); syncFakes(); });
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
        else if (field.type === "camera") v = samplePhoto();
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

  // ------------------------------------------------------------------ changed records
  // The main button of a form opened on a record (Save on Edit User) writes what was typed back into that
  // record, so the list it came from, and every screen that shows it, shows the change. Only fields the
  // list's records hold are written (a comment typed on an approval form is not), never the record's id, and
  // only fields the presenter saw (a step of the form never opened keeps its values).
  const saveAttr = (b, r, dialog) => {
    const screen = byId(S.screens, r.screen);
    return !dialog && !b.dialog && b.style === "primary" && screen && screen.type === "form" && formOnRecord(screen, r.q) ? " data-save" : "";
  };
  function saveRecord(r) {
    rememberTyped();
    const screen = byId(S.screens, r.screen) || {};
    const rec = record(screen, r.q);
    const list = (S.data || {})[screen.data] || [];
    const key = Object.keys(list[0] || {})[0];
    if (!key || !Object.keys(rec).length) return null;
    const held = new Set(list.flatMap((x) => Object.keys(x)));
    let changed = false;
    (screen.sections || []).flatMap((s) => s.fields || []).forEach((f) => {
      if (f.id === key || f.id === "status" || f.id === "timeline" || !held.has(f.id) || !typed.values["field:" + f.id]) return;
      const was = rec[f.id];
      let v = typedValue(f);
      if (typeof was === "number" && v !== "" && !isNaN(Number(v))) v = Number(v);
      else if (typeof was === "boolean") v = v === true || /^(true|yes|y|1)$/i.test(String(v));
      else if (typeof was === "string" && /^(yes|no)$/i.test(was) && (v === true || v === "")) v = v === true ? "Yes" : "No";
      if (JSON.stringify(v) !== JSON.stringify(was == null ? "" : was)) { rec[f.id] = v; changed = true; }
    });
    if (changed) demo.save({ [screen.data]: [String(rec[key])] });
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

  // ------------------------------------------------------------------ phone screens
  const screenKind = { phone: false };  // the screen being drawn is a phone screen (set by render)
  // A screen with `device: phone` (or every screen, with `project.device: phone`; a screen's own `device: desktop`
  // keeps it a web page) is drawn as a phone app, after Apple's own apps (docs/design-language.md, Phones and
  // tablets): a phone 390 × 844 on the page, its status bar, a top bar with Back on a screen opened from a list,
  // a large title, the lists as rows, one field per line, the main button full width within thumb reach, and a
  // tab bar at the bottom with the phone screens of the menu (at most five: more go under More). A dialog is a
  // sheet that slides up from the bottom. The phone's own parts are how the mock-up is shown, never custom work.
  const DEVICE = String(P.device || "").toLowerCase();
  const isPhone = (screen) => String((screen && screen.device) || DEVICE).toLowerCase() === "phone";
  const TAB_ICON = '<svg viewBox="0 0 24 24" width="22" height="22" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><rect x="4" y="4" width="16" height="16" rx="4"/></svg>';
  const MORE_ICON = '<svg viewBox="0 0 24 24" width="22" height="22" fill="currentColor" aria-hidden="true"><circle cx="5" cy="12" r="1.8"/><circle cx="12" cy="12" r="1.8"/><circle cx="19" cy="12" r="1.8"/></svg>';
  const phoneTabs = (role) => S.screens.filter((s) => s.menu && isPhone(s) && canSee(s, role));
  let cameFrom = null, shownScreen = null;  // the screen shown before this one (Back names it and goes back to it), and this one
  function phoneShell(r, screen, body) {
    const role = byId(S.roles, r.role) || { name: r.role };
    const tabs = phoneTabs(r.role);
    const shown = tabs.length > 5 ? tabs.slice(0, 4) : tabs;
    const more = tabs.length > 5 ? tabs.slice(4) : [];
    const onTab = tabs.some((s) => s.id === screen.id);
    const from = cameFrom && cameFrom !== screen.id ? byId(S.screens, cameFrom) : null;
    const backTo = from && isPhone(from) ? from : tabs[0];
    const back = !onTab && backTo ? `<a href="#" class="p-back" data-back="${esc(backTo.id)}" data-el="button:Back">‹ ${esc(backTo.menu || backTo.title || "Back")}</a>` : "<span></span>";
    const clean = r.q.clean ? "?clean=1" : "";
    const tab = (s) => `<a class="p-tab${s.id === screen.id ? " on" : ""}" data-el="menu:${esc(s.menu)}" href="#/${s.id}${clean}">${TAB_ICON}<span>${esc(s.menu)}</span></a>`;
    const moreOn = more.some((s) => s.id === screen.id);
    return `
      <div class="phone-stage">
        <div class="phone" data-el="region:phone">
          <div class="p-status" aria-hidden="true"><span>9:41</span><span class="p-signal"><i></i><i></i><i></i><i></i></span></div>
          <header class="p-bar" data-el="region:header">${back}<span class="user" data-el="header:user">${role.user ? person(role.user) : esc(role.name)}</span><a class="logout" href="#/login" data-el="header:logout">${W.logout}</a></header>
          <main class="content p-content" id="content" data-el="region:page background">${body}</main>
          ${tabs.length ? `<nav class="p-tabs" data-el="region:tab bar">${shown.map(tab).join("")}${more.length ? `<a href="#" class="p-tab${moreOn ? " on" : ""}" data-more data-el="menu:More">${MORE_ICON}<span>More</span></a>` : ""}</nav>` : ""}
          ${more.length ? `<div class="p-more" hidden data-el="region:more">${more.map((s) => `<a class="p-more-item" data-el="menu:${esc(s.menu)}" href="#/${s.id}${clean}">${esc(s.menu)}<span>›</span></a>`).join("")}</div>` : ""}
          <div class="p-home" aria-hidden="true"></div>
        </div>
      </div>`;
  }
  // A list on a phone: a row per record, the first column on top, the next two under it in grey, the first
  // status column on the right, and a chevron when the row opens a screen. The row's other actions are links.
  function phoneRows(list, r, data, key) {
    const cols = list.columns || [];
    const chip = cols.find((c) => c.chip);
    const [main, ...rest] = cols.filter((c) => !c.chip);
    const details = rest.slice(0, 2);
    const cell = (c, row, cls) => `<span class="${cls}" data-el="cell:${esc(c.label)}|${esc(row[key])}">${esc(row[c.field])}</span>`;
    return data.map((row) => {
      const acts = (list.actions || []).filter((a) => matches(a.when, row) && (!a.roles || a.roles.includes(r.role)));
      const opener = acts.find((a) => a.to && !a.dialog && a.set_status == null);
      const others = acts.filter((a) => a !== opener);
      const text = `${main ? cell(main, row, "p-main") : ""}${details.length ? `<span class="p-details">${details.filter((c) => row[c.field] != null && row[c.field] !== "").map((c) => cell(c, row, "p-detail")).join('<span class="p-dot"> · </span>')}</span>` : ""}`;
      const side = `${chip ? `<span class="p-side" data-el="cell:${esc(chip.label)}|${esc(row[key])}"><span class="chip ${statusClass(row[chip.field])}">${esc(row[chip.field])}</span></span>` : ""}${opener ? '<span class="p-chevron" aria-hidden="true">›</span>' : ""}`;
      const body = opener
        ? `<a href="#" class="p-row-link" data-el="action:${esc(opener.label)}" data-go="${esc(opener.to)}" data-record="${esc(row[key])}" data-list="${esc(list.data)}"${opener.toast ? ` data-toast="${esc(opener.toast)}"` : ""}><span class="p-text">${text}</span>${side}</a>`
        : `<div class="p-row-link"><span class="p-text">${text}</span>${side}</div>`;
      const links = others.length ? `<div class="p-actions" data-el="cell:${W.action}|${esc(row[key])}">${others.map((a) => rowAction(a, row, key, list)).join(" ")}</div>` : "";
      return `<tr data-row="${esc(JSON.stringify(Object.fromEntries([...(list.filters || []), ...(list.search || [])].map((f) => [f, row[f] == null ? "" : String(row[f])]))))}" data-el="row:${esc(row[key])}"><td class="p-row">${body}${links}</td></tr>`;
    }).join("");
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

  // What a filter or search box is called on the screen (and in a comment on it): the label of the list's column
  // for that field, else the label of a field with that id on a screen or in a dialog, else the id in words
  // ("unit_ref" reads "Unit Ref"). Never the bare id: the client read "the unit_ref search box".
  const words = (id) => String(id).replace(/[_\s]+/g, " ").trim().replace(/\b\w/g, (ch) => ch.toUpperCase());
  function boxLabel(list, f) {
    const col = (list.columns || []).find((c) => c.field === f && c.label);
    if (col) return col.label;
    const fields = [...S.screens.flatMap((s) => (s.sections || []).flatMap((x) => x.fields || [])), ...(S.dialogs || []).flatMap((d) => d.fields || [])];
    const named = fields.find((x) => x.id === f && x.label);
    return named ? named.label : words(f);
  }
  // A row action works on its own row: `to` opens a screen with that row's record, `set_status` moves it,
  // `dialog` opens a dialog on it (its confirm button then moves that row, and goes on with its record), and
  // `toast` says something. Without one of them it is a link that does nothing.
  function rowAction(a, row, key, list) {
    const id = esc(row[key]);
    const onRow = a.to || a.dialog || a.set_status != null;
    return `<a href="#" class="link" data-el="action:${esc(a.label)}" ${a.dialog ? `data-dialog="${esc(a.dialog)}"` : a.to ? `data-go="${a.to}"` : ""}`
      + ` ${onRow ? `data-record="${id}" data-list="${esc(list.data)}"` : ""} ${a.set_status != null && !a.dialog ? moveAttr(a) : ""}`
      + ` ${a.toast ? `data-toast="${esc(a.toast)}"` : ""}>${esc(a.label)}</a>`;
  }

  // The values a list's filters open on, for the role signed in: {field: value}, or null. The word All (or
  // nothing) is no filter, so a role can be given the whole list where the others open on a value.
  function filtersStarted(list) {
    const by = (list.filter_start_by_role || {})[route().role];
    const start = by && typeof by === "object" ? by : list.filter_start;
    if (!start || typeof start !== "object") return null;
    const out = {};
    Object.entries(start).forEach(([f, v]) => { if (v != null && String(v).trim() !== "" && !/^all$/i.test(String(v).trim())) out[f] = v; });
    return Object.keys(out).length ? out : null;
  }
  // `shown`: the record of the detail screen a related list is drawn on (see `where_record` in rows()).
  function renderList(list, r, shown) {
    if (!list) return "";
    const data = rows(list, shown);
    const cols = list.columns || [];
    // A filter's first choice, "All", is no filter: its value is empty, so a record whose value is the word
    // "All" (a user of all sites) cannot be taken for it. That choice is then "Any", so the list never offers
    // "All" twice, and the real value stays a choice of its own. A blank value is no choice.
    // A filter may open on a value of its own (`filter_start`, or `filter_start_by_role` for a role): the list
    // is then drawn already filtered, and Clear Filters still shows everything.
    const start = filtersStarted(list) || {};
    const filters = (list.filters || []).map((f) => {
      const label = boxLabel(list, f);
      const vals = [...new Set(((S.data || {})[list.data] || []).map((x) => x[f]).filter((v) => v != null && v !== "").map(String))];
      const none = vals.some((v) => v.trim().toLowerCase() === "all") ? "Any" : "All";
      const from = start[f] == null ? "" : String(start[f]);
      if (from && !vals.includes(from)) vals.push(from);
      return `<div class="filter" data-el="filter:${esc(label)}"><label>${esc(label)}</label><select class="f-input" data-filter="${esc(f)}"><option value="">${none}</option>${vals.map((v) => `<option value="${esc(v)}"${v === from ? " selected" : ""}>${esc(v)}</option>`).join("")}</select></div>`;
    }).join("");
    const search = (list.search || []).map((f) => {
      const label = boxLabel(list, f);
      return `<div class="filter" data-el="search:${esc(label)}"><label>${esc(label)}</label><input class="f-input" placeholder="Search" data-search="${esc(f)}"></div>`;
    }).join("");
    const toolbar = (list.toolbar || []).map((b) => button(b, r)).join("");
    const key = Object.keys(data[0] || {})[0];
    // Each row carries the values its filters and search boxes look at (also fields that are not columns).
    const watched = [...(list.filters || []), ...(list.search || [])];
    const watchedValues = (row) => esc(JSON.stringify(Object.fromEntries(watched.map((f) => [f, row[f] == null ? "" : String(row[f])]))));
    // A column holds people when any of its values is a person: then every name in it gets its initials.
    const peopleCols = new Set(cols.filter((c) => !c.chip && data.some((row) => PEOPLE.has(String(row[c.field] == null ? "" : row[c.field]).trim().toLowerCase()))).map((c) => c.field));
    const body = data.length && screenKind.phone ? phoneRows(list, r, data, key) : data.length ? data.map((row) => `<tr data-row="${watchedValues(row)}" data-el="row:${esc(row[key])}">${cols.map((c) => `<td ${shortClass(String(row[c.field] == null ? "" : row[c.field]))}data-el="cell:${esc(c.label)}|${esc(row[key])}">${c.chip ? `<span class="chip ${statusClass(row[c.field])}">${esc(row[c.field])}</span>` : person(row[c.field], peopleCols.has(c.field))}</td>`).join("")}${(list.actions || []).length ? `<td class="actions" data-el="cell:Action|${esc(row[key])}">${list.actions.filter((a) => matches(a.when, row) && (!a.roles || a.roles.includes(r.role))).map((a) => rowAction(a, row, key, list)).join(" ")}</td>` : ""}</tr>`).join("")
      : `<tr><td colspan="${cols.length + 1}" class="empty">${esc(list.empty || "No records found")}</td></tr>`;
    // One block for the list: its toolbar row, the table and the count (the desk theme draws it as one card).
    return `<div class="list-block">
      ${search || filters || toolbar ? `<div class="list-tools" data-el="region:area above the list">${search || filters ? (screenKind.phone && filters
        // On a phone the filters fold into one Filters button; the search boxes stay in view.
        ? `<div class="filters" data-el="region:filters">${search}<details class="p-filters"${filtersStarted(list) ? " data-started" : ""}><summary class="btn small" data-el="button:Filters">Filters</summary><div class="p-filter-sheet">${filters}</div></details><button class="btn small" data-el="button:Search" data-apply-filters>Search</button><button class="btn small" data-el="button:Clear Filters" data-clear-filters>${W.clear}</button></div>`
        : `<div class="filters" data-el="region:filters">${search}${filters}<button class="btn small" data-el="button:Search" data-apply-filters>Search</button><button class="btn small" data-el="button:Clear Filters" data-clear-filters>${W.clear}</button></div>`) : "<div></div>"}<div class="toolbar" data-el="region:list buttons">${toolbar}</div></div>` : ""}
      <div class="table-wrap" data-el="region:list"><table class="datalist ${cols.length > 9 ? "dense" : ""}${screenKind.phone ? " p-list" : ""}">
        ${screenKind.phone ? "" : `<thead><tr>${cols.map((c) => `<th data-el="column:${esc(c.label)}">${esc(c.label)}</th>`).join("")}${(list.actions || []).length ? `<th data-el="column:${W.action}">${W.action}</th>` : ""}</tr></thead>`}
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
      case "file": input = ro ? `<div class="f-value">${esc(v) || "-"}</div>` : `<div class="file-drop" data-fake="file"><input type="hidden"><span class="fake-view">${fileHint()}</span></div>`; break;
      // A camera field takes a photo with the phone's camera: no file to drop or browse for.
      case "camera": input = `<div class="file-drop camera" data-fake="camera"><input type="hidden"><span class="fake-view">${CAMERA_HINT}</span></div>`; break;
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
    return `<button class="btn ${b.style || ""}${choice} ${b.example ? "fb-hide" : ""}" data-el="button:${esc(b.label)}" ${b.to ? `data-go="${b.to}"` : ""} ${b.toast ? `data-toast="${esc(b.toast)}"` : ""} ${b.dialog ? `data-dialog="${b.dialog}"` : ""} ${moveAttr(b)}${creates}${saveAttr(b, r, dialog)} ${attrs || ""}>${esc(b.label)}</button>`;
  }
  // A button on a screen that shows a record (a detail screen, or a form opened on a record), and the confirm
  // button of a dialog opened there, takes that record along to its `to` screen when that screen shows the same
  // data, so a walk-through stays on one record (details → progress → report) instead of jumping to the next
  // screen's own sample record. Toolbar and dashboard buttons show no record, so they take none.
  function carried(b, r, rec) {
    const here = byId(S.screens, r.screen), there = b && b.to && byId(S.screens, b.to);
    if (!here || !there || !here.data || here.data !== there.data) return "";
    if (!(here.type === "detail" || (here.type === "form" && formOnRecord(here, r.q)))) return "";
    const key = Object.keys(((S.data || {})[here.data] || [])[0] || {})[0];
    const shown = rec && Object.keys(rec).length ? rec : record(here, r.q);
    return key && shown[key] != null ? `data-record="${esc(shown[key])}"` : "";
  }
  const buttons = (list, r, rec) => (list && list.length ? `<div class="form-buttons" data-el="region:buttons">${list.map((b) => button(b, r, rec, carried(b, r, rec))).join("")}</div>` : "");
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
      return (i === main ? prev : "") + button(b, r, rec, carried(b, r, rec));
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
  // A step may name its role and status by id (`role: security`, `status: in-progress`): the picture, which goes
  // into the requirements document, shows their names, as the role and status tables beside it do.
  function renderFlow() {
    const f = S.process_flow;
    if (!f) return "<p>No process_flow in the spec.</p>";
    const roleName = (v) => (byId(S.roles, v) || (S.roles || []).find((x) => same(x.name, v)) || {}).name || v;
    const statusName = (v) => (findStatus(v) || {}).name || v;
    const steps = f.steps.map((s, i) => `
      ${i ? '<div class="flow-arrow">&#10140;</div>' : ""}
      <div class="flow-step ${s.optional ? "optional" : ""}">
        <div class="flow-num">${i + 1}</div>
        <div class="flow-name">${esc(s.name)}</div>
        <div class="flow-role">${esc(s.role ? roleName(s.role) : "")}${s.optional ? " · optional" : ""}</div>
        ${s.status ? `<div class="flow-status"><span class="chip ${statusClass(statusName(s.status))}">${esc(statusName(s.status))}</span></div>` : ""}
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
      <div class="modal-foot"><button class="btn" data-close>Cancel</button>${button(d.confirm || { label: "OK" }, route(), null, `data-close ${route().q.row != null ? "" : carried(d.confirm, route())}`, d.id)}</div>
    </div></div>`;
  }

  // ------------------------------------------------------------------ filters and search
  // They work on the rows already on the page: Search (or Enter in a search box) applies them, Clear Filters
  // resets them. A filter picks one value; a search box matches part of the text, in any letter case.
  function applyFilters(scope) {
    if (!scope) return;
    const picks = [...scope.querySelectorAll("[data-filter]")].filter((s) => s.value !== "").map((s) => [s.dataset.filter, s.value]);
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
    const inDialog = app.querySelector(".modal-body");
    if (inDialog && inDialog.querySelector("[data-filter] option[selected]")) applyFilters(inDialog);  // a filter that opens on a value
  }

  // ------------------------------------------------------------------ file and signature fields
  // Each keeps what it holds in a hidden input, so it survives a redraw like anything typed.
  // An empty file field says what a person does there: on a computer drop a file or browse for one, on a phone
  // take a photo or choose a file (a phone has no files to drop). The mock-up is on a phone when the window is
  // as narrow as one, or when the page is: a project's own code may draw a phone screen inside a phone frame.
  // A camera field (type: camera) only ever takes a photo, on a phone or a computer.
  const PHONE_WIDTH = 480, PHONE_PAGE = 440;
  function onPhone() {
    const content = document.getElementById("content");
    return document.body.classList.contains("on-phone") || window.innerWidth <= PHONE_WIDTH || (!!content && content.clientWidth > 0 && content.clientWidth <= PHONE_PAGE);
  }
  const fileHint = () => (onPhone() ? 'Take a photo or <span class="link">choose a file</span>' : 'Drop file here or <span class="link">browse</span>');
  const CAMERA_ICON = '<svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M4 8h3l2-3h6l2 3h3v11H4z"/><circle cx="12" cy="13" r="3.5"/></svg>';
  const CAMERA_HINT = `<span class="camera-take">${CAMERA_ICON}<span>Take a photo</span></span>`;
  const samplePhoto = () => { const d = new Date(); return `photo-${d.getFullYear()}${two(d.getMonth() + 1)}${two(d.getDate())}-${two(d.getHours())}${two(d.getMinutes())}.jpg`; };
  function syncFakes() {
    app.querySelectorAll("[data-fake]").forEach((box) => {
      const value = box.querySelector("input[type=hidden]").value;
      const kind = box.dataset.fake;
      box.querySelector(".fake-view").innerHTML = kind === "file"
        ? (value ? `<span class="file-name">${esc(value)}</span> <a href="#" class="link" data-fake-clear>Remove</a>` : fileHint())
        : kind === "camera"
          ? (value ? `<span class="file-name">${CAMERA_ICON} ${esc(value)}</span> <a href="#" class="link" data-fake-clear>Retake</a>` : CAMERA_HINT)
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
    // menu=0: the pictures for the requirements document leave the side menu out (the access matrix lists
    // each role's menu), so the screen itself is printed larger.
    document.body.classList.toggle("no-menu", r.q.menu === "0");
    if (r.screen === "__flow") {
      app.innerHTML = renderFlow();
      app.dataset.screen = "__flow";
      runHooks({ screen: "__flow", role: r.role, q: r.q, root: app });
      return;
    }
    const screen = byId(S.screens, r.screen) || byId(S.screens, "login") || { type: "login" };
    const signIn = screen.type === "login" || !r.role;
    // The sign-in page is a phone's when its screen says so, or when the project's screens are all phones.
    const phone = screenKind.phone = signIn ? isPhone(screen.type === "login" ? screen : byId(S.screens, "login") || {}) : isPhone(screen);
    document.body.classList.toggle("on-phone", phone);
    if ((screen.id || "login") !== shownScreen) { cameFrom = shownScreen; shownScreen = screen.id || "login"; }
    const frame = (inner) => (phone ? phoneShell(r, screen, inner) : shell(r, inner));
    if (signIn) {
      app.innerHTML = phone ? `<div class="phone-stage"><div class="phone p-sign-in" data-el="region:phone"><div class="p-status" aria-hidden="true"><span>9:41</span><span class="p-signal"><i></i><i></i><i></i><i></i></span></div>${renderLogin(screen)}<div class="p-home" aria-hidden="true"></div></div></div>` : renderLogin(screen);
    } else if (!canSee(screen, r.role)) {
      app.innerHTML = frame(`<div class="denied">You do not have access to this page.</div>`);
    } else {
      app.innerHTML = frame(renderScreen(screen, r));
    }
    // On a phone a dialog is a sheet from the bottom of the phone.
    if (r.q.dialog) (phone && app.querySelector(".phone") || app).insertAdjacentHTML("beforeend", renderDialog(r.q.dialog));
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
    syncFakes();  // again: the project's code may have drawn the screen as a phone
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
      input.value = clear ? "" : fake.dataset.fake === "file" ? "sample-document.pdf" : fake.dataset.fake === "camera" ? samplePhoto() : role.user || role.name || "Signed";
      syncFakes();
      if (typed.required) markRequired();
      return;
    }
    const back = e.target.closest("[data-back]");
    if (back) { e.preventDefault(); return go(back.dataset.back); }
    const more = e.target.closest("[data-more]");
    if (more) {  // the phone screens past the fifth tab
      e.preventDefault();
      const sheet = app.querySelector(".p-more");
      if (sheet) sheet.hidden = !sheet.hidden;
      return;
    }
    const el = e.target.closest("[data-go],[data-toast],[data-dialog],[data-close],[data-page],[data-role-login],[data-apply-filters],[data-clear-filters],[data-status],[data-status-by],[data-create],[data-save]");
    if (!el) return;
    e.preventDefault();
    if (el.dataset.applyFilters !== undefined || el.dataset.clearFilters !== undefined) {
      const scope = listScope(el);
      if (el.dataset.clearFilters !== undefined) {
        scope.querySelectorAll("[data-filter]").forEach((s) => { s.value = ""; });
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
    // On a form opened on a record the main button keeps what was typed in that record first.
    const saved = !made && el.dataset.save !== undefined ? saveRecord(r) : null;
    const moved = !made && (el.dataset.status !== undefined || el.dataset.statusBy !== undefined) && !el.dataset.dialog && moveStatus(el, r);
    const acted = made || moved || saved;
    if (saved) typed.key = null;  // drawn again, the form shows the record as saved
    // "{id}" in a message is the id of the record the button added or moved.
    if (el.dataset.toast) toast(el.dataset.toast.replace(/\{id\}/g, acted ? String(acted[Object.keys(acted)[0]]) : ""));
    if (made) typed.key = null;  // what was typed went into the record: drawn again, the form starts empty
    const before = location.hash;
    if (el.dataset.page) go(r.screen, { ...stay(r.q), page: el.dataset.page });
    // A row action's dialog opens on that row (row and list in the address), so its confirm button moves that row.
    else if (el.dataset.dialog) go(r.screen, { ...stay(r.q), dialog: el.dataset.dialog, ...(el.dataset.list && el.dataset.record != null ? { row: el.dataset.record, list: el.dataset.list } : {}) }, true);
    // A dialog's confirm button has both: it goes where it says, and only closes when it goes nowhere. Opened on
    // a row, it goes on with that row's record.
    else if (el.dataset.go) {
      const onRow = !el.dataset.record && r.q.row != null && el.closest(".modal") ? { record: r.q.row } : {};
      go(el.dataset.go, el.dataset.record ? { record: el.dataset.record } : onRow, !!r.q.dialog);
    }
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
    // The engine's own two parts of the top bar; any other (added by the project's own code, `header:connection`)
    // goes by its own name. All others used to be called the Logout link.
    if (kind === "header") return name === "user" ? "the signed-in user" : name === "logout" ? "the Logout link" : name ? `the ${name}` : "the header";
    // A filter or search box goes by its field's label; one saved under its field's id reads in words.
    if ((kind === "filter" || kind === "search") && /^[a-z0-9_]+$/.test(name) && name.includes("_")) {
      const fields = [...S.screens.flatMap((s) => (s.sections || []).flatMap((x) => x.fields || [])), ...(S.dialogs || []).flatMap((d) => d.fields || [])];
      const col = S.screens.flatMap((s) => ((s.list || {}).columns || [])).find((c) => c.field === name && c.label);
      return `the ${col ? col.label : (fields.find((f) => f.id === name && f.label) || {}).label || words(name)} ${kind === "search" ? "search box" : "filter"}`;
    }
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
  // The presenter's own settings (the folded bar, a minimised panel, done comments shown): kept in this browser
  // for every mock-up alike, like a preference, not per project. Storage switched off: the default, not an error.
  function remembered(key) {
    try { return localStorage.getItem(key) || ""; } catch (e) { return ""; }
  }
  function remember(key, value) {
    try { localStorage.setItem(key, value); } catch (e) { /* not remembered */ }
  }
  // What became of a comment, in the words the room reads (the server's ROOM_WORDS in tools/mockup.py says
  // the same: change both together).
  // A decision (often not to build what was asked) reads Decided, never Applied.
  const STATE_WORDS = { received: "Received", working: "Working on it", applied: "Applied", decided: "Decided", noted: "Noted for follow-up" };
  // Why a comment has no mark on the page (see place.of), said on its card in the panel.
  const AWAY = { hidden: "In a part of the screen that is folded away or hidden: open it to see the mark.",
    gone: "Not on this screen now (changed or removed since), so it has no mark.",
    role: "Made while viewing as {role}: what it is about may be on this screen for that role only. View as {role} to see it." };
  // A comment worked through (applied, decided, or noted for follow-up) is history: it steps back from the page, to a Done
  // part of the panel, so the marks on the page are only those still open. Show on the screen brings its marks back, faded.
  const DONE_STATES = ["applied", "decided", "noted"];
  const isDone = (c) => DONE_STATES.includes(c.state);
  // Where a comment's marks sit, in pixels. A pin overlaps the top-right corner of what it is about (in from the
  // right, up from the top); pins on the same thing sit side by side, this far apart. A box's pin sits on its
  // top-right corner. A box drawn round several things leaves this much room round them.
  const PIN = { inFromRight: 12, upFromTop: 8, apart: 18, boxInFromRight: 12, boxUpFromTop: 10 };
  const BOX_PADDING = 6;
  // A drag shorter than this (width plus height) is a click that wobbled, not a box.
  const CLICK_WOBBLE = 14;
  // Where a comment is on the page now: whether what it is about is on show, hidden or gone, why it has no mark,
  // and where its box goes. Reads the page only; the comments themselves are feedback's.
  const place = {
    // Whether what a comment is about can be marked on the page: "shown", "hidden" (there, but in a part folded
    // away or a closed tab) or "gone" (not on this screen now: removed by a change, or not drawn for this role).
    // A comment that is hidden or gone has no pin or box: one at its old place would point at something else.
    // Its card in the panel says so instead. A box for something new marks empty space, so it stays.
    of(c) {
      const forNew = c.box && !(Array.isArray(c.elements) && c.elements.length);
      const names = Array.isArray(c.elements) && c.elements.length ? c.elements : forNew ? [] : [c.element].filter(Boolean);
      if (!names.length || names.every((e) => e === "region:page background")) return "shown";
      const found = names.map((e) => document.querySelector(`#app [data-el="${CSS.escape(e)}"]`)).filter(Boolean);
      if (!found.length) {
        const now = route().role;  // made as another role: it may simply not be drawn for this one
        return c.role && now && c.role !== now ? "role" : "gone";
      }
      return found.some((el) => place.shown(el)) ? "shown" : "hidden";
    },
    // `where` is place.of(c) when the caller has it already.
    away(c, where) {
      if (isDone(c)) return null;  // history: the Done part of the panel says what became of it
      const text = AWAY[where === undefined ? place.of(c) : where];
      return text ? text.replaceAll("{role}", (byId(S.roles, c.role) || {}).name || c.role) : null;
    },
    // A thing on show, or null. A hidden one (in a section folded away, a closed tab) says it is at the top-left
    // corner of the page: a pin or box placed by it landed there, or stretched from there across the screen.
    shown(el) {
      if (!el) return null;
      const r = el.getBoundingClientRect();
      return r.width || r.height ? el : null;
    },
    // Where a drawn box is now: at its things, or where it was drawn when they are no longer on the screen.
    // null while what it is about is there but hidden: it is not drawn then (its comment stays in the panel).
    box(c) {
      const b = c.box || {};
      // A box drawn around several things follows them: around where they are now, whatever the window's width.
      const found = (Array.isArray(c.elements) ? c.elements : []).map((e) => document.querySelector(`#app [data-el="${CSS.escape(e)}"]`)).filter(Boolean);
      const parts = found.filter((el) => place.shown(el));
      if (Array.isArray(c.elements) && c.elements.length && !parts.length) return null;
      if (parts.length) {
        const rects = parts.map((el) => el.getBoundingClientRect());
        const left = Math.min(...rects.map((r) => r.left)), top = Math.min(...rects.map((r) => r.top));
        const right = Math.max(...rects.map((r) => r.right)), bottom = Math.max(...rects.map((r) => r.bottom));
        return { x: left + window.scrollX - BOX_PADDING, y: top + window.scrollY - BOX_PADDING,
          w: right - left + 2 * BOX_PADDING, h: bottom - top + 2 * BOX_PADDING };
      }
      // A box for something new stays beside the thing it was drawn next to, at the same distance.
      const near = b.near ? [...document.querySelectorAll(`#app [data-el="${CSS.escape(b.near)}"]`)][b.nearAt || 0] : null;
      if (near && !place.shown(near)) return null;
      if (near && Array.isArray(b.sx) && Array.isArray(b.sy)) {
        const a = near.getBoundingClientRect();
        const along = ([how, off], a0, alen, len) => how === "after" ? a0 + alen + off : how === "before" ? a0 - off - len : a0 + off;
        return { x: along(b.sx, a.left + window.scrollX, a.width, b.w), y: along(b.sy, a.top + window.scrollY, a.height, b.h), w: b.w, h: b.h };
      }
      const target = c.element && (b.fx != null || b.dx != null) ? document.querySelector(`#app [data-el="${CSS.escape(c.element)}"]`) : null;
      if (target && !place.shown(target)) return null;
      if (target && b.fx != null) {  // drawn in 1.3.1: sideways in proportion to its area; up and down at its distance from the nearest thing
        const at = target.getBoundingClientRect();
        const ref = b.ref ? document.querySelector(`#app [data-el="${CSS.escape(b.ref)}"]`) : null;
        const top = ref ? ref.getBoundingClientRect().top + window.scrollY + b.ry : at.top + window.scrollY + b.fy * at.height;
        return { x: at.left + window.scrollX + b.fx * at.width, y: top, w: b.fw * at.width, h: b.h };
      }
      if (target) {  // drawn before boxes kept their proportion: a fixed distance from its element
        const at = target.getBoundingClientRect();
        return { x: at.left + window.scrollX + b.dx, y: at.top + window.scrollY + b.dy, w: b.w, h: b.h };
      }
      return { x: b.x, y: b.y, w: b.w, h: b.h };
    },
  };

  // The comments a new one about `elements` is a layer on (see feedback.earlierOn).
  function layerOn(comments, elements) {
    const named = (elements || []).filter((e) => e && e !== "region:page background");
    if (!named.length) return [];
    return comments.filter((c) => {
      const about = Array.isArray(c.elements) && c.elements.length ? c.elements : [c.element];
      return named.every((e) => about.includes(e));
    });
  }
  window.MockupLayerOn = layerOn;  // for the tests

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
    mini: remembered("mock-feedback-mini") === "1",  // the list put away while Feedback stays on
    // Which comment a card or pin stands for: its number (FB-007), or for one not yet saved a key of its own that
    // lives as long as the page. Never its place in a list, which another browser's comment can shift.
    localKeys: new WeakMap(),
    nextKey: 0,
    keyOf(c) {
      if (c.id) return String(c.id);
      if (!this.localKeys.has(c)) this.localKeys.set(c, `new-${++this.nextKey}`);
      return this.localKeys.get(c);
    },
    byKey(key) { return this.forScreen().find((c) => this.keyOf(c) === key) || null; },
    showDone: remembered("mock-feedback-done") === "1",  // the marks of done comments shown, faded
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
    // This browser's unsent comments, kept across a reload. Another tab of the same mock-up keeps its own in the
    // same place: theirs are kept too, never written over (a comment is known by its writer, time and text).
    keepUnsent() {
      const sig = (c) => `${c.owner || ""}|${c.time || ""}|${c.text || ""}`;
      this.known = this.known || new Set();
      this.unsent.forEach((c) => this.known.add(sig(c)));
      const others = this.stored(this.unsentKey).filter((c) => !this.known.has(sig(c)));
      this.store(this.unsentKey, others.concat(this.unsent));
    },
    async load() {
      if (!this.remote) { this.items = this.stored(this.key); return; }
      // Served by the mock-up server, comments always go to it. When it does not answer just now (restarting,
      // busy), the page does not fall back to keeping comments in this browser for good: what is typed waits
      // here only until the server takes it, and the list comes with the next sync (every few seconds).
      this.unsent = this.stored(this.unsentKey);
      this.keepUnsent();
      let list = [];
      try {
        const res = await fetch("api/feedback");
        if (!res.ok) throw new Error(res.status);
        list = await res.json();
      } catch (e) { /* the list comes with the next sync, a few seconds from now */ }
      this.items = list.concat(this.unsent);
      if (this.unsent.length) await this.resend();
    },
    // Send the unsent comments, oldest first. True when none are left. One run at a time: two at once would
    // send the same comment twice and could drop another from the list.
    resend() {
      const run = () => this.sendUnsent();
      this.sending = (this.sending || Promise.resolve()).then(run, run);
      return this.sending;
    },
    async sendUnsent() {
      while (this.unsent.length) {
        const item = this.unsent[0];
        let saved;
        try {
          const res = await fetch("api/feedback", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(item) });
          if (!res.ok) throw new Error(res.status);
          saved = await res.json();
        } catch (e) { break; }
        // The comment as the server saved it carries its number (FB-007): show that from now on.
        const at = this.items.indexOf(item);
        if (at >= 0 && saved && saved.id) this.items[at] = saved;
        if (saved && saved.id) this.store(this.mineKey, [...this.stored(this.mineKey), saved.id].slice(-500));
        const i = this.unsent.indexOf(item);
        if (i >= 0) this.unsent.splice(i, 1);
        this.keepUnsent();
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
        this.keepUnsent();
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
      this.renderPanel();
      this.renderPins();
      custom.draw();
    },
    toggle() {
      this.active = !this.active;
      if (this.active && changes.shown) changes.close();  // one panel at a time
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
      const waiting = this.unsent.includes(c);
      if (waiting || !this.remote) {
        if (!waiting) {  // a saved comment keeps its earlier text; one not yet sent is simply replaced
          const now = new Date().toISOString();
          (c.history = c.history || []).push({ text: c.text, until: now });
          c.edited = now;
        }
        c.text = text;
        if (waiting) this.keepUnsent();
        else this.store(this.key, this.items);
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
        this.keepUnsent();
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
    // The cards' notes follow the page too: a section folded or unfolded marks a comment away or back.
    // `placeOf` gives a comment's place (place.of), worked out once per redraw by renderPins.
    markAway(placeOf = (c) => place.of(c)) {
      document.querySelectorAll("#fb-panel .fb-pick").forEach((card) => {
        const c = this.byKey(card.dataset.fb);
        const text = c ? place.away(c, placeOf(c)) : null;
        let line = card.querySelector(".fb-away");
        if (!text) { if (line) line.remove(); return; }
        if (!line) {
          line = document.createElement("div");
          line.className = "fb-away";
          const meta = card.querySelector(".fb-meta");
          (card.querySelector(".fb-st") || meta).after(line);
        }
        line.textContent = text;
      });
    },
    renderPins() {
      // Each comment's place is looked up on the page once per redraw (redraws run on every resize), then read
      // by the cards' notes and the pins.
      const at = new Map();
      const placeOf = (c) => {
        const key = this.keyOf(c);
        if (!at.has(key)) at.set(key, place.of(c));
        return at.get(key);
      };
      this.markAway(placeOf);
      document.querySelectorAll(".fb-pin, .fb-box:not(.drawing)").forEach((p) => p.remove());
      if (document.body.classList.contains("clean")) return;
      const onSame = {};  // several comments on one thing: their pins sit side by side, not on top of each other
      this.forScreen().forEach((c) => {
        if (placeOf(c) !== "shown") return;  // its card in the panel says why there is no pin
        if (isDone(c) && !this.showDone) return;
        const target = c.element ? place.shown(document.querySelector(`[data-el="${CSS.escape(c.element)}"]`)) : null;
        const rect_ = c.box ? place.box(c) : null;
        if (c.box && !rect_) return;
        const pin = document.createElement("div");
        pin.onclick = () => {  // show the comment this pin stands for
          if (!this.active) this.toggle();
          if (this.mini) { this.mini = false; this.renderPanel(); }
          this.picked = c;
          this.markPicked();
          const row = document.querySelector(`#fb-panel [data-fb="${CSS.escape(this.keyOf(c))}"]`);
          if (!row) return;
          row.scrollIntoView({ block: "nearest" });
          row.classList.remove("flash");
          void row.offsetWidth;  // lets the highlight play again on a second click
          row.classList.add("flash");
        };
        pin.dataset.fbPin = this.keyOf(c);
        const unsent = this.unsent.includes(c);
        pin.className = (unsent ? "fb-pin unsent" : "fb-pin") + (isDone(c) ? " done" : "");
        pin.textContent = this.number(c);
        pin.title = (unsent ? "NOT SAVED YET: " : "") + c.text;
        if (c.box) {  // something new: its box, and the number at its corner
          const b = rect_;
          const frame = document.createElement("div");
          frame.className = (unsent ? "fb-box unsent" : "fb-box") + (isDone(c) ? " done" : "");
          if (c.id) frame.dataset.fbId = c.id;
          frame.title = pin.title;
          Object.assign(frame.style, { left: `${b.x}px`, top: `${b.y}px`, width: `${b.w}px`, height: `${b.h}px` });
          document.body.appendChild(frame);
          pin.style.left = `${b.x + b.w - PIN.boxInFromRight}px`;
          pin.style.top = `${b.y - PIN.boxUpFromTop}px`;
          document.body.appendChild(pin);
          return;
        }
        const rect = target ? target.getBoundingClientRect() : { right: c.x - window.scrollX, top: c.y - window.scrollY };
        const spot = target ? c.element : `${c.x},${c.y}`;
        onSame[spot] = (onSame[spot] || 0) + 1;
        pin.style.left = `${rect.right + window.scrollX - PIN.inFromRight - (onSame[spot] - 1) * PIN.apart}px`;
        pin.style.top = `${rect.top + window.scrollY - PIN.upFromTop}px`;
        document.body.appendChild(pin);
      });
    },
    renderPanel() {
      const panel = document.getElementById("fb-panel");
      // The panel lies over the page: opening it never moves what is on the page, so the pins and boxes drawn on
      // it stay where they were put. (The page used to make room for it, and a box could be drawn mid-move.)
      if (!this.active) { panel.hidden = true; document.getElementById("fb-list").hidden = true; return; }
      panel.hidden = false;
      const list = this.forScreen();
      const about = (c) => [c.author, (byId(S.roles, c.role) || {}).name || c.role, when(c)].filter(Boolean).join(" · ");
      // What a comment is about: one thing, several things a box was drawn around, or something new drawn where
      // there is nothing yet.
      const where = (c) => (Array.isArray(c.elements) && c.elements.length > 1 ? `${c.elements.length} things: ${c.elements.map((e) => nameOf(e)).join(", ")}`
        : c.box ? `New, ${c.element && c.element !== "region:page background" ? `in ${nameOf(c.element)}` : "on this screen"}` : capital(nameOf(c.element)));
      // What became of a comment, in a word the client may read. "Received" only while an assistant is listening.
      const state = (c) => (STATE_WORDS[c.state] && (c.state !== "received" || live.listening) ? `<div class="fb-st ${c.state}">${STATE_WORDS[c.state]}</div>` : "");
      // Edit and Delete for a comment this browser may change while it waits; once it is taken, why not.
      const LOCK = '<svg viewBox="0 0 24 24" width="13" height="13" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><rect x="4" y="11" width="16" height="10" rx="2"/><path d="M8 11V7a4 4 0 0 1 8 0v4"/></svg>';
      const actions = (c) => {
        const can = this.changeable(c);
        const key = esc(this.keyOf(c));
        if (can.may) return `<div class="fb-acts"><button class="fb-act" data-fb-edit="${key}">Edit</button><button class="fb-act destroy" data-fb-remove="${key}">Delete</button></div>`;
        return can.why ? `<div class="fb-locked" title="${esc(can.why)}">${LOCK}<span>${esc(can.why)}</span></div>` : "";
      };
      const note = (c) => { const text = place.away(c); return text ? `<div class="fb-away">${esc(text)}</div>` : ""; };
      // Minimised, the list goes and a Comments button on the bar brings it back: Feedback stays on and nothing
      // covers the page.
      const back = document.getElementById("fb-list");
      back.hidden = !this.mini;
      back.textContent = `Comments \u00B7 ${list.length}`;
      if (this.mini) { panel.hidden = true; return; }
      const follows = (c) => (Array.isArray(c.follows) && c.follows.length ? ` · follows ${c.follows.map(esc).join(", ")}` : "");
      const picked = this.picked ? this.keyOf(this.picked) : null;  // by key: a sync brings fresh copies of the comments
      const card = (c) => `<div class="fb-item fb-pick${this.keyOf(c) === picked ? " on" : ""}${isDone(c) ? " fb-done" : ""}" data-fb="${esc(this.keyOf(c))}" role="button" tabindex="0" title="Show it on the screen"><span class="fb-num${this.unsent.includes(c) ? " unsent" : ""}">${esc(this.number(c))}</span><div class="fb-body"><div class="fb-el">${esc(where(c))}</div><div class="fb-text">${esc(c.text)}</div><div class="fb-meta">${esc(about(c))}${c.edited ? " · edited" : ""}${follows(c)}</div>${state(c)}${note(c)}${actions(c)}</div></div>`;
      const open = list.filter((c) => !isDone(c));
      const done = list.filter(isDone);
      panel.innerHTML = `<div class="fb-panel-head"><span>Feedback on this screen <span class="fb-count">${list.length}</span></span>`
        + `<button class="fb-wc-x" id="fb-mini" type="button" title="Minimise: keep commenting with the list out of the way (Comments on the bar brings it back)" aria-label="Minimise the comments">\u2013</button></div>
        ${open.map(card).join("") || (done.length ? '<p class="fb-empty">Nothing open on this screen. Click anything to comment on it.</p>' : '<p class="fb-empty">No feedback yet. Click anything on the screen to comment on it.</p>')}
        ${done.length ? `<div class="fb-done-head"><span>Done <span class="fb-count">${done.length}</span></span><button type="button" class="fb-act" id="fb-show-done" aria-pressed="${!!this.showDone}">${this.showDone ? "Hide from the screen" : "Show on the screen"}</button></div>${done.map(card).join("")}` : ""}
        ${!this.remote ? `<button class="fb-btn quiet" id="fb-export">Export feedback (${this.items.filter((c) => !c.withdrawn).length})</button>`
          : !this.unsent.length ? `<p class="fb-state ok">Saved to the project folder.</p>`
          : `<div class="fb-warn"><b>${this.unsent.length} comment${this.unsent.length > 1 ? "s" : ""} not saved to the project yet.</b> The mock-up server is not answering. Check that the window that started the mock-up is still open, then try again. The comments are kept in this browser until then.</div>
             <div class="fb-warn-buttons"><button class="fb-btn solid" id="fb-retry">Try again</button><button class="fb-btn quiet" id="fb-export">Export unsaved (${this.unsent.length})</button></div>`}`;
      panel.onclick = (e) => {
        if (e.target.closest("#fb-show-done")) {
          this.showDone = !this.showDone;
          remember("mock-feedback-done", this.showDone ? "1" : "");
          this.renderPanel();
          return this.renderPins();
        }
        if (e.target.closest("#fb-mini")) {
          this.mini = true;
          remember("mock-feedback-mini", "1");
          return this.renderPanel();
        }
        const ed = e.target.closest("[data-fb-edit]"), rm = e.target.closest("[data-fb-remove]");
        const c = ed ? this.byKey(ed.dataset.fbEdit) : rm ? this.byKey(rm.dataset.fbRemove) : null;
        if (ed) return c && this.edit(c);
        if (rm) return c && this.remove(c);
        const picked = e.target.closest(".fb-pick");
        if (picked) this.show(picked.dataset.fb);
      };
      panel.onkeydown = (e) => {
        const card = e.target.closest && e.target.closest(".fb-pick");
        if (card && (e.key === "Enter" || e.key === " ")) { e.preventDefault(); this.show(card.dataset.fb); }
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
    // A comment picked in the panel: its card stays marked, as in What changed, and the thing it is about is
    // brought into view and outlined for a moment: its box, the element, or its pin when it is on neither.
    show(key) {
      const c = this.byKey(key);
      if (!c) return;
      this.picked = c;
      this.markPicked();
      const box = c.id ? document.querySelector(`.fb-box[data-fb-id="${CSS.escape(c.id)}"]`) : null;
      const el = !box && c.element && c.element !== "region:page background" ? document.querySelector(`#app [data-el="${CSS.escape(c.element)}"]`) : null;
      const shown = box || place.shown(el) || document.querySelector(`.fb-pin[data-fb-pin="${CSS.escape(key)}"]`);
      if (!shown) return toast(place.away(c) || "What this comment is about is not on this screen now.");
      shown.scrollIntoView({ block: "center", behavior: "smooth" });
      shown.classList.remove("fb-wc-flash");
      void shown.offsetWidth;  // start the outline again when the same comment is picked twice
      shown.classList.add("fb-wc-flash");
      setTimeout(() => shown.classList.remove("fb-wc-flash"), 2600);
    },
    markPicked() {
      const picked = this.picked ? this.keyOf(this.picked) : null;
      document.querySelectorAll("#fb-panel .fb-pick").forEach((card) => card.classList.toggle("on", card.dataset.fb === picked));
    },
    capture(e) {
      if (this.drew) { this.drew = false; e.preventDefault(); e.stopPropagation(); return; }  // the click that ends a drawn box
      if (!this.active || e.target.closest(".fb-tools,.fb-dialog,.fb-pin,.cw-tag")) return;
      e.preventDefault();
      e.stopPropagation();
      const target = e.target.closest("[data-el]");
      const element = target ? target.dataset.el : "";
      const r = route();
      const earlier = this.earlierOn([element]);
      this.openBox({ title: `Comment on ${nameOf(element)}`, author: true, target, earlier }).then((text) => {
        if (!text) return;
        this.save({ screen: app.dataset.screen, role: r.role || "", element, text, author: localStorage.getItem("mock-author") || "", x: e.pageX, y: e.pageY,
          ...(earlier.some((c) => c.id) ? { follows: earlier.map((c) => c.id).filter(Boolean) } : {}),  // saved comments only: they have a number
          time: new Date().toISOString(), version: P.version, ...(live.stamp ? { build: live.stamp } : {}) });  // the build it was made on, when changes are made during the session
      });
    },
    // A box drawn on the screen (dragging in feedback mode). Drawn around things that are there (fields,
    // buttons, columns …) it is one comment about all of them; drawn where there is nothing, it is for
    // something new: a button, a field, a column. It is kept beside the nearest thing on the screen, so it
    // stays in place when the window changes size or a panel opens, and the area it is in is named as where
    // it goes. A box never picks the page background: only a click comments on that.
    captureBox(drawn, rect) {
      // The things wholly inside the box: the smallest named parts, not the areas around them.
      const PARTS = /^(field|button|column|stat|menu|action|search|filter|cell|tab|title|header|chip|link):/;
      const inside = [...document.querySelectorAll("#app [data-el]")].filter((el) => {
        if (!PARTS.test(el.dataset.el)) return false;
        const at = el.getBoundingClientRect();
        if (!at.width && !at.height) return false;
        const x = at.left + window.scrollX, y = at.top + window.scrollY;
        return x >= rect.x - 2 && y >= rect.y - 2 && x + at.width <= rect.x + rect.w + 2 && y + at.height <= rect.y + rect.h + 2;
      }).filter((el, i, all) => !all.some((other) => other !== el && other.contains(el)));  // a part inside another counts once
      const elements = [...new Set(inside.map((el) => el.dataset.el))];
      if (elements.length) return this.captureMany(drawn, rect, inside, elements);
      // The area it is in names where the new thing goes: the smallest one it lies wholly inside, never the page itself.
      const BACKGROUND = "region:page background";
      const page = (el) => { const a = el.getBoundingClientRect(); return { x: a.left + window.scrollX, y: a.top + window.scrollY, w: a.width, h: a.height }; };
      const all = [...document.querySelectorAll("#app [data-el]")];
      const holders = all.filter((el) => {
        const a = page(el);
        return a.w && a.h && a.x <= rect.x + 1 && a.y <= rect.y + 1 && a.x + a.w >= rect.x + rect.w - 1 && a.y + a.h >= rect.y + rect.h - 1;
      });
      let anchor = holders.filter((el) => el.dataset.el !== BACKGROUND).sort((a, b) => page(a).w * page(a).h - page(b).w * page(b).h)[0];
      if (!anchor) {  // over the edge of everything: the thing under its middle
        drawn.style.visibility = "hidden";
        const under = document.elementFromPoint(rect.x + rect.w / 2 - window.scrollX, rect.y + rect.h / 2 - window.scrollY);
        drawn.style.visibility = "";
        anchor = under && under.closest("#app [data-el]");
        if (anchor && anchor.dataset.el === BACKGROUND) anchor = null;
      }
      const element = anchor ? anchor.dataset.el : "";
      const at = anchor ? anchor.getBoundingClientRect() : null;
      const share = (n) => Math.round(n * 10000) / 10000;
      // Where it stays: beside a thing in the same row (14px left of the New button stays 14px left of it, wherever
      // the toolbar wraps to), else in the same column (14px under the sign-in card stays under it), else the
      // nearest thing; a button, field or column rather than the area around it.
      const gap = (a) => Math.max(0, a.x - (rect.x + rect.w), rect.x - (a.x + a.w)) + Math.max(0, a.y - (rect.y + rect.h), rect.y - (a.y + a.h));
      const overlap = (lo, len, a0, alen) => Math.min(lo + len, a0 + alen) - Math.max(lo, a0);
      const BESIDE = /^(field|button|column|stat|menu|action|search|filter|tab|title|header|chip|link):/;
      const near = all.filter((el) => !holders.includes(el) && el.dataset.el !== BACKGROUND)
        .map((el) => ({ el, a: page(el) })).filter((x) => x.a.w && x.a.h).sort((p, q) => gap(p.a) - gap(q.a));
      const best = (list) => {
        const part = list.find((x) => BESIDE.test(x.el.dataset.el));
        return list[0] && part && gap(part.a) <= gap(list[0].a) + 48 ? part : list[0];
      };
      const row = near.filter((x) => overlap(rect.y, rect.h, x.a.y, x.a.h) >= Math.min(rect.h, x.a.h) / 2 && gap(x.a) <= 240);
      const column = near.filter((x) => overlap(rect.x, rect.w, x.a.x, x.a.w) >= Math.min(rect.w, x.a.w) / 2 && gap(x.a) <= 240);
      const by = best(row) || best(column) || near[0];
      const side = (lo, len, a0, alen) => lo >= a0 + alen ? ["after", Math.round(lo - (a0 + alen))]
        : lo + len <= a0 ? ["before", Math.round(a0 - (lo + len))] : ["from", Math.round(lo - a0)];
      const box = { x: Math.round(rect.x), y: Math.round(rect.y), w: Math.round(rect.w), h: Math.round(rect.h),
        ...(at && at.width && at.height ? { fx: share((rect.x - (at.left + window.scrollX)) / at.width), fy: share((rect.y - (at.top + window.scrollY)) / at.height),
          fw: share(rect.w / at.width), fh: share(rect.h / at.height) } : {}),
        ...(by ? { near: by.el.dataset.el, nearAt: all.filter((el) => el.dataset.el === by.el.dataset.el).indexOf(by.el),
          sx: side(rect.x, rect.w, by.a.x, by.a.w), sy: side(rect.y, rect.h, by.a.y, by.a.h) } : {}) };
      const r = route();
      const named = element && element !== "region:page background";  // the empty page is no place worth naming
      this.openBox({ title: `Something new${named ? ` in ${nameOf(element)}` : " here"}`, ask: "What should go here?", author: true }).then((text) => {
        drawn.remove();
        if (!text) return;
        this.save({ screen: app.dataset.screen, role: r.role || "", element, box, text, author: localStorage.getItem("mock-author") || "",
          x: box.x + box.w, y: box.y, time: new Date().toISOString(), version: P.version, ...(live.stamp ? { build: live.stamp } : {}) });
      });
    },
    // A box drawn around several things: one comment about all of them, each named.
    captureMany(drawn, rect, inside, elements) {
      const r = route();
      const names = elements.map((el) => nameOf(el));
      inside.forEach((el) => el.classList.add("fb-target"));
      const first = inside[0].getBoundingClientRect();
      const box = { x: Math.round(rect.x), y: Math.round(rect.y), w: Math.round(rect.w), h: Math.round(rect.h),
        dx: Math.round(rect.x - (first.left + window.scrollX)), dy: Math.round(rect.y - (first.top + window.scrollY)) };
      const title = elements.length === 1 ? `Comment on ${names[0]}` : `Comment on ${elements.length} things: ${names.join(", ")}`;
      const earlier = this.earlierOn(elements);
      this.openBox({ title, author: true, earlier }).then((text) => {
        inside.forEach((el) => el.classList.remove("fb-target"));
        drawn.remove();
        if (!text) return;
        this.save({ screen: app.dataset.screen, role: r.role || "", element: elements[0], ...(elements.length > 1 ? { elements, box } : {}),
          ...(earlier.some((c) => c.id) ? { follows: earlier.map((c) => c.id).filter(Boolean) } : {}),  // saved comments only: they have a number
          text, author: localStorage.getItem("mock-author") || "", x: box.x + box.w, y: box.y,
          time: new Date().toISOString(), version: P.version, ...(live.stamp ? { build: live.stamp } : {}) });
      });
    },
    // The earlier comments on this screen a new one is a layer on, oldest first: those about the same things,
    // by what they are about, not where they sit. A comment on one thing follows the comments on that thing and
    // the boxes drawn round it; a box round several things follows only the boxes round all of them, not each
    // comment on one of its things (a box round seven figures is not a layer on a comment about one of them).
    earlierOn(elements) {
      return layerOn(this.forScreen(), elements);
    },
    // The comment box: a new comment (with the writer's name and the earlier comments on the same thing), or an
    // earlier one to edit. Resolves to the text, or null when it was closed without saving.
    openBox({ title, text, author, target, save, ask, earlier }) {
      return new Promise((done) => {
        const box = document.createElement("div");
        box.className = "fb-dialog";
        // Earlier comments on the same thing, so a new one builds on them ("now make it smaller", "put it back").
        const before = earlier && earlier.length ? `<div class="fb-earlier"><div class="fb-label">Earlier on this</div>${earlier.map((c) =>
          `<div class="fb-earlier-item"><span class="fb-num">${esc(this.number(c))}</span><span>${esc(c.text)}${STATE_WORDS[c.state] ? ` <span class="fb-earlier-st">\u00B7 ${STATE_WORDS[c.state].toLowerCase()}${c.state === "applied" && c.version ? ` in v${esc(c.version)}` : ""}</span>` : ""}</span></div>`).join("")}</div>` : "";
        box.innerHTML = `<div class="fb-dialog-inner" role="dialog" aria-modal="true" aria-labelledby="fb-title"><div class="fb-title" id="fb-title">${esc(title)}</div>${before}
          <label class="fb-label" for="fb-text">${esc(ask || "What should change?")}</label>
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
  let drawing = null;
  document.addEventListener("mousedown", (e) => {
    if (!feedback.active || e.button !== 0 || e.target.closest(".fb-tools,.fb-dialog,.fb-pin,.cw-tag")) return;
    drawing = { x: e.pageX, y: e.pageY, el: null };
  }, true);
  document.addEventListener("mousemove", (e) => {
    if (!drawing) return;
    const w = Math.abs(e.pageX - drawing.x), h = Math.abs(e.pageY - drawing.y);
    if (!drawing.el && w + h < CLICK_WOBBLE) return;  // a click that wobbled is still a click
    e.preventDefault();
    if (!drawing.el) {
      drawing.el = document.createElement("div");
      drawing.el.className = "fb-box drawing";
      document.body.appendChild(drawing.el);
      document.body.classList.add("fb-drawing");  // nothing under the pointer is marked while a box is drawn
    }
    Object.assign(drawing.el.style, { left: `${Math.min(e.pageX, drawing.x)}px`, top: `${Math.min(e.pageY, drawing.y)}px`, width: `${w}px`, height: `${h}px` });
  }, true);
  document.addEventListener("mouseup", (e) => {
    const d = drawing;
    drawing = null;
    document.body.classList.remove("fb-drawing");
    if (!d || !d.el) return;
    feedback.drew = true;  // the click that follows ends the drawing; it is not a comment on what is under it
    setTimeout(() => { feedback.drew = false; }, 0);
    const rect = { x: Math.min(e.pageX, d.x), y: Math.min(e.pageY, d.y), w: Math.max(Math.abs(e.pageX - d.x), 16), h: Math.max(Math.abs(e.pageY - d.y), 16) };
    feedback.captureBox(d.el, rect);
  }, true);
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
  // A phone screen scrolls inside the phone: the pins and tags follow it.
  document.addEventListener("scroll", (e) => { if (screenKind.phone && e.target && e.target.id === "content") { feedback.renderPins(); custom.draw(); } }, true);
  // The page changing size by itself (a section folded or unfolded, the project's own code run after drawing):
  // the pins and boxes follow, and those of things now hidden or shown again go or come back.
  if (window.ResizeObserver) {
    let queued = false;
    new ResizeObserver(() => {
      if (queued) return;
      queued = true;
      requestAnimationFrame(() => { queued = false; feedback.renderPins(); });
    }).observe(app);
  }

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
    + `<button id="fb-changes-btn" hidden title="What the last update changed: go through it one by one">What changed</button>`
    + `<button id="fb-list" type="button" hidden title="Show the comments on this screen">Comments</button>`
    + `<button id="fb-toggle">Feedback</button></div><div id="fb-panel" hidden></div><div id="fb-changes" hidden></div>`;
  document.body.appendChild(tools);
  // The page keeps room at its bottom for the presenter's tools, so whatever they lie over can be scrolled clear
  // of them: the last buttons of a page (at the bottom right in most themes), the last row of a list and its
  // actions. The room is as tall as the tools are from the bottom of the window, the bar and, in feedback mode,
  // the panel above it however long its list has grown; it follows them as they change (CSS: --fb-room, and
  // --fb-bar-room for a dialog, which only the bar can cover). A fixed room used to leave the open panel lying
  // over the last buttons, which then could neither be clicked nor commented on.
  function makeRoom() {
    const from = (el) => (el && el.getClientRects().length ? Math.max(0, Math.ceil(window.innerHeight - el.getBoundingClientRect().top)) : 0);
    document.documentElement.style.setProperty("--fb-room", `${from(tools)}px`);
    document.documentElement.style.setProperty("--fb-bar-room", `${from(tools.querySelector(".fb-bar"))}px`);
  }
  makeRoom();
  window.addEventListener("resize", makeRoom);
  if (window.ResizeObserver) new ResizeObserver(makeRoom).observe(tools);
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
      // A custom build (BUILD.custom_build): everything is custom work, so nothing is tagged, not even what the
      // project's own code marks with Mockup.custom.
      if (!BUILD.custom_build) app.querySelectorAll("[data-custom]").forEach((el) => {
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


  // ------------------------------------------------------------------ what changed
  // After Update ready the page says what the update changed, worked out by comparing the spec the room was
  // looking at with the new one: screens, fields, buttons, list columns, figures, dialogs, statuses, roles,
  // sample data and the look, and the comments worked in since. Each change can be visited: the screen opens
  // as a role that can see it, and the element is outlined. Previous and Next go through them one by one.
  const BEFORE_KEY = "mock-before";
  // Spec text only the requirements document prints: rewording it changes nothing on a screen.
  const DOC_ONLY = new Set(["description", "caption", "meaning", "scope", "source", "validation", "length", "sort", "access",
    "doc_table", "srs_table", "formula", "tbc", "note", "notes", "priority", "requirements", "history", "date"]);
  const plain = (v) => JSON.stringify(v === undefined ? null : v, (k, x) => (DOC_ONLY.has(k) ? undefined : x));
  const LOOK_WORDS = { theme: "theme", primary_color: "colour", data_colors: "data colours", text_size: "text size", font: "font",
    font_file: "font", corners: "corners", menu: "side menu", header: "top bar", logo: "logo" };
  // The mock-up's own styles and code as served: a change there (a new look, the project's own code) shows too.
  function styleSignature() {
    if (!location.protocol.startsWith("http")) return Promise.resolve("");
    const files = ["assets/theme.css", "assets/look.css", "assets/project.css", "assets/project.js"];
    return Promise.all(files.map((u) => fetch(u, { cache: "no-store" }).then((r) => (r.ok ? r.text() : "")).catch(() => "")))
      .then((texts) => {
        let h = 5381;
        for (const ch of texts.join("\u0000")) h = ((h * 33) ^ ch.charCodeAt(0)) >>> 0;
        return String(h);
      });
  }
  const styleAtOpen = styleSignature();

  function whatChanged(A, B) {
    const out = [];
    const add = (text, where) => out.push({ text, ...(where || {}) });
    const keyed = (list, key) => new Map((list || []).filter((x) => x && x[key] != null).map((x) => [String(x[key]), x]));
    const big = (word) => word[0].toUpperCase() + word.slice(1);
    const pa = A.project || {}, pb = B.project || {};
    const looks = [...new Set(Object.keys(LOOK_WORDS).filter((k) => plain(pa[k]) !== plain(pb[k])).map((k) => LOOK_WORDS[k]))];
    if (looks.length) add(`Look: ${looks.join(", ")}`, { look: true });
    const screensA = keyed(A.screens, "id"), screensB = keyed(B.screens, "id");
    const fieldsOf = (s) => keyed((s.sections || []).flatMap((sec) => (sec && sec.fields) || []), "id");
    const compare = (id, a, b, kind, element, label) => {
      for (const [k, x] of b) {
        const y = a.get(k);
        if (!y) add(`New ${kind}: ${label(x, k)}`, { screen: id, element: element(x, k) });
        else if (plain(y) !== plain(x)) add(`${big(kind)} changed: ${label(x, k)}`, { screen: id, element: element(x, k) });
      }
      for (const [k, y] of a) if (!b.has(k)) add(`${big(kind)} taken out: ${label(y, k)}`, { screen: id });
    };
    for (const [id, s] of screensB) {
      const o = screensA.get(id);
      const name = s.title || id;
      if (!o) { add(`New screen: ${name}`, { screen: id, element: "region:page heading" }); continue; }
      if (plain(o) === plain(s)) continue;
      const before = out.length;
      if (o.title !== s.title) add(`Title: ${o.title} → ${s.title}`, { screen: id, element: `title:${s.title}` });
      compare(id, fieldsOf(o), fieldsOf(s), "field", (f, k) => `field:${k}`, (f, k) => f.label || k);
      compare(id, keyed(o.buttons, "label"), keyed(s.buttons, "label"), "button", (b) => `button:${b.label}`, (b) => b.label);
      compare(id, keyed((o.list || {}).columns, "field"), keyed((s.list || {}).columns, "field"), "column", (c) => `column:${c.label}`, (c, k) => c.label || k);
      compare(id, keyed(o.stats, "label"), keyed(s.stats, "label"), "figure", (x) => `stat:${x.label}`, (x) => x.label);
      if (out.length === before) add(`Changed: ${name}`, { screen: id, element: "region:page heading" });
    }
    for (const [id, s] of screensA) if (!screensB.has(id)) add(`Screen taken out: ${s.title || id}`);
    // A dialog is seen on the screen whose button opens it.
    const host = (dialog) => (B.screens || []).find((s) => [...(s.buttons || []), ...((s.list || {}).actions || [])].some((b) => b && b.dialog === dialog));
    const dialogsA = keyed(A.dialogs, "id"), dialogsB = keyed(B.dialogs, "id");
    for (const [id, d] of dialogsB) {
      const o = dialogsA.get(id), h = host(id);
      if (o && plain(o) === plain(d)) continue;
      add(`${o ? "Dialog changed" : "New dialog"}: ${d.title || id}`, h ? { screen: h.id, dialog: id } : {});
    }
    for (const [id, d] of dialogsA) if (!dialogsB.has(id)) add(`Dialog taken out: ${d.title || id}`);
    const statusesA = keyed(A.statuses, "id"), statusesB = keyed(B.statuses, "id");
    for (const [id, x] of statusesB) {
      const o = statusesA.get(id);
      if (!o) add(`New status: ${x.name || id}`);
      else if (o.name !== x.name) add(`Status renamed: ${o.name} → ${x.name}`);
    }
    for (const [id, x] of statusesA) if (!statusesB.has(id)) add(`Status taken out: ${x.name || id}`);
    const rolesA = keyed(A.roles, "id"), rolesB = keyed(B.roles, "id");
    for (const [id, x] of rolesB) if (!rolesA.has(id)) add(`New role: ${x.name || id}`);
    for (const [id, x] of rolesA) if (!rolesB.has(id)) add(`Role taken out: ${x.name || id}`);
    const lists = new Set([...Object.keys(A.data || {}), ...Object.keys(B.data || {})]);
    for (const name of lists) {
      if (plain((A.data || {})[name]) === plain((B.data || {})[name])) continue;
      const shown = (B.screens || []).find((s) => s.list && s.list.data === name);
      add(`Sample data changed: ${name.replace(/_/g, " ")}`, shown ? { screen: shown.id, element: "region:list" } : {});
    }
    return out;
  }
  window.MockupWhatChanged = whatChanged;  // for the tests

  const screenName = (id) => (byId(S.screens, id) || {}).title || (id === "__flow" ? "Process flow" : id);
  const changes = {
    list: [], at: -1, from: null, to: null, shown: false, doneAtOpen: null,
    dealtWith: () => feedback.items.filter((c) => c.id && isDone(c)).map((c) => c.id),
    remember() {
      // Pressing Update ready: keep what the room was looking at, to compare once the page has reloaded.
      return styleAtOpen.then((style) => {
        // The comments already dealt with when this version was opened: any other comment dealt with by the time
        // the page reloads was worked in since, also one written after the page was opened.
        const done = this.doneAtOpen || [];
        try { sessionStorage.setItem(BEFORE_KEY, JSON.stringify({ spec: SPEC_AS_OPENED, style, done, version: P.version })); } catch (e) { /* too big to keep: no list */ }
      });
    },
    async work() {
      let before;
      try { before = JSON.parse(sessionStorage.getItem(BEFORE_KEY) || "null"); } catch (e) { before = null; }
      sessionStorage.removeItem(BEFORE_KEY);
      if (!before || !before.spec) return;
      const list = whatChanged(JSON.parse(before.spec), JSON.parse(SPEC_AS_OPENED));
      if (before.style && (await styleAtOpen) !== before.style && !list.some((c) => c.look)) list.unshift({ text: "Look: the mock-up's styles", look: true });
      // The comments worked in since: those dealt with now that were not when the page was opened.
      this.withComments(list, feedback.items.filter((c) => c.id && !c.withdrawn && isDone(c) && !(before.done || []).includes(c.id)));
      this.list = list;
      this.from = before.version != null ? `v${before.version}` : null;
      this.to = P.version;
      this.button("What changed");
      if (list.length) this.open();
    },
    // The comments worked in: beside the change on their screen, or as a line of their own.
    withComments(list, done) {
      for (const c of done) {
        const said = { id: c.id, state: c.state };
        const on = list.find((x) => x.screen === c.screen);
        if (on) (on.comments = on.comments || []).push(said);
        else list.push({ text: `“${c.text}”`, screen: c.screen, element: c.element, role: c.role, comments: [said], ...(c.box ? { boxOf: c.id } : {}) });
      }
    },
    button(label) {
      const b = document.getElementById("fb-changes-btn");
      b.textContent = label;
      b.hidden = !this.list.length;
    },
    // A page opened afresh (a reload, someone joining late) never saw Update ready: the bar offers what changed
    // since the earlier mock-up the build names (BUILD.earlier: the live session's first showing of this version,
    // or the version before), with the comments made on that one and dealt with since. Nothing opens by itself.
    sinceEarlier() {
      const e = BUILD.earlier;
      if (!e || !e.spec || typeof e.spec !== "object") return;
      const list = whatChanged(e.spec, JSON.parse(SPEC_AS_OPENED));
      this.withComments(list, feedback.items.filter((c) => c.id && !c.withdrawn && isDone(c) && e.version && String(c.version) === String(e.version)));
      this.list = list;
      this.from = e.label || (e.version ? `v${e.version}` : null);
      this.to = P.version;
      this.button(`What changed since ${this.from || "the last version"}`);
    },
    open() {
      if (feedback.active) feedback.toggle();
      this.shown = true;
      this.mini = false;
      this.draw();
    },
    close() {
      this.shown = false;
      this.draw();
    },
    draw() {
      const panel = document.getElementById("fb-changes");
      // Minimised, the list goes and What changed on the bar brings it back: the screen is all yours.
      panel.hidden = !this.shown || !!this.mini;
      document.getElementById("fb-changes-btn").classList.toggle("on", this.shown && !this.mini);
      if (!this.shown || this.mini) return;
      const n = this.list.length;
      const versions = this.from != null && String(this.from) !== `v${this.to}` ? ` · ${esc(this.from)} → v${esc(this.to)}` : "";
      const where = (c) => (c.screen ? `${screenName(c.screen)}${c.dialog ? " · dialog" : ""}` : c.look ? "Every screen" : "Not on one screen");
      panel.innerHTML = `<div class="fb-panel-head"><span>What changed${versions}</span><span><button class="fb-wc-x" id="wc-mini" type="button" aria-label="Minimise" title="Minimise: What changed on the bar brings it back">\u2013</button><button class="fb-wc-x" id="wc-close" aria-label="Close" title="Close">×</button></span></div>
        ${this.list.map((c, i) => `<button type="button" class="fb-item fb-wc-item${i === this.at ? " on" : ""}" data-wc="${i}" ${c.screen ? "" : "disabled"}><span class="fb-num">${i + 1}</span><span class="fb-body"><span class="fb-text">${esc(c.text)}</span><span class="fb-el">${esc(where(c))}</span>${(c.comments || []).map((x) => `<span class="fb-st ${x.state === "applied" || x.state === "decided" ? x.state : ""}">${esc(x.id)} ${(STATE_WORDS[x.state] || STATE_WORDS.noted).toLowerCase()}</span>`).join("")}</span></button>`).join("")}
        <div class="fb-wc-nav"><button type="button" class="fb-btn quiet" id="wc-prev" ${this.at <= 0 ? "disabled" : ""}>Previous</button><span class="fb-count">${this.at >= 0 ? `${this.at + 1} of ${n}` : `${n} change${n === 1 ? "" : "s"}`}</span><button type="button" class="fb-btn solid" id="wc-next" ${this.at >= n - 1 ? "disabled" : ""}>${this.at < 0 ? "Start" : "Next"}</button></div>`;
      panel.onclick = (e) => {
        const item = e.target.closest("[data-wc]");
        if (item) return this.visit(Number(item.dataset.wc));
        if (e.target.closest("#wc-prev")) return this.step(-1);
        if (e.target.closest("#wc-next")) return this.step(1);
        if (e.target.closest("#wc-close")) return this.close();
        if (e.target.closest("#wc-mini")) { this.mini = true; return this.draw(); }
      };
      const on = panel.querySelector(".fb-wc-item.on");
      if (on) on.scrollIntoView({ block: "nearest" });
    },
    step(by) {
      let i = this.at + by;
      while (i >= 0 && i < this.list.length && !this.list[i].screen) i += by;  // a change on no one screen is read, not visited
      if (i >= 0 && i < this.list.length) this.visit(i);
    },
    visit(i) {
      const c = this.list[i];
      this.at = i;
      this.draw();
      if (!c.screen) return;
      const target = byId(S.screens, c.screen);
      const now = route();
      const role = c.role && target && canSee(target, c.role) ? c.role
        : target && now.role && !canSee(target, now.role) ? (target.roles || [])[0] : now.role;
      go(c.screen, { ...(role ? { role } : {}), ...(c.dialog ? { dialog: c.dialog } : {}) });
      setTimeout(() => {
        // A comment drawn as a box is shown by its box; anything else by its element.
        const box = c.boxOf ? document.querySelector(`.fb-box[data-fb-id="${CSS.escape(c.boxOf)}"]`) : null;
        const el = box || (c.element ? document.querySelector(`#app [data-el="${CSS.escape(c.element)}"]`) : null);
        const shown = el || (c.dialog ? document.querySelector(".modal") : null);
        if (!shown) return;
        shown.scrollIntoView({ block: "center", behavior: "smooth" });
        shown.classList.remove("fb-wc-flash");
        void shown.offsetWidth;  // start the outline again when the same element is visited twice
        shown.classList.add("fb-wc-flash");
        setTimeout(() => shown.classList.remove("fb-wc-flash"), 2600);
      }, 150);
    },
  };
  document.getElementById("fb-changes-btn").onclick = () => (changes.shown && !changes.mini ? changes.close() : changes.open());
  document.getElementById("fb-list").onclick = () => {
    feedback.mini = false;
    remember("mock-feedback-mini", "");
    feedback.renderPanel();
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
  document.getElementById("fb-update").onclick = async () => {
    await changes.remember();
    sessionStorage.setItem("mock-updated", "1");
    location.reload();
  };
  const updated = sessionStorage.getItem("mock-updated");
  sessionStorage.removeItem("mock-updated");
  if (!updated) sessionStorage.removeItem(BEFORE_KEY);

  document.getElementById("fb-reset").onclick = () => demo.reset();
  document.getElementById("fb-custom").checked = custom.shown;
  document.getElementById("fb-custom").onchange = (e) => custom.toggle(e.target.checked);

  Promise.all([feedback.load(), demo.load()]).then(() => {
    changes.doneAtOpen = changes.dealtWith();
    render();
    feedback.refresh();
    follow();
    // After Update ready: say what changed, or that it is the mock-up as the spec is now.
    if (updated) changes.work().then(() => { if (!changes.list.length) toast("Updated: this is the mock-up as the spec is now."); });
    else changes.sinceEarlier();
  });
  setInterval(() => feedback.sync(), 5000);
  setInterval(follow, 2500);
  setInterval(() => demo.poll(), 2500);
})();
