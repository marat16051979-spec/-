"""Операции с БД: сид правил, прогон движка, правка правил, статусы, аудит."""
from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from . import scoring
from .db import Base
from .models import AuditLog, Case, CaseEvent, CaseStatus, Result, Rule, RuleChange, Run, Setting, STATUSES
from .rules import ALL_RULES, RULES_BY_ID

KEEP_RUNS = 10


# ---------- инициализация ----------

def init_db(engine, session_factory) -> None:
    Base.metadata.create_all(engine)
    with session_factory() as s:
        seed(s)
        s.commit()


def seed(s: Session) -> None:
    """Стартовые значения из PRD 6.2: только для отсутствующих правил."""
    existing = {r.id for r in s.scalars(select(Rule))}
    for spec in ALL_RULES:
        if spec.id not in existing:
            s.add(Rule(
                id=spec.id, scheme=spec.scheme, products=list(spec.products), name=spec.name,
                weight=spec.weight, enabled=True, params=dict(spec.params), action=spec.action, version=1,
            ))
    if s.get(Setting, "levels") is None:
        s.add(Setting(key="levels", value=dict(scoring.DEFAULT_LEVELS)))
    if s.get(Setting, "ruleset_version") is None:
        s.add(Setting(key="ruleset_version", value=1))
    s.flush()


# ---------- аудит ----------

def audit(s: Session, user: str, action: str, obj: str | None = None, details: dict | None = None) -> None:
    s.add(AuditLog(user=user, action=action, object=obj, details=details))


# ---------- настройки и версии ----------

def get_levels(s: Session) -> dict:
    st = s.get(Setting, "levels")
    return dict(st.value) if st else dict(scoring.DEFAULT_LEVELS)


def ruleset_version(s: Session) -> int:
    st = s.get(Setting, "ruleset_version")
    return int(st.value) if st else 1


def _bump_version(s: Session) -> int:
    st = s.get(Setting, "ruleset_version")
    st.value = int(st.value) + 1
    return st.value


def load_configs(s: Session) -> list[scoring.RuleConfig]:
    rows = {r.id: r for r in s.scalars(select(Rule))}
    out = []
    for spec in ALL_RULES:
        r = rows.get(spec.id)
        if r is None:
            out.append(scoring.RuleConfig.default(spec.id))
            continue
        out.append(scoring.RuleConfig(
            id=r.id, weight=r.weight, enabled=r.enabled, params=dict(r.params or {}), action=r.action,
            scheme=r.scheme, products=tuple(r.products or spec.products), name=r.name,
        ))
    return out


def ruleset_snapshot(s: Session) -> dict:
    return {
        "version": ruleset_version(s),
        "levels": get_levels(s),
        "rules": [
            {"id": c.id, "weight": c.weight, "enabled": c.enabled, "params": c.params}
            for c in load_configs(s)
        ],
    }


# ---------- дела и прогон ----------

def all_cases(s: Session) -> list[dict]:
    return [c.to_dict() for c in s.scalars(select(Case))]


def import_cases(s: Session, cases: list[dict], mode: str = "replace") -> None:
    if mode == "replace":
        s.execute(delete(Case))
        s.flush()
        s.add_all(Case(**c) for c in cases)
    else:
        for c in cases:
            s.merge(Case(**c))
    s.flush()


def recalculate(s: Session, user: str = "system") -> Run:
    cases = all_cases(s)
    results, ctx, errors = scoring.run(cases, load_configs(s), get_levels(s))
    run = Run(
        ruleset_version=ruleset_version(s), ruleset_snapshot=ruleset_snapshot(s),
        as_of=ctx.as_of, n_cases=len(cases), errors=errors[:500],
    )
    s.add(run)
    s.flush()
    s.bulk_insert_mappings(Result, [
        {"run_id": run.id, "case_id": r.case_id, "score": r.score, "level": r.level, "hits": r.hits}
        for r in results
    ])
    old = s.scalars(select(Run.id).order_by(Run.id.desc()).offset(KEEP_RUNS)).all()
    if old:
        s.execute(delete(Result).where(Result.run_id.in_(old)))
        s.execute(delete(Run).where(Run.id.in_(old)))
    audit(s, user, "recalculate", f"run:{run.id}", {"cases": len(cases), "errors": len(errors)})
    s.flush()
    return run


def latest_run(s: Session) -> Run | None:
    return s.scalars(select(Run).order_by(Run.id.desc()).limit(1)).first()


# ---------- правила ----------

class ValidationError(ValueError):
    pass


