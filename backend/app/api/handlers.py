"""Логика API без привязки к веб-фреймворку.

Эти функции вызывают и FastAPI (app/api/main.py), и демо-версия в браузере
(app/demo_bridge.py через Pyodide). Ошибки — ApiError(статус, текст).
"""
from __future__ import annotations

import csv
import io
import re
from collections import defaultdict
from dataclasses import dataclass
from datetime import date
from typing import Any, Callable

from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import importer, services
from ..fields import FIELD_BY_NAME, format_value
from ..models import AuditLog, Case, CaseEvent, CaseStatus, Result, Rule, RuleChange, STATUSES
from ..rules import RULES_BY_ID, SCHEMES
from ..rules.base import first_year_surrender

COMMON_FIELDS = ["id", "product", "client", "agent", "region", "contractDate", "amount"]
PRODUCT_FIELDS = {
    "ПА": ["commissionPct", "complaint", "basis", "disabilityDate", "disabilityIssuer", "stillWorking",
           "beneficiaryRel", "beneficiaryAddedDays", "deathDate", "paymentsAfterDeath", "requisitesChangedDays"],
    "ОСНС": ["employer", "eventDate", "actDelayDays", "witnesses", "salaryAvg12", "salaryLast", "hireDate",
             "lossPct", "diagnosis", "requisitesChangedDays"],
    "НСЖ": ["employer", "payer", "payerCard", "surrenderDate", "payoutSameAccount", "medUnderwriting",
            "deathDate", "deathAbroad"],
}
AMOUNT_TITLE = {"ПА": "Накопления, ₸", "ОСНС": "Резерв выплат, ₸", "НСЖ": "Премия, ₸"}
EXPORT_COLS = ["id", "product", "client", "agent", "score", "level", "rules", "status"]
EXPORT_TITLES = ["ID", "Продукт", "Клиент", "Агент", "Балл", "Уровень", "Правила", "Статус"]
XLSX_TYPE = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


class ApiError(Exception):
    def __init__(self, status: int, detail: str):
        super().__init__(detail)
        self.status = status
        self.detail = detail


@dataclass
class FileOut:
    content: bytes
    media_type: str
    filename: str


# ---------- общие выборки ----------

def queue_rows(s: Session) -> list[dict]:
    run = services.latest_run(s)
    if run is None:
        return []
    results = {r.case_id: r for r in s.scalars(select(Result).where(Result.run_id == run.id))}
    statuses = {st.case_id: st for st in s.scalars(select(CaseStatus))}
    rows = []
    for c in s.scalars(select(Case)):
        r = results.get(c.id)
        st = statuses.get(c.id)
        rows.append({
            "id": c.id, "product": c.product, "client": c.client, "agent": c.agent,
            "employer": c.employer, "region": c.region, "amount": c.amount,
            "contractDate": c.contractDate.isoformat() if c.contractDate else None,
            "score": r.score if r else 0, "level": r.level if r else "низкий",
            "hits": list(r.hits) if r else [],
            "flags": len(r.hits) if r else 0,
            "schemes": sorted({h["scheme"] for h in r.hits}) if r else [],
            "status": st.status if st else "Новое",
            "assignee": st.assignee if st else None,
        })
    rows.sort(key=lambda x: (-x["score"], -(x["amount"] or 0), x["id"]))
    return rows


# ---------- сводка, очередь, карточка ----------

def meta(s: Session) -> dict:
    run = services.latest_run(s)
    return {
        "schemes": SCHEMES,
        "statuses": list(STATUSES),
        "levels": services.get_levels(s),
        "ruleset_version": services.ruleset_version(s),
        "run": None if run is None else {
            "id": run.id, "ts": run.ts.isoformat() if run.ts else None,
            "ruleset_version": run.ruleset_version, "as_of": run.as_of.isoformat() if run.as_of else None,
            "n_cases": run.n_cases, "errors": len(run.errors or []),
        },
        "fields": [{"name": f.name, "type": f.type, "title": f.title, "choices": list(f.choices)}
                   for f in FIELD_BY_NAME.values()],
    }


def summary(s: Session) -> dict:
    rows = queue_rows(s)
    high = [r for r in rows if r["level"] == "высокий"]
    by_scheme: dict[str, int] = defaultdict(int)
    by_rule: dict[str, int] = defaultdict(int)
    by_level: dict[str, int] = defaultdict(int)
    for r in rows:
        by_level[r["level"]] += 1
        for sc in r["schemes"]:
            by_scheme[sc] += 1
        for h in r["hits"]:
            by_rule[h["rule"]] += 1
    return {
        "total": len(rows),
        "high": len(high),
        "high_amount": sum(r["amount"] or 0 for r in high),
        "high_agents": len({r["agent"] for r in high if r["agent"]}),
        "by_level": dict(by_level),
        "by_scheme": [{"scheme": k, "name": v, "count": by_scheme.get(k, 0)} for k, v in SCHEMES.items()],
        "by_rule": dict(by_rule),
    }


