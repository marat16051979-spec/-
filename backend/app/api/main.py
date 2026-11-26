"""HTTP API (FastAPI) и раздача веб-интерфейса."""
from __future__ import annotations

import csv
import io
from collections import defaultdict
from datetime import date
from pathlib import Path
from typing import Any

from fastapi import Depends, FastAPI, File, Form, HTTPException, Query, Request, UploadFile
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import importer, services
from ..db import make_engine, make_session_factory
from ..fields import FIELD_BY_NAME, format_value
from ..models import AuditLog, Case, CaseEvent, CaseStatus, Result, Rule, RuleChange, STATUSES
from ..rules import RULES_BY_ID, SCHEMES
from ..rules.base import first_year_surrender

STATIC = Path(__file__).resolve().parents[1] / "static"

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


class StatusIn(BaseModel):
    status: str | None = None
    assignee: str | None = None
    comment: str | None = None


class RuleIn(BaseModel):
    weight: int | None = None
    enabled: bool | None = None
    params: dict[str, Any] | None = None


class LevelsIn(BaseModel):
    high: int
    medium: int


def create_app(database_url: str | None = None) -> FastAPI:
    engine = make_engine(database_url)
    SessionLocal = make_session_factory(engine)
    services.init_db(engine, SessionLocal)

    app = FastAPI(title="Антифрод: страхование жизни и аннуитеты", version="0.1.0")
    app.state.engine = engine
    app.state.SessionLocal = SessionLocal

    def get_db():
        with SessionLocal() as s:
            try:
                yield s
                s.commit()
            except Exception:
                s.rollback()
                raise

    def current_user(request: Request) -> str:
        # MVP: один пользователь. В v1 — из SSO/AD.
        return request.headers.get("X-User", "local")

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
                "hits": r.hits if r else [],
                "flags": len(r.hits) if r else 0,
                "schemes": sorted({h["scheme"] for h in r.hits}) if r else [],
                "status": st.status if st else "Новое",
                "assignee": st.assignee if st else None,
            })
        rows.sort(key=lambda x: (-x["score"], -(x["amount"] or 0), x["id"]))
        return rows

    # ---------- API ----------

    @app.get("/api/meta")
    def meta(s: Session = Depends(get_db)):
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

    @app.get("/api/summary")
    def summary(s: Session = Depends(get_db)):
        rows = queue_rows(s)
        high = [r for r in rows if r["level"] == "высокий"]
        by_scheme: dict[str, int] = defaultdict(int)
        by_rule: dict[str, int] = defaultdict(int)
        for r in rows:
            for sc in r["schemes"]:
                by_scheme[sc] += 1
            for h in r["hits"]:
                by_rule[h["rule"]] += 1
        by_level = defaultdict(int)
        for r in rows:
            by_level[r["level"]] += 1
        return {
            "total": len(rows),
            "high": len(high),
            "high_amount": sum(r["amount"] or 0 for r in high),
            "high_agents": len({r["agent"] for r in high if r["agent"]}),
            "by_level": by_level,
            "by_scheme": [{"scheme": k, "name": v, "count": by_scheme.get(k, 0)} for k, v in SCHEMES.items()],
            "by_rule": by_rule,
        }

    @app.get("/api/cases")
    def list_cases(
        s: Session = Depends(get_db),
        product: str | None = None, level: str | None = None, scheme: str | None = None,
        status: str | None = None, assignee: str | None = None, rule: str | None = None,
        q: str | None = None, flagged: bool = False,
        limit: int = Query(100, ge=1, le=1000), offset: int = Query(0, ge=0),
    ):
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

    @app.get("/api/cases/{case_id}")
    def get_case(case_id: str, s: Session = Depends(get_db), user: str = Depends(current_user)):
        c = s.get(Case, case_id)
        if c is None:
            raise HTTPException(404, "Дело не найдено")
        run = services.latest_run(s)
        res = s.get(Result, (run.id, case_id)) if run else None
        st = services.get_status(s, case_id)
        events = s.scalars(select(CaseEvent).where(CaseEvent.case_id == case_id).order_by(CaseEvent.id)).all()
        services.audit(s, user, "case_view", case_id)
        names = COMMON_FIELDS + PRODUCT_FIELDS.get(c.product, [])
        fields = []
        for n in names:
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

    @app.patch("/api/cases/{case_id}/status")
    def patch_status(case_id: str, body: StatusIn, s: Session = Depends(get_db), user: str = Depends(current_user)):
        try:
            st = services.set_status(s, case_id, user, status=body.status, assignee=body.assignee, comment=body.comment)
        except KeyError:
            raise HTTPException(404, "Дело не найдено")
        except services.ValidationError as e:
            raise HTTPException(422, str(e))
        return {"status": st.status, "assignee": st.assignee, "comment": st.comment}

    @app.get("/api/agents")
    def agents(s: Session = Depends(get_db)):
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

    @app.get("/api/rules")
    def list_rules(s: Session = Depends(get_db)):
        rules = {r.id: r for r in s.scalars(select(Rule))}
        return [rule_out(rules[rid]) for rid in RULES_BY_ID if rid in rules]

    @app.patch("/api/rules/{rule_id}")
    def patch_rule(rule_id: str, body: RuleIn, s: Session = Depends(get_db), user: str = Depends(current_user)):
        try:
            r = services.update_rule(s, rule_id, user, weight=body.weight, enabled=body.enabled, params=body.params)
        except KeyError:
            raise HTTPException(404, "Правило не найдено")
        except services.ValidationError as e:
            raise HTTPException(422, str(e))
        return rule_out(r)

    @app.post("/api/rules/{rule_id}/reset")
    def reset_rule(rule_id: str, s: Session = Depends(get_db), user: str = Depends(current_user)):
        if rule_id not in RULES_BY_ID:
            raise HTTPException(404, "Правило не найдено")
        return rule_out(services.reset_rule(s, rule_id, user))

    @app.post("/api/rules/reset")
    def reset_rules(s: Session = Depends(get_db), user: str = Depends(current_user)):
        services.reset_all(s, user)
        return {"ok": True}

    @app.get("/api/rules/history")
    def rules_history(s: Session = Depends(get_db), limit: int = 500):
        rows = s.scalars(select(RuleChange).order_by(RuleChange.id.desc()).limit(limit)).all()
        return [{"ts": r.ts.isoformat() if r.ts else None, "user": r.user, "rule": r.rule_id, "field": r.field,
                 "old": r.old_value, "new": r.new_value, "ruleset_version": r.ruleset_version} for r in rows]

    @app.put("/api/settings/levels")
    def put_levels(body: LevelsIn, s: Session = Depends(get_db), user: str = Depends(current_user)):
        try:
            return services.update_levels(s, user, body.high, body.medium)
        except services.ValidationError as e:
            raise HTTPException(422, str(e))

    @app.post("/api/recalculate")
    def recalc(s: Session = Depends(get_db), user: str = Depends(current_user)):
        run = services.recalculate(s, user)
        return {"run_id": run.id, "n_cases": run.n_cases, "errors": run.errors}

    # ---------- импорт и экспорт ----------

    @app.post("/api/import")
    async def import_file(
        file: UploadFile = File(...), mode: str = Form("replace"),
        s: Session = Depends(get_db), user: str = Depends(current_user),
    ):
        if mode not in ("replace", "append"):
            raise HTTPException(422, "mode: replace или append")
        data = await file.read()
        try:
            cases, report = importer.parse_file(file.filename or "", data)
        except importer.ImportFailed as e:
            raise HTTPException(422, str(e))
        services.import_cases(s, cases, mode)
        run = services.recalculate(s, user)
        services.audit(s, user, "import", file.filename, {"mode": mode, **report.as_dict()})
        return {**report.as_dict(), "run_id": run.id, "total_cases": services.count_cases(s)}

    @app.get("/api/import/template")
    def import_template():
        return Response(importer.template_csv(), media_type="text/csv; charset=utf-8",
                        headers={"Content-Disposition": "attachment; filename=template.csv"})

    EXPORT_COLS = ["id", "product", "client", "agent", "score", "level", "rules", "status"]
    EXPORT_TITLES = ["ID", "Продукт", "Клиент", "Агент", "Балл", "Уровень", "Правила", "Статус"]

    @app.get("/api/export")
    def export(fmt: str = Query("csv", pattern="^(csv|xlsx)$"), s: Session = Depends(get_db),
               user: str = Depends(current_user)):
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
            return Response(("﻿" + buf.getvalue()).encode("utf-8"), media_type="text/csv; charset=utf-8",
                            headers={"Content-Disposition": f"attachment; filename=results-{stamp}.csv"})
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
        return Response(out.getvalue(),
                        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                        headers={"Content-Disposition": f"attachment; filename=results-{stamp}.xlsx"})

    # ---------- калибровка и аудит ----------

    @app.get("/api/calibration")
    def calibration(s: Session = Depends(get_db)):
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

    @app.get("/api/audit")
    def audit_log(s: Session = Depends(get_db), limit: int = 300):
        rows = s.scalars(select(AuditLog).order_by(AuditLog.id.desc()).limit(limit)).all()
        return [{"ts": r.ts.isoformat() if r.ts else None, "user": r.user, "action": r.action,
                 "object": r.object, "details": r.details} for r in rows]

    # ---------- веб-интерфейс ----------

    @app.get("/", include_in_schema=False)
    def index():
        return FileResponse(STATIC / "index.html", headers={"Cache-Control": "no-cache"})

    app.mount("/static", StaticFiles(directory=STATIC), name="static")
    return app
