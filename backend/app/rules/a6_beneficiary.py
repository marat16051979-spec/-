"""A6. Схема 3: выгодоприобретатель — посторонний или назначен незадолго до договора."""
from .base import RuleSpec


def evaluate(c, ctx, p):
    reasons = []
    if c.get("beneficiaryRel") == "третье лицо":
        reasons.append("выгодоприобретатель — третье лицо")
    added = c.get("beneficiaryAddedDays")
    if added is not None and added <= int(p["d"]):
        reasons.append(f"назначен за {added} дн. до договора")
    return "; ".join(reasons) or None


RULE = RuleSpec(
    id="A6",
    scheme="3",
    products=("ПА",),
    name="Подозрительный выгодоприобретатель",
    weight=15,
    params={"d": 30},
    param_titles={"d": "Назначен не ранее чем за N дней"},
    action="KYC выгодоприобретателя",
    evaluate=evaluate,
)
