"""Каталог правил (PRD, 6.2). Порядок списка — порядок вывода в интерфейсе."""
from . import (
    a1_commission,
    a2_agent_spike,
    a3_recent_disability,
    a4_issuer_cluster,
    a5_still_working,
    a6_beneficiary,
    a7_early_death,
    a8_payments_after_death,
    a9_requisites_change,
    n1_salary_scheme,
    n2_laundering,
    n3_shared_card,
    n4_agent_lapse,
    n5_hidden_illness,
    o1_salary_inflation,
    o2_fake_injury,
    o3_loss_vs_diagnosis,
    o4_hire_before_event,
)
from .base import SCHEMES, RuleSpec

ALL_RULES: list[RuleSpec] = [
    m.RULE
    for m in (
        a1_commission, a2_agent_spike, a3_recent_disability, a4_issuer_cluster, a5_still_working,
        a6_beneficiary, a7_early_death, a8_payments_after_death, a9_requisites_change,
        o1_salary_inflation, o2_fake_injury, o3_loss_vs_diagnosis, o4_hire_before_event,
        n1_salary_scheme, n2_laundering, n3_shared_card, n4_agent_lapse, n5_hidden_illness,
    )
]
RULES_BY_ID: dict[str, RuleSpec] = {r.id: r for r in ALL_RULES}

__all__ = ["ALL_RULES", "RULES_BY_ID", "SCHEMES", "RuleSpec"]
