"""Поля витрины дел (PRD, раздел 5.1) и разбор значений из CSV/XLSX.

Пустое значение — «нет данных» (None). Правило по такому полю не срабатывает.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any

PRODUCTS = ("ПА", "ОСНС", "НСЖ")


@dataclass(frozen=True)
class Field:
    name: str
    type: str  # str | enum | date | decimal | int | bool
    title: str
    choices: tuple[str, ...] = ()


FIELDS: list[Field] = [
    Field("id", "str", "ID дела"),
    Field("product", "enum", "Продукт", PRODUCTS),
    Field("client", "str", "Клиент / застрахованный"),
    Field("agent", "str", "Агент / брокер"),
    Field("region", "str", "Регион"),
    Field("contractDate", "date", "Дата договора"),
    Field("amount", "decimal", "Сумма, ₸"),
    Field("commissionPct", "decimal", "Вознаграждение посредника, %"),
    Field("complaint", "bool", "Есть жалоба клиента"),
    Field("basis", "enum", "Основание ПА", ("возраст", "инвалидность")),
    Field("disabilityDate", "date", "Дата установления инвалидности"),
    Field("disabilityIssuer", "str", "Кто выдал заключение"),
    Field("stillWorking", "bool", "Продолжает работать"),
    Field("beneficiaryRel", "enum", "Выгодоприобретатель", ("родственник", "третье лицо")),
    Field("beneficiaryAddedDays", "int", "Выгодоприобретатель назначен за N дней до договора"),
    Field("deathDate", "date", "Дата смерти"),
    Field("paymentsAfterDeath", "int", "Выплат после даты смерти"),
    Field("requisitesChangedDays", "int", "Реквизиты изменены вручную N дней назад"),
    Field("employer", "str", "Работодатель / корпоративный страхователь"),
    Field("eventDate", "date", "Дата несчастного случая"),
    Field("actDelayDays", "int", "Задержка акта Н-1, дней"),
    Field("witnesses", "bool", "Есть свидетели"),
    Field("salaryAvg12", "decimal", "Средняя зарплата за 12 мес."),
    Field("salaryLast", "decimal", "Зарплата в месяц события"),
    Field("hireDate", "date", "Дата приёма на работу"),
    Field("lossPct", "decimal", "Утрата профтрудоспособности, %"),
    Field("diagnosis", "enum", "Тяжесть диагноза", ("лёгкий", "средний", "тяжёлый")),
    Field("payer", "enum", "Плательщик премии", ("сам", "третье лицо")),
    Field("payerCard", "str", "Карта / счёт плательщика (маска или хэш)"),
    Field("surrenderDate", "date", "Дата расторжения с выкупом"),
    Field("payoutSameAccount", "bool", "Выкуп на счёт плательщика"),
    Field("medUnderwriting", "bool", "Был медицинский андеррайтинг"),
    Field("deathAbroad", "bool", "Смерть за рубежом"),
]

FIELD_BY_NAME = {f.name: f for f in FIELDS}
FIELD_NAMES = [f.name for f in FIELDS]
REQUIRED = ("id", "product")

_TRUE = {"1", "true", "да", "yes", "y", "истина", "д", "+"}
_FALSE = {"0", "false", "нет", "no", "n", "ложь", "н", "-"}


class ParseError(ValueError):
    pass


def _is_empty(v: Any) -> bool:
    return v is None or (isinstance(v, str) and v.strip() == "")


def parse_date(v: Any) -> date | None:
    if _is_empty(v):
        return None
    if isinstance(v, datetime):
        return v.date()
    if isinstance(v, date):
        return v
    s = str(v).strip()
    for fmt in ("%Y-%m-%d", "%d.%m.%Y", "%Y-%m-%d %H:%M:%S", "%d/%m/%Y", "%Y.%m.%d"):
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            continue
    raise ParseError(f"не удалось разобрать дату «{s}»")


def parse_decimal(v: Any) -> float | None:
    if _is_empty(v):
        return None
    if isinstance(v, (int, float)) and not isinstance(v, bool):
        return float(v)
    s = re.sub(r"[\s ₸%]", "", str(v)).replace(",", ".")
    try:
        return float(s)
    except ValueError as e:
        raise ParseError(f"не число «{v}»") from e


def parse_int(v: Any) -> int | None:
    d = parse_decimal(v)
    return None if d is None else int(round(d))


def parse_bool(v: Any) -> bool | None:
    if _is_empty(v):
        return None
    if isinstance(v, bool):
        return v
    if isinstance(v, (int, float)):
        return bool(v)
    s = str(v).strip().lower()
    if s in _TRUE:
        return True
    if s in _FALSE:
        return False
    raise ParseError(f"не логическое значение «{v}»")


def parse_value(field: Field, v: Any) -> Any:
    if field.type == "date":
        return parse_date(v)
    if field.type == "decimal":
        return parse_decimal(v)
    if field.type == "int":
        return parse_int(v)
    if field.type == "bool":
        return parse_bool(v)
    if _is_empty(v):
        return None
    s = str(v).strip()
    if field.type == "enum":
        low = s.lower().replace("ё", "е")
        for c in field.choices:
            if c.lower().replace("ё", "е") == low:
                return c
        raise ParseError(f"недопустимое значение «{s}», ожидается: {', '.join(field.choices)}")
    return s


def format_value(v: Any) -> str:
    """Значение для CSV-выгрузки."""
    if v is None:
        return ""
    if isinstance(v, bool):
        return "1" if v else "0"
    if isinstance(v, date):
        return v.isoformat()
    if isinstance(v, float) and v.is_integer():
        return str(int(v))
    return str(v)
