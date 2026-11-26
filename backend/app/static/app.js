"use strict";

const $ = (s, el = document) => el.querySelector(s);
const $$ = (s, el = document) => [...el.querySelectorAll(s)];
const esc = (v) => String(v ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const fmt = (n) => (n == null || n === "" ? "—" : Number(n).toLocaleString("ru-RU"));
const fmtTs = (s) => (s ? new Date(s).toLocaleString("ru-RU") : "");

let META = null;
const Q = { offset: 0, limit: 100 };

async function api(path, opts = {}) {
  const res = await fetch(path, opts);
  if (!res.ok) {
    let msg = res.statusText;
    try { msg = (await res.json()).detail || msg; } catch (_) {}
    throw new Error(typeof msg === "string" ? msg : JSON.stringify(msg));
  }
  return res.json();
}
const json = (method, body) => ({ method, headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });

function toast(text) {
  const t = $("#toast");
  t.textContent = text;
  t.hidden = false;
  clearTimeout(toast._t);
  toast._t = setTimeout(() => (t.hidden = true), 3000);
}

function scoreBar(score, level) {
  return `<div class="score lvl-${esc(level)}"><div class="track"><div class="fill" style="width:${Math.min(100, score)}%"></div></div><b>${score}</b></div>`;
}
const pill = (level) => `<span class="pill lvl-${esc(level)}">${esc(level)}</span>`;

// ---------- тема ----------
(function theme() {
  let saved = null;
  try { saved = localStorage.getItem("theme"); } catch (_) {}
  if (saved) document.documentElement.dataset.theme = saved;
  $("#theme").onclick = () => {
    const cur = document.documentElement.dataset.theme
      || (matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light");
    const next = cur === "dark" ? "light" : "dark";
    document.documentElement.dataset.theme = next;
    try { localStorage.setItem("theme", next); } catch (_) {}
  };
})();

// ---------- вкладки ----------
const loaders = {};
function showTab(name) {
  $$("#tabs button").forEach((b) => b.classList.toggle("active", b.dataset.tab === name));
  $$(".tab").forEach((t) => t.classList.toggle("active", t.id === `tab-${name}`));
  (loaders[name] || (() => {}))();
}
$$("#tabs button").forEach((b) => (b.onclick = () => showTab(b.dataset.tab)));

async function loadMeta() {
  META = await api("/api/meta");
  const sch = $("#f-scheme");
  if (sch.options.length === 1) {
    for (const [k, v] of Object.entries(META.schemes)) sch.add(new Option(`${k === "ОСНС" ? "ОСНС" : "№" + k} · ${v}`, k));
    for (const s of META.statuses) $("#f-status").add(new Option(s, s));
  }
  const r = META.run;
  $("#run-info").textContent = r
    ? `Последний прогон №${r.id}: ${fmtTs(r.ts)}, дел ${fmt(r.n_cases)}, версия набора правил ${r.ruleset_version}, дата отсчёта окон ${r.as_of || "—"}${r.errors ? `, ошибок правил: ${r.errors}` : ""}.`
    : "Данных пока нет — загрузите файл на вкладке «Данные».";
}

// ---------- сводка ----------
loaders.summary = async () => {
  await loadMeta();
  const s = await api("/api/summary");
  $("#kpis").innerHTML = [
    ["Дел всего", fmt(s.total)],
    ["Высокий риск", fmt(s.high)],
    ["Сумма под высоким риском, ₸", fmt(Math.round(s.high_amount))],
    ["Агентов с делами высокого риска", fmt(s.high_agents)],
  ].map(([l, v]) => `<div class="kpi"><div class="v">${v}</div><div class="l">${l}</div></div>`).join("");
  const max = Math.max(1, ...s.by_scheme.map((x) => x.count));
  $("#scheme-chart").innerHTML = s.by_scheme.map((x) => `
    <div class="row" data-scheme="${esc(x.scheme)}" title="Открыть очередь по схеме">
      <div>${x.scheme === "ОСНС" ? "ОСНС" : "№" + esc(x.scheme)} · ${esc(x.name)}</div>
      <div class="track"><div class="fill" style="width:${(100 * x.count) / max}%"></div></div>
      <div class="n">${x.count}</div>
    </div>`).join("");
  $$("#scheme-chart .row").forEach((r) => (r.onclick = () => {
    $("#f-scheme").value = r.dataset.scheme;
    showTab("queue");
  }));
};

// ---------- очередь ----------
function queueParams() {
  const p = new URLSearchParams();
  const map = { q: "#f-q", product: "#f-product", level: "#f-level", scheme: "#f-scheme", status: "#f-status", assignee: "#f-assignee" };
  for (const [k, sel] of Object.entries(map)) if ($(sel).value) p.set(k, $(sel).value);
  if ($("#f-flagged").checked) p.set("flagged", "true");
  p.set("limit", Q.limit);
  p.set("offset", Q.offset);
  return p;
}
async function loadQueue(append = false) {
  if (!append) Q.offset = 0;
  const data = await api(`/api/cases?${queueParams()}`);
  const rows = data.items.map((r) => `
    <tr class="click" data-id="${esc(r.id)}">
      <td>${esc(r.id)}</td><td>${esc(r.product)}</td><td>${esc(r.client)}</td><td>${esc(r.agent)}</td>
      <td><div class="tags">${r.rules.map((x) => `<span class="tag">${esc(x)}</span>`).join("") || "—"}</div></td>
      <td>${esc(r.status)}${r.assignee ? `<div class="muted">${esc(r.assignee)}</div>` : ""}</td>
      <td>${scoreBar(r.score, r.level)}</td>
    </tr>`).join("");
  const tb = $("#queue tbody");
  tb.innerHTML = append ? tb.innerHTML + rows : rows || `<tr><td colspan="7" class="muted">Нет дел по фильтру</td></tr>`;
  const shown = Q.offset + data.items.length;
  $("#q-total").textContent = `Показано ${shown} из ${data.total}`;
  $("#q-more").hidden = shown >= data.total;
  $$("#queue tbody tr.click").forEach((tr) => (tr.onclick = () => openCase(tr.dataset.id)));
}
loaders.queue = () => loadQueue();
let qTimer;
["#f-q", "#f-assignee"].forEach((s) => $(s).addEventListener("input", () => { clearTimeout(qTimer); qTimer = setTimeout(loadQueue, 250); }));
["#f-product", "#f-level", "#f-scheme", "#f-status", "#f-flagged"].forEach((s) => $(s).addEventListener("change", () => loadQueue()));
$("#q-more").onclick = () => { Q.offset += Q.limit; loadQueue(true); };

// ---------- карточка дела ----------
async function openCase(id) {
  const c = await api(`/api/cases/${encodeURIComponent(id)}`);
  const hits = c.hits.length
    ? c.hits.map((h) => `<div class="hit"><b>${esc(h.rule)}</b> · ${esc(h.name)} · вес ${h.weight} · схема ${esc(h.scheme)}
        <div>${esc(h.explanation)}</div><div class="act">Действие: ${esc(h.action)}</div></div>`).join("")
    : `<p class="muted">Правила не сработали.</p>`;
  const fields = c.fields.map((f) => {
    let v = f.value;
    if (f.type === "bool") v = v === "1" ? "да" : v === "0" ? "нет" : "";
    else if (f.type === "decimal" && v !== "") v = fmt(v);
    return `<dt>${esc(f.title)}</dt><dd>${v === "" ? '<span class="muted">нет данных</span>' : esc(v)}</dd>`;
  }).join("");
  const history = c.history.length
    ? `<ul class="history">${c.history.map((h) => `<li>${fmtTs(h.ts)} · ${esc(h.user)}${h.status ? ` · статус «${esc(h.status)}»` : ""}${h.assignee ? ` · исполнитель ${esc(h.assignee)}` : ""}${h.comment ? ` · ${esc(h.comment)}` : ""}</li>`).join("")}</ul>`
    : `<p class="muted">Пока нет.</p>`;
  $("#case").innerHTML = `
    <div class="case-head"><h2>${esc(c.id)}</h2>${pill(c.level)}<span>балл <b>${c.score}</b></span><span class="muted">${esc(c.product)} · ${esc(c.client)}</span></div>
    <div class="card"><h2>Сработавшие правила</h2>${hits}</div>
    <div class="card"><h2>Решение</h2>
      <form class="status-form" id="status-form">
        <select name="status">${META.statuses.map((s) => `<option${s === c.status ? " selected" : ""}>${esc(s)}</option>`).join("")}</select>
        <input name="assignee" placeholder="Исполнитель" value="${esc(c.assignee || "")}">
        <textarea name="comment" placeholder="Комментарий"></textarea>
        <button>Сохранить</button>
      </form>
    </div>
    <div class="card"><h2>Данные дела</h2><dl class="fields">${fields}</dl></div>
    <div class="card"><h2>История</h2>${history}</div>
    <p class="muted">Результат получен на версии набора правил ${c.run ? c.run.ruleset_version : "—"}.</p>`;
  $("#status-form").onsubmit = async (e) => {
    e.preventDefault();
    const fd = new FormData(e.target);
    try {
      await api(`/api/cases/${encodeURIComponent(id)}/status`, json("PATCH", {
        status: fd.get("status"), assignee: fd.get("assignee"), comment: fd.get("comment") || null,
      }));
      toast("Сохранено");
      openCase(id);
      if ($("#tab-queue").classList.contains("active")) loadQueue();
    } catch (err) { toast(err.message); }
  };
  $("#drawer").hidden = false;
}
$("#drawer-close").onclick = () => ($("#drawer").hidden = true);
$("#drawer").onclick = (e) => { if (e.target.id === "drawer") $("#drawer").hidden = true; };
document.addEventListener("keydown", (e) => { if (e.key === "Escape") $("#drawer").hidden = true; });

// ---------- агенты ----------
loaders.agents = async () => {
  const rows = await api("/api/agents");
  $("#agents tbody").innerHTML = rows.map((a) => `
    <tr class="click" data-agent="${esc(a.agent)}"><td>${esc(a.agent)}</td><td>${a.total}</td><td>${a["ПА"]}</td><td>${a["ОСНС"]}</td><td>${a["НСЖ"]}</td>
    <td>${a.avg_commission_pa ?? "—"}</td><td>${a.nsj_first_year_lapse_pct ?? "—"}</td>
    <td>${a.high ? `<span class="pill lvl-высокий">${a.high}</span>` : 0}</td><td>${a.score_sum}</td></tr>`).join("");
  $$("#agents tbody tr").forEach((tr) => (tr.onclick = () => { $("#f-q").value = tr.dataset.agent; showTab("queue"); }));
};

// ---------- правила ----------
loaders.rules = async () => {
  await loadMeta();
  const f = $("#levels");
  f.high.value = META.levels.high;
  f.medium.value = META.levels.medium;
  const rules = await api("/api/rules");
  $("#rules-list").innerHTML = rules.map((r) => `
    <div class="card rule ${r.enabled ? "" : "off"}" data-id="${esc(r.id)}">
      <div>
        <h3>${esc(r.id)} · ${esc(r.name)}</h3>
        <div class="muted">Схема ${esc(r.scheme)} · ${esc(r.scheme_name || "")} · продукты: ${r.products.map(esc).join(", ")} · версия ${r.version}</div>
        <div class="muted">Действие: ${esc(r.action)}</div>
        <div class="params">
          <label>Вес <input type="number" name="weight" min="0" max="100" value="${r.weight}"></label>
          ${Object.entries(r.params).map(([k, v]) => `<label>${esc(r.param_titles[k] || k)} <input type="number" step="any" min="0" name="p:${esc(k)}" value="${esc(v)}"></label>`).join("")}
        </div>
      </div>
      <div class="actions">
        <label class="chk"><input type="checkbox" name="enabled" ${r.enabled ? "checked" : ""}> включено</label>
        <button class="save">Сохранить</button>
        <button class="ghost reset">По умолчанию</button>
      </div>
    </div>`).join("");
  $$("#rules-list .rule").forEach((el) => {
    const id = el.dataset.id;
    $(".save", el).onclick = async () => {
      const params = {};
      $$("input[name^='p:']", el).forEach((i) => (params[i.name.slice(2)] = Number(i.value)));
      try {
        await api(`/api/rules/${id}`, json("PATCH", { weight: Number($("[name=weight]", el).value), enabled: $("[name=enabled]", el).checked, params }));
        toast(`Правило ${id} сохранено, баллы пересчитаны`);
        loaders.rules();
      } catch (err) { toast(err.message); }
    };
    $(".reset", el).onclick = async () => {
      await api(`/api/rules/${id}/reset`, { method: "POST" });
      toast(`Правило ${id} сброшено`);
      loaders.rules();
    };
  });
  const hist = await api("/api/rules/history");
  $("#rules-history tbody").innerHTML = hist.map((h) => `<tr><td>${fmtTs(h.ts)}</td><td>${esc(h.user)}</td><td>${esc(h.rule)}</td><td>${esc(h.field)}</td><td>${esc(JSON.stringify(h.old))}</td><td>${esc(JSON.stringify(h.new))}</td><td>${h.ruleset_version}</td></tr>`).join("")
    || `<tr><td colspan="7" class="muted">Изменений не было</td></tr>`;
};
$("#levels").onsubmit = async (e) => {
  e.preventDefault();
  try {
    await api("/api/settings/levels", json("PUT", { high: Number(e.target.high.value), medium: Number(e.target.medium.value) }));
    toast("Пороги уровней сохранены");
    loaders.rules();
  } catch (err) { toast(err.message); }
};
$("#reset-all").onclick = async () => {
  if (!confirm("Сбросить веса и параметры всех правил к стартовым значениям?")) return;
  await api("/api/rules/reset", { method: "POST" });
  toast("Все правила сброшены");
  loaders.rules();
};

// ---------- калибровка ----------
loaders.calibration = async () => {
  const rows = await api("/api/calibration");
  $("#calibration tbody").innerHTML = rows.map((r) => `
    <tr><td><b>${esc(r.rule)}</b> ${esc(r.name)}</td><td>${esc(r.scheme)}</td><td>${r.hits}</td><td>${r.confirmed}</td><td>${r.false}</td><td>${r.in_review}</td><td>${r.new}</td>
    <td>${r.precision_pct == null ? "—" : r.precision_pct + "%"}</td></tr>`).join("");
};

// ---------- данные ----------
$("#import-form").onsubmit = async (e) => {
  e.preventDefault();
  const out = $("#import-report");
  try {
    const r = await api("/api/import", { method: "POST", body: new FormData(e.target) });
    out.textContent = [
      `Загружено дел: ${r.loaded}; отклонено строк: ${r.rejected}; всего в витрине: ${r.total_cases}.`,
      r.skipped_columns.length ? `Пропущены лишние столбцы: ${r.skipped_columns.join(", ")}` : "Лишних столбцов нет.",
      r.missing_columns.length ? `Нет в файле (правила по ним не сработают): ${r.missing_columns.join(", ")}` : "",
      r.errors_total ? `Замечания (${r.errors_total}):\n` + r.errors.map((x) => `  строка ${x.row}, ${x.field}: ${x.message}`).join("\n") : "",
    ].filter(Boolean).join("\n");
    out.hidden = false;
    toast("Файл загружен, баллы пересчитаны");
  } catch (err) {
    out.textContent = "Ошибка: " + err.message;
    out.hidden = false;
  }
};
$("#recalc").onclick = async () => {
  const r = await api("/api/recalculate", { method: "POST" });
  toast(`Пересчитано дел: ${r.n_cases}`);
};

// ---------- журнал ----------
loaders.audit = async () => {
  const rows = await api("/api/audit");
  $("#audit tbody").innerHTML = rows.map((r) => `<tr><td>${fmtTs(r.ts)}</td><td>${esc(r.user)}</td><td>${esc(r.action)}</td><td>${esc(r.object)}</td><td class="muted">${esc(r.details ? JSON.stringify(r.details) : "")}</td></tr>`).join("");
};

showTab("summary");