def list_cases(
    s: Session, *, product: str | None = None, level: str | None = None, scheme: str | None = None,
    status: str | None = None, assignee: str | None = None, rule: str | None = None,
    q: str | None = None, flagged: bool = False, limit: int = 100, offset: int = 0,
) -> dict:
    limit = max(1, min(int(limit), 1000))
    offset = max(0, int(offset))
    rows = queue_rows(s)
    if product:
        rows = [r for r in rows if r["product"] == product]
    if level:
        rows = [r for r in rows if r["level"] == level]
    if scheme:
        rows = [r for r in rows if scheme in r["schemes"]]
    if rule:
        rows = [r for r in rows if any(h["rule"] == rule for h in r["hits"])]
    if status:
        rows = [r for r in rows if r["status"] == status]
    if assignee:
        rows = [r for r in rows if (r["assignee"] or "") == assignee]
    if flagged:
        rows = [r for r in rows if r["flags"]]
    if q:
        ql = q.lower()
        rows = [r for r in rows if any(ql in (r[k] or "").lower() for k in ("id", "client", "agent", "employer"))]
    total = len(rows)
    page = rows[offset: offset + limit]
    for r in page:
        r["rules"] = [h["rule"] for h in r.pop("hits")]
    return {"total": total, "items": page}


def get_case(s: Session, case_id: str, user: str) -> dict:
    c = s.get(Case, case_id)
    if c is None:
        raise ApiError(404, "Дело не найдено")
    run = services.latest_run(s)
    res = s.get(Result, (run.id, case_id)) if run else None
    st = services.get_status(s, case_id)
    events = s.scalars(select(CaseEvent).where(CaseEvent.case_id == case_id).order_by(CaseEvent.id)).all()
    services.audit(s, user, "case_view", case_id)
    fields = []
    for n in COMMON_FIELDS + PRODUCT_FIELDS.get(c.product, []):
        f = FIELD_BY_NAME[n]
        title = AMOUNT_TITLE.get(c.product, f.title) if n == "amount" else f.title
        fields.append({"name": n, "title": title, "type": f.type, "value": format_value(getattr(c, n))})
    return {
        "id": c.id, "product": c.product, "client": c.client, "agent": c.agent,
        "fields": fields,
        "score": res.score if res else 0, "level": res.level if res else "низкий",
        "hits": res.hits if res else [],
        "run": {"id": run.id, "ruleset_version": run.ruleset_version} if run else None,
        "status": st.status, "assignee": st.assignee, "comment": st.comment,
        "history": [{"ts": e.ts.isoformat() if e.ts else None, "user": e.user, "status": e.status,
                     "assignee": e.assignee, "comment": e.comment} for e in events],
    }


def patch_status(s: Session, case_id: str, user: str, *, status: str | None = None,
                 assignee: str | None = None, comment: str | None = None) -> dict:
    try:
        st = services.set_status(s, case_id, user, status=status, assignee=assignee, comment=comment)
    except KeyError:
        raise ApiError(404, "Дело не найдено")
    except services.ValidationError as e:
        raise ApiError(422, str(e))
    return {"status": st.status, "assignee": st.assignee, "comment": st.comment}


def agents(s: Session) -> list[dict]:
    rows = queue_rows(s)
    cases = {c.id: c for c in s.scalars(select(Case))}
    agg: dict[str, dict[str, Any]] = {}
    for r in rows:
        a = r["agent"]
        if not a:
            continue
        d = agg.setdefault(a, {"agent": a, "total": 0, "ПА": 0, "ОСНС": 0, "НСЖ": 0, "_comm": [],
                               "_nsj_lapsed": 0, "high": 0, "score_sum": 0})
        c = cases[r["id"]]
        d["total"] += 1
        d[r["product"]] += 1
        if r["product"] == "ПА" and c.commissionPct is not None:
            d["_comm"].append(c.commissionPct)
        if r["product"] == "НСЖ" and first_year_surrender(c.to_dict()):
            d["_nsj_lapsed"] += 1
        if r["level"] == "высокий":
            d["high"] += 1
        d["score_sum"] += r["score"]
    out = []
    for d in agg.values():
        comm = d.pop("_comm")
        lapsed = d.pop("_nsj_lapsed")
        d["avg_commission_pa"] = round(sum(comm) / len(comm), 2) if comm else None
        d["nsj_first_year_lapse_pct"] = round(100 * lapsed / d["НСЖ"], 1) if d["НСЖ"] else None
        out.append(d)
    out.sort(key=lambda x: (-x["high"], -x["score_sum"], x["agent"]))
    return out


