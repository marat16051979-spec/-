"""HTTP API (FastAPI) и раздача веб-интерфейса. Логика — в handlers.py."""
from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import Depends, FastAPI, File, Form, HTTPException, Query, Request, UploadFile
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from sqlalchemy.orm import Session

from .. import services
from ..db import make_engine, make_session_factory
from . import handlers as h

STATIC = Path(__file__).resolve().parents[1] / "static"


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


def _file(f: h.FileOut) -> Response:
    return Response(f.content, media_type=f.media_type,
                    headers={"Content-Disposition": f"attachment; filename={f.filename}"})


def create_app(database_url: str | None = None) -> FastAPI:
    engine = make_engine(database_url)
    SessionLocal = make_session_factory(engine)
    services.init_db(engine, SessionLocal)

    app = FastAPI(title="Антифрод: страхование жизни и аннуитеты", version="0.1.0")
    app.state.engine = engine
    app.state.SessionLocal = SessionLocal

    @app.exception_handler(h.ApiError)
    async def _api_error(request: Request, exc: h.ApiError):
        from fastapi.responses import JSONResponse

        return JSONResponse({"detail": exc.detail}, status_code=exc.status)

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

    @app.get("/api/meta")
    def meta(s: Session = Depends(get_db)):
        return h.meta(s)

    @app.get("/api/summary")
    def summary(s: Session = Depends(get_db)):
        return h.summary(s)

    @app.get("/api/cases")
    def list_cases(
        s: Session = Depends(get_db),
        product: str | None = None, level: str | None = None, scheme: str | None = None,
        status: str | None = None, assignee: str | None = None, rule: str | None = None,
        q: str | None = None, flagged: bool = False,
        limit: int = Query(100, ge=1, le=1000), offset: int = Query(0, ge=0),
    ):
        return h.list_cases(s, product=product, level=level, scheme=scheme, status=status, assignee=assignee,
                            rule=rule, q=q, flagged=flagged, limit=limit, offset=offset)

    @app.get("/api/cases/{case_id}")
    def get_case(case_id: str, s: Session = Depends(get_db), user: str = Depends(current_user)):
        return h.get_case(s, case_id, user)

    @app.patch("/api/cases/{case_id}/status")
    def patch_status(case_id: str, body: StatusIn, s: Session = Depends(get_db), user: str = Depends(current_user)):
        return h.patch_status(s, case_id, user, status=body.status, assignee=body.assignee, comment=body.comment)

    @app.get("/api/agents")
    def agents(s: Session = Depends(get_db)):
        return h.agents(s)

    @app.get("/api/rules")
    def list_rules(s: Session = Depends(get_db)):
        return h.list_rules(s)

    @app.patch("/api/rules/{rule_id}")
    def patch_rule(rule_id: str, body: RuleIn, s: Session = Depends(get_db), user: str = Depends(current_user)):
        return h.patch_rule(s, rule_id, user, weight=body.weight, enabled=body.enabled, params=body.params)

    @app.post("/api/rules/reset")
    def reset_rules(s: Session = Depends(get_db), user: str = Depends(current_user)):
        return h.reset_rules(s, user)

    @app.post("/api/rules/{rule_id}/reset")
    def reset_rule(rule_id: str, s: Session = Depends(get_db), user: str = Depends(current_user)):
        return h.reset_rule(s, rule_id, user)

    @app.get("/api/rules/history")
    def rules_history(s: Session = Depends(get_db), limit: int = 500):
        return h.rules_history(s, limit)

    @app.put("/api/settings/levels")
    def put_levels(body: LevelsIn, s: Session = Depends(get_db), user: str = Depends(current_user)):
        return h.put_levels(s, user, body.high, body.medium)

    @app.post("/api/recalculate")
    def recalc(s: Session = Depends(get_db), user: str = Depends(current_user)):
        return h.recalc(s, user)

    @app.post("/api/import")
    async def import_file(
        file: UploadFile = File(...), mode: str = Form("replace"),
        s: Session = Depends(get_db), user: str = Depends(current_user),
    ):
        return h.import_file(s, user, file.filename or "", await file.read(), mode)

    @app.get("/api/import/template")
    def import_template():
        return _file(h.import_template())

    @app.get("/api/export")
    def export(fmt: str = Query("csv", pattern="^(csv|xlsx)$"), s: Session = Depends(get_db),
               user: str = Depends(current_user)):
        return _file(h.export(s, user, fmt))

    @app.get("/api/calibration")
    def calibration(s: Session = Depends(get_db)):
        return h.calibration(s)

    @app.get("/api/audit")
    def audit_log(s: Session = Depends(get_db), limit: int = 300):
        return h.audit_log(s, limit)

    @app.get("/", include_in_schema=False)
    def index():
        return FileResponse(STATIC / "index.html", headers={"Cache-Control": "no-cache"})

    app.mount("/static", StaticFiles(directory=STATIC), name="static")
    return app
