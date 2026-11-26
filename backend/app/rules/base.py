"""Общий интерфейс правил.

Каждое правило — модуль с объектом RULE. Функция evaluate(case, context, params)
возвращает текст объяснения (почему сработало) или None.
Пороги и веса в коде — только стартовые значения для сида таблицы `rules`;
движок всегда передаёт параметры из БД.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import TYPE_CHECKING, Any, Callable, Optional

if TYPE_CHECKING:
    from ..context import Context

Explanation = Optional[str]
Evaluate = Callable[[dict, "Context", dict], Explanation]

SCHEMES: dict[str, str] = {
    "1": "Кэшбэк из комиссии",
    "2": "Фиктивные основания раннего аннуитета",
    "3": "Злоупотребление гарантированным периодом",
    "4": "Выплаты умершим",
    "ОСНС": "Аннуитет ОСНС: завышение и фиктивные события",
    "5": "Зарплатные схемы",
    "6": "Отмывание через выкуп",
    "7": "Чёрнинг агентов",
    "8": "Скрытая болезнь, поддельная смерть",
}


@dataclass(frozen=True)
class RuleSpec:
    id: str
    scheme: str
    products: tuple[str, ...]
    name: str
    weight: int
    params: dict[str, Any]
    action: str
    evaluate: Evaluate
    param_titles: dict[str, str] = field(default_factory=dict)


def days(a: date | None, b: date | None) -> int | None:
    """Число дней от a до b (None, если нет данных)."""
    if a is None or b is None:
        return None
    return (b - a).days


def first_year_surrender(c: dict) -> bool:
    """Договор расторгнут с выкупом в первый год (0–365 дней)."""
    d = days(c.get("contractDate"), c.get("surrenderDate"))
    return d is not None and 0 <= d <= 365


def between(x: float | int | None, lo: float, hi: float) -> bool:
    return x is not None and lo <= x <= hi


def num(x: float | int | None) -> str:
    """Число по-русски: 45 000 000, 4,8."""
    if x is None:
        return "—"
    if float(x).is_integer():
        return f"{int(x):,}".replace(",", " ")
    s = f"{x:,.2f}".rstrip("0").rstrip(".")
    return s.replace(",", " ").replace(".", ",")


def money(x: float | int | None) -> str:
    return f"{num(x)} ₸"