# ---------- правила ----------

def rule_out(r: Rule) -> dict:
    spec = RULES_BY_ID[r.id]
    return {
        "id": r.id, "scheme": r.scheme, "scheme_name": SCHEMES.get(r.scheme), "products": r.products,
        "name": r.name, "weight": r.weight, "enabled": r.enabled, "params": r.params,
        "param_titles": spec.param_titles, "action": r.action, "version": r.version,
        "default": {"weight": spec.weight, "params": spec.params},
    }


def list_rules(s: Session) -> list[dict]:
    rules = {r.id: r for r in s.scalars(select(Rule))}
    return [rule_out(rules[rid]) for rid in RULES_BY_ID if rid in rules]


def patch_rule(s: Session, rule_id: str, user: str, *, weight: int | None = None,
               enabled: bool | None = None, params: dict | None = None) -> dict:
    try:
        r = services.update_rule(s, rule_id, user, weight=weight, enabled=enabled, params=params)
    except KeyError:
        raise ApiError(404, "Правило не найдено")
    except services.ValidationError as e:
        raise ApiError(422, str(e))
    return rule_out(r)


def reset_rule(s: Session, rule_id: str, user: str) -> dict:
    if rule_id not in RULES_BY_ID:
        raise ApiError(404, "Правило не найдено")
    return rule_out(services.reset_rule(s, rule_id, user))


def reset_rules(s: Session, user: str) -> dict:
    services.reset_all(s, user)
    return {"ok": True}


def rules_history(s: Session, limit: int = 500) -> list[dict]:
    rows = s.scalars(select(RuleChange).order_by(RuleChange.id.desc()).limit(int(limit))).all()
    return [{"ts": r.ts.isoformat() if r.ts else None, "user": r.user, "rule": r.rule_id, "field": r.field,
             "old": r.old_value, "new": r.new_value, "ruleset_version": r.ruleset_version} for r in rows]


def put_levels(s: Session, user: str, high: int, medium: int) -> dict:
    try:
        return services.update_levels(s, user, high, medium)
    except (services.ValidationError, TypeError, ValueError) as e:
        raise ApiError(422, str(e))


def recalc(s: Session, user: str) -> dict:
    run = services.recalculate(s, user)
    return {"run_id": run.id, "n_cases": run.n_cases, "errors": run.errors}


# ---------- импорт и экспорт ----------

def import_file(s: Session, user: str, filename: str, data: bytes, mode: str = "replace") -> dict:
    if mode not in ("replace", "append"):
        raise ApiError(422, "mode: replace или append")
    try:
        cases, report = importer.parse_file(filename or "", data)
    except importer.ImportFailed as e:
        raise ApiError(422, str(e))
    services.import_cases(s, cases, mode)
    run = services.recalculate(s, user)
    services.audit(s, user, "import", filename, {"mode": mode, **report.as_dict()})
    return {**report.as_dict(), "run_id": run.id, "total_cases": services.count_cases(s)}


def import_template() -> FileOut:
    return FileOut(importer.template_csv(), "text/csv; charset=utf-8", "template.csv")


def export(s: Session, user: str, fmt: str = "csv") -> FileOut:
    if fmt not in ("csv", "xlsx"):
        raise ApiError(422, "fmt: csv или xlsx")
    rows = queue_rows(s)
    for r in rows:
        r["rules"] = ", ".join(f"{h['rule']}: {h['explanation']}" for h in r["hits"])
    services.audit(s, user, "export", fmt, {"rows": len(rows)})
    stamp = date.today().isoformat()
    if fmt == "csv":
        buf = io.StringIO()
        w = csv.writer(buf, delimiter=";", lineterminator="\n")
        w.writerow(EXPORT_TITLES)
        for r in rows:
            w.writerow([r[c] if r[c] is not None else "" for c in EXPORT_COLS])
        return FileOut(("﻿" + buf.getvalue()).encode("utf-8"), "text/csv; charset=utf-8", f"results-{stamp}.csv")
    from openpyxl import Workbook

    wb = Workbook()
    ws = wb.active
    ws.title = "Результаты"
    ws.append(EXPORT_TITLES)
    for r in rows:
        ws.append([r[c] for c in EXPORT_COLS])
    for col, width in zip("ABCDEFGH", (14, 8, 28, 22, 7, 10, 90, 18)):
        ws.column_dimensions[col].width = width
    out = io.BytesIO()
    wb.save(out)
    return FileOut(out.getvalue(), XLSX_TYPE, f"results-{stamp}.xlsx")


# ---------- калибровка и аудит ----------