def _log_change(s: Session, user: str, rule_id: str, fld: str, old: Any, new: Any, version: int) -> None:
    s.add(RuleChange(user=user, rule_id=rule_id, field=fld, old_value=old, new_value=new, ruleset_version=version))


def update_rule(
    s: Session, rule_id: str, user: str, *,
    weight: int | None = None, enabled: bool | None = None, params: dict | None = None,
) -> Rule:
    rule = s.get(Rule, rule_id)
    if rule is None:
        raise KeyError(rule_id)
    spec = RULES_BY_ID[rule_id]
    changes: list[tuple[str, Any, Any]] = []

    if weight is not None:
        weight = int(weight)
        if not 0 <= weight <= 100:
            raise ValidationError("Вес должен быть от 0 до 100")
        if weight != rule.weight:
            changes.append(("weight", rule.weight, weight))
    if enabled is not None and bool(enabled) != rule.enabled:
        changes.append(("enabled", rule.enabled, bool(enabled)))
    new_params = dict(rule.params or {})
    if params:
        for k, v in params.items():
            if k not in spec.params:
                raise ValidationError(f"У правила {rule_id} нет параметра «{k}»")
            try:
                v = float(v)
            except (TypeError, ValueError) as e:
                raise ValidationError(f"Параметр «{k}» должен быть числом") from e
            if v < 0:
                raise ValidationError(f"Параметр «{k}» не может быть отрицательным")
            v = int(v) if v.is_integer() else v
            if new_params.get(k) != v:
                changes.append((f"params.{k}", new_params.get(k), v))
                new_params[k] = v

    if not changes:
        return rule
    version = _bump_version(s)
    for fld, old, new in changes:
        _log_change(s, user, rule_id, fld, old, new, version)
    if weight is not None:
        rule.weight = weight
    if enabled is not None:
        rule.enabled = bool(enabled)
    rule.params = new_params
    rule.version += 1
    audit(s, user, "rule_update", rule_id, {"changes": [list(c) for c in changes]})
    s.flush()
    recalculate(s, user)
    return rule


def reset_rule(s: Session, rule_id: str, user: str) -> Rule:
    spec = RULES_BY_ID[rule_id]
    return update_rule(s, rule_id, user, weight=spec.weight, enabled=True, params=dict(spec.params))


def reset_all(s: Session, user: str) -> None:
    for spec in ALL_RULES:
        reset_rule(s, spec.id, user)


def update_levels(s: Session, user: str, high: int, medium: int) -> dict:
    high, medium = int(high), int(medium)
    if not 0 < medium < high <= 100:
        raise ValidationError("Нужно 0 < средний < высокий ≤ 100")
    st = s.get(Setting, "levels")
    old = dict(st.value)
    new = {"high": high, "medium": medium}
    if old == new:
        return new
    st.value = new
    version = _bump_version(s)
    _log_change(s, user, "levels", "levels", old, new, version)
    audit(s, user, "levels_update", "levels", {"old": old, "new": new})
    s.flush()
    recalculate(s, user)
    return new


# ---------- статусы ----------

def get_status(s: Session, case_id: str) -> CaseStatus:
    st = s.get(CaseStatus, case_id)
    return st or CaseStatus(case_id=case_id, status="Новое", assignee=None, comment=None)


def set_status(
    s: Session, case_id: str, user: str, *,
    status: str | None = None, assignee: str | None = None, comment: str | None = None,
) -> CaseStatus:
    if s.get(Case, case_id) is None:
        raise KeyError(case_id)
    if status is not None and status not in STATUSES:
        raise ValidationError(f"Статус должен быть одним из: {', '.join(STATUSES)}")
    st = s.get(CaseStatus, case_id)
    if st is None:
        st = CaseStatus(case_id=case_id, status="Новое")
        s.add(st)
    ev = CaseEvent(case_id=case_id, user=user)
    if status is not None and status != st.status:
        st.status = status
        ev.status = status
    if assignee is not None and assignee != (st.assignee or ""):
        st.assignee = assignee or None
        ev.assignee = assignee or "—"
    if comment:
        st.comment = comment
        ev.comment = comment
    st.updated_at = datetime.now()
    if ev.status or ev.assignee or ev.comment:
        s.add(ev)
        audit(s, user, "case_update", case_id, {"status": ev.status, "assignee": ev.assignee, "comment": bool(ev.comment)})
    s.flush()
    return st


def count_cases(s: Session) -> int:
    return s.scalar(select(func.count()).select_from(Case)) or 0
