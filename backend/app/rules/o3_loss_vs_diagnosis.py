"""O3. ОСНС: высокий процент утраты трудоспособности при лёгком диагнозе."""
from .base import RuleSpec, num


def evaluate(c, ctx, p):
    loss = c.get("lossPct")
    if loss is not None and loss >= float(p["l"]) and c.get("diagnosis") == "лёгкий":
        return f"утрата {num(loss)}% при лёгком диагнозе"
    return None


RULE = RuleSpec(
    id="O3",
    scheme="ОСНС",
    products=("ОСНС",),
    name="Завышенная утрата трудоспособности",
    weight=25,
    params={"l": 50},
    param_titles={"l": "Утрата от, %"},
    action="Независимая медицинская экспертиза; при необходимости — оспаривание в суде",
    evaluate=evaluate,
)
