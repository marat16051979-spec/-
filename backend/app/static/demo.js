"use strict";
/*
 * Демо-режим для GitHub Pages: сервера нет, поэтому Python-код движка
 * (app/*.py) запускается в браузере через Pyodide, а запросы к /api/...
 * перехватываются и передаются в app.demo_bridge.Demo.
 * Включается на *.github.io или с параметром ?demo=1.
 */
(function () {
  const params = new URLSearchParams(location.search);
  const DEMO = location.hostname.endsWith("github.io") || params.has("demo");
  if (!DEMO) return;

  const PYODIDE = "https://cdn.jsdelivr.net/pyodide/v0.26.4/full/";
  const setText = (t) => { const el = document.getElementById("loading-text"); if (el) el.textContent = t; };

  function loadScript(src) {
    return new Promise((resolve, reject) => {
      const s = document.createElement("script");
      s.src = src;
      s.onload = resolve;
      s.onerror = () => reject(new Error("Не удалось загрузить " + src));
      document.head.appendChild(s);
    });
  }

  async function boot() {
    document.getElementById("demo-banner").hidden = false;
    document.getElementById("loading").hidden = false;
    setText("Загрузка Python в браузере…");
    await loadScript(PYODIDE + "pyodide.js");
    const py = await loadPyodide({ indexURL: PYODIDE });
    setText("Установка библиотек (SQLAlchemy, SQLite, openpyxl)…");
    await py.loadPackage(["sqlalchemy", "sqlite3", "micropip"]);
    await py.pyimport("micropip").install("openpyxl");
    setText("Загрузка движка правил…");
    const zip = await (await fetch("app.zip", { cache: "no-cache" })).arrayBuffer();
    py.unpackArchive(zip, "zip", { extractDir: "/home/pyodide" });
    py.runPython("import sys; sys.path.insert(0, '/home/pyodide')");
    const Demo = py.pyimport("app.demo_bridge").Demo;
    const demo = Demo();
    setText("Загрузка демо-данных и расчёт баллов…");
    const sample = new Uint8Array(await (await fetch("sample.csv", { cache: "no-cache" })).arrayBuffer());
    demo.load("sample.csv", sample);
    return { py, demo };
  }

  const ready = boot();
  ready.then(() => { document.getElementById("loading").hidden = true; })
    .catch((e) => { setText("Ошибка запуска демо: " + e.message); console.error(e); });

  const realFetch = window.fetch.bind(window);
  window.fetch = async function (input, opts = {}) {
    const raw = typeof input === "string" ? input : input.url;
    const url = new URL(raw, location.href);
    const apiAt = url.pathname.indexOf("/api/");
    if (apiAt < 0) return realFetch(input, opts);

    const { demo } = await ready;
    const path = url.pathname.slice(apiAt);
    const method = (opts.method || "GET").toUpperCase();
    let body = "", filename = "", data = null;
    if (opts.body instanceof FormData) {
      const file = opts.body.get("file");
      body = JSON.stringify({ mode: opts.body.get("mode") || "replace" });
      if (file) { filename = file.name; data = new Uint8Array(await file.arrayBuffer()); }
    } else if (typeof opts.body === "string") {
      body = opts.body;
    }
    const out = JSON.parse(demo.request(method, path, url.search.slice(1), body, filename, data));
    if (out.file_b64) {
      const bin = Uint8Array.from(atob(out.file_b64), (c) => c.charCodeAt(0));
      return new Response(bin, {
        status: 200,
        headers: { "Content-Type": out.media_type, "Content-Disposition": `attachment; filename=${out.filename}` },
      });
    }
    return new Response(JSON.stringify(out.json), { status: out.status, headers: { "Content-Type": "application/json" } });
  };

  window.apiReady = ready;
})();