def calibration(s: Session) -> list[dict]:
    rows = queue_rows(s)
    stats = {rid: {"rule": rid, "name": spec.name, "scheme": spec.scheme, "hits": 0,
                   "confirmed": 0, "false": 0, "in_review": 0, "new": 0}
             for rid, spec in RULES_BY_ID.items()}
    key = {"Подтверждено": "confirmed", "Ложное срабатывание": "false", "В проверке": "in_review", "Новое": "new"}
    for r in rows:
        for h in r["hits"]:
            st = stats[h["rule"]]
            st["hits"] += 1
            st[key.get(r["status"], "new")] += 1
    out = []
    for st in stats.values():
        decided = st["confirmed"] + st["false"]
        st["precision_pct"] = round(100 * st["confirmed"] / decided, 1) if decided else None
        out.append(st)
    return out


def audit_log(s: Session, limit: int = 300) -> list[dict]:
    rows = s.scalars(select(AuditLog).order_by(AuditLog.id.desc()).limit(int(limit))).all()
    return [{"ts": r.ts.isoformat() if r.ts else None, "user": r.user, "action": r.action,
             "object": r.object, "details": r.details} for r in rows]


# ---------- маршрутизатор без фреймворка (для демо в браузере) ----------

def _flag(v: Any) -> bool:
    return str(v).lower() in ("1", "true", "yes", "on")


Handler = Callable[[Session, dict, dict, dict, str], Any]  # (s, path_params, query, body, user)

ROUTES: list[tuple[str, re.Pattern, Handler]] = [
    ("GET", re.compile(r"/api/meta"), lambda s, p, q, b, u: meta(s)),
    ("GET", re.compile(r"/api/summary"), lambda s, p, q, b, u: summary(s)),
    ("GET", re.compile(r"/api/cases"), lambda s, p, q, b, u: list_cases(
        s, product=q.get("product"), level=q.get("level"), scheme=q.get("scheme"), status=q.get("status"),
        assignee=q.get("assignee"), rule=q.get("rule"), q=q.get("q"), flagged=_flag(q.get("flagged", "")),
        limit=q.get("limit", 100), offset=q.get("offset", 0))),
    ("GET", re.compile(r"/api/cases/(?P<id>[^/]+)"), lambda s, p, q, b, u: get_case(s, p["id"], u)),
    ("PATCH", re.compile(r"/api/cases/(?P<id>[^/]+)/status"), lambda s, p, q, b, u: patch_status(
        s, p["id"], u, status=b.get("status"), assignee=b.get("assignee"), comment=b.get("comment"))),
    ("GET", re.compile(r"/api/agents"), lambda s, p, q, b, u: agents(s)),
    ("GET", re.compile(r"/api/rules"), lambda s, p, q, b, u: list_rules(s)),
    ("GET", re.compile(r"/api/rules/history"), lambda s, p, q, b, u: rules_history(s, q.get("limit", 500))),
    ("POST", re.compile(r"/api/rules/reset"), lambda s, p, q, b, u: reset_rules(s, u)),
    ("PATCH", re.compile(r"/api/rules/(?P<id>[^/]+)"), lambda s, p, q, b, u: patch_rule(
        s, p["id"], u, weight=b.get("weight"), enabled=b.get("enabled"), params=b.get("params"))),
    ("POST", re.compile(r"/api/rules/(?P<id>[^/]+)/reset"), lambda s, p, q, b, u: reset_rule(s, p["id"], u)),
    ("PUT", re.compile(r"/api/settings/levels"), lambda s, p, q, b, u: put_levels(
        s, u, b.get("high"), b.get("medium"))),
    ("POST", re.compile(r"/api/recalculate"), lambda s, p, q, b, u: recalc(s, u)),
    ("POST", re.compile(r"/api/import"), lambda s, p, q, b, u: import_file(
        s, u, b.get("filename", ""), b.get("data", b""), b.get("mode", "replace"))),
    ("GET", re.compile(r"/api/import/template"), lambda s, p, q, b, u: import_template()),
    ("GET", re.compile(r"/api/export"), lambda s, p, q, b, u: export(s, u, q.get("fmt", "csv"))),
    ("GET", re.compile(r"/api/calibration"), lambda s, p, q, b, u: calibration(s)),
    ("GET", re.compile(r"/api/audit"), lambda s, p, q, b, u: audit_log(s, q.get("limit", 300))),
]


def dispatch(s: Session, method: str, path: str, query: dict, body: dict, user: str) -> Any:
    """Найти обработчик по методу и пути. Возвращает dict/list или FileOut."""
    for m, pattern, handler in ROUTES:
        if m != method:
            continue
        match = pattern.fullmatch(path)
        if match:
            return handler(s, match.groupdict(), query, body, user)
    raise ApiError(404, f"Нет такого метода API: {method} {path}")
