"""Таблицы БД (PRD, раздел 5)."""
from __future__ import annotations

from datetime import date, datetime
from typing import Any

from sqlalchemy import JSON, Boolean, Date, DateTime, Float, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from .db import Base
from .fields import FIELD_NAMES


class Case(Base):
    """Витрина дел: одна строка — одно дело."""

    __tablename__ = "cases"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    product: Mapped[str] = mapped_column(String(8), index=True)
    client: Mapped[str | None] = mapped_column(String(255))
    agent: Mapped[str | None] = mapped_column(String(255), index=True)
    region: Mapped[str | None] = mapped_column(String(255))
    contractDate: Mapped[date | None] = mapped_column(Date)
    amount: Mapped[float | None] = mapped_column(Float)
    commissionPct: Mapped[float | None] = mapped_column(Float)
    complaint: Mapped[bool | None] = mapped_column(Boolean)
    basis: Mapped[str | None] = mapped_column(String(32))
    disabilityDate: Mapped[date | None] = mapped_column(Date)
    disabilityIssuer: Mapped[str | None] = mapped_column(String(255))
    stillWorking: Mapped[bool | None] = mapped_column(Boolean)
    beneficiaryRel: Mapped[str | None] = mapped_column(String(32))
    beneficiaryAddedDays: Mapped[int | None] = mapped_column(Integer)
    deathDate: Mapped[date | None] = mapped_column(Date)
    paymentsAfterDeath: Mapped[int | None] = mapped_column(Integer)
    requisitesChangedDays: Mapped[int | None] = mapped_column(Integer)
    employer: Mapped[str | None] = mapped_column(String(255), index=True)
    eventDate: Mapped[date | None] = mapped_column(Date)
    actDelayDays: Mapped[int | None] = mapped_column(Integer)
    witnesses: Mapped[bool | None] = mapped_column(Boolean)
    salaryAvg12: Mapped[float | None] = mapped_column(Float)
    salaryLast: Mapped[float | None] = mapped_column(Float)
    hireDate: Mapped[date | None] = mapped_column(Date)
    lossPct: Mapped[float | None] = mapped_column(Float)
    diagnosis: Mapped[str | None] = mapped_column(String(16))
    payer: Mapped[str | None] = mapped_column(String(32))
    payerCard: Mapped[str | None] = mapped_column(String(128))
    surrenderDate: Mapped[date | None] = mapped_column(Date)
    payoutSameAccount: Mapped[bool | None] = mapped_column(Boolean)
    medUnderwriting: Mapped[bool | None] = mapped_column(Boolean)
    deathAbroad: Mapped[bool | None] = mapped_column(Boolean)

    def to_dict(self) -> dict:
        return {n: getattr(self, n) for n in FIELD_NAMES}


class Rule(Base):
    __tablename__ = "rules"

    id: Mapped[str] = mapped_column(String(8), primary_key=True)
    scheme: Mapped[str] = mapped_column(String(16))
    products: Mapped[list] = mapped_column(JSON)
    name: Mapped[str] = mapped_column(String(255))
    weight: Mapped[int] = mapped_column(Integer)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    params: Mapped[dict] = mapped_column(JSON, default=dict)
    action: Mapped[str] = mapped_column(Text)
    version: Mapped[int] = mapped_column(Integer, default=1)


class Setting(Base):
    """Настройки скоринга (пороги уровней) и версия набора правил."""

    __tablename__ = "settings"

    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    value: Mapped[Any] = mapped_column(JSON)


class RuleChange(Base):
    __tablename__ = "rule_changes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    ts: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    user: Mapped[str] = mapped_column(String(128))
    rule_id: Mapped[str] = mapped_column(String(32))
    field: Mapped[str] = mapped_column(String(64))
    old_value: Mapped[Any] = mapped_column(JSON, nullable=True)
    new_value: Mapped[Any] = mapped_column(JSON, nullable=True)
    ruleset_version: Mapped[int] = mapped_column(Integer)


class Run(Base):
    """Прогон движка: на какой версии набора правил получен результат."""

    __tablename__ = "runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    ts: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    ruleset_version: Mapped[int] = mapped_column(Integer)
    ruleset_snapshot: Mapped[dict] = mapped_column(JSON)
    as_of: Mapped[date | None] = mapped_column(Date)
    n_cases: Mapped[int] = mapped_column(Integer, default=0)
    errors: Mapped[list] = mapped_column(JSON, default=list)


class Result(Base):
    __tablename__ = "results"

    run_id: Mapped[int] = mapped_column(ForeignKey("runs.id", ondelete="CASCADE"), primary_key=True)
    case_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    score: Mapped[int] = mapped_column(Integer, index=True)
    level: Mapped[str] = mapped_column(String(16), index=True)
    hits: Mapped[list] = mapped_column(JSON)  # [{rule, scheme, weight, explanation, action}]


class CaseStatus(Base):
    __tablename__ = "case_status"

    case_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    status: Mapped[str] = mapped_column(String(32), default="Новое")
    assignee: Mapped[str | None] = mapped_column(String(128))
    comment: Mapped[str | None] = mapped_column(Text)
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())


class CaseEvent(Base):
    """История дела: смены статуса, исполнителя, комментарии."""

    __tablename__ = "case_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    case_id: Mapped[str] = mapped_column(String(64), index=True)
    ts: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    user: Mapped[str] = mapped_column(String(128))
    status: Mapped[str | None] = mapped_column(String(32))
    assignee: Mapped[str | None] = mapped_column(String(128))
    comment: Mapped[str | None] = mapped_column(Text)


class AuditLog(Base):
    __tablename__ = "audit_log"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    ts: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    user: Mapped[str] = mapped_column(String(128))
    action: Mapped[str] = mapped_column(String(64))
    object: Mapped[str | None] = mapped_column(String(128))
    details: Mapped[dict | None] = mapped_column(JSON, nullable=True)


STATUSES = ("Новое", "В проверке", "Подтверждено", "Ложное срабатывание")
