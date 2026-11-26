"""Юнит-тесты правил: срабатывание, граничное значение, пустые поля (PRD, раздел 11)."""
from datetime import date, timedelta

import pytest

from app.context import Context, Lapse, build_context
from app.fields import FIELD_NAMES
from app.rules import ALL_RULES, RULES_BY_ID
from app.scoring import RuleConfig, evaluate_case, level_for, run, score_hits

D0 = date(2026, 1, 1)


def case(**kw) -> dict:
    c = {n: None for n in FIELD_NAMES}
    c.update({"id": "T-1", **kw})
    return c


def ev(rule_id, c, ctx=None, **params):
    spec = RULES_BY_ID[rule_id]
    return spec.evaluate(c, ctx or Context(), {**spec.params, **params})


def test_catalog_has_18_rules():
    assert len(ALL_RULES) == 18
    assert {r.id for r in ALL_RULES} == {
        "A1", "A2", "A3", "A4", "A5", "A6", "A7", "A8", "A9",
        "O1", "O2", "O3", "O4", "N1", "N2", "N3", "N4", "N5",
    }


@pytest.mark.parametrize("rule", ALL_RULES, ids=lambda r: r.id)
def test_empty_case_never_fires(rule):
    """Пустое значение — «нет данных»: ни одно правило не срабатывает."""
    for product in rule.products:
        assert rule.evaluate(case(product=product), Context(), dict(rule.params)) is None


# ---------- ПА ----------

def test_a1_commission_boundary():
    assert ev("A1", case(commissionPct=4.5)) is not None          # 5 × 90 % = 4,5 — граница включительно
    assert "4,5%" in ev("A1", case(commissionPct=4.5))
    assert ev("A1", case(commissionPct=4.49)) is None
    assert ev("A1", case(commissionPct=1.0, complaint=True)) == "есть жалоба клиента"
    assert ev("A1", case(commissionPct=1.0, complaint=False)) is None
    assert ev("A1", case(commissionPct=4.0), lim=4, sh=100) is not None


def test_a2_agent_spike():
    cases = [case(id=f"P{i}", product="ПА", agent="X", contractDate=D0 - timedelta(days=i * 10)) for i in range(4)]
    cases += [case(id=f"Q{i}", product="ПА", agent=f"Y{i}", contractDate=D0) for i in range(3)]
    params = {"A2": RULES_BY_ID["A2"].params}
    ctx = build_context(cases, params)
    assert ctx.paRecent["X"] == 4 and ctx.paMed == 1
    assert "4 договоров ПА" in ev("A2", cases[0], ctx)
    assert ev("A2", cases[4], ctx) is None                         # у Y0 один договор
    # граница: 3 договора < min = 4
    ctx3 = build_context(cases[1:], params)
    assert ev("A2", cases[1], ctx3) is None
    # договор вне окна не флагуется
    old = case(id="OLD", product="ПА", agent="X", contractDate=D0 - timedelta(days=91))
    ctx_old = build_context(cases + [old], params)
    assert ev("A2", old, ctx_old) is None
    assert ev("A2", case(product="ПА", agent="X"), ctx) is None   # нет даты договора


def test_a3_recent_disability():
    c = case(basis="инвалидность", contractDate=D0, disabilityDate=D0 - timedelta(days=90))
    assert ev("A3", c) == "инвалидность за 90 дн. до договора"
    c["disabilityDate"] = D0 - timedelta(days=91)
    assert ev("A3", c) is None
    c["disabilityDate"] = D0 + timedelta(days=1)                     # после договора — не флаг
    assert ev("A3", c) is None
    assert ev("A3", case(basis="возраст", contractDate=D0, disabilityDate=D0)) is None


def test_a4_issuer_cluster():
    ctx = Context(issuer={"МСЭ-1": 3, "МСЭ-2": 2})
    assert "по 3 договорам" in ev("A4", case(basis="инвалидность", disabilityIssuer="МСЭ-1"), ctx)
    assert ev("A4", case(basis="инвалидность", disabilityIssuer="МСЭ-2"), ctx) is None
    assert ev("A4", case(basis="возраст", disabilityIssuer="МСЭ-1"), ctx) is None


def test_a5_still_working():
    assert ev("A5", case(basis="инвалидность", stillWorking=True)) is not None
    assert ev("A5", case(basis="инвалидность", stillWorking=False)) is None
    assert ev("A5", case(basis="возраст", stillWorking=True)) is None


def test_a6_beneficiary():
    assert ev("A6", case(beneficiaryRel="третье лицо")) == "выгодоприобретатель — третье лицо"
    assert ev("A6", case(beneficiaryRel="родственник", beneficiaryAddedDays=30)) == "назначен за 30 дн. до договора"
    assert ev("A6", case(beneficiaryRel="родственник", beneficiaryAddedDays=31)) is None


def test_a7_early_death():
    assert ev("A7", case(contractDate=D0, deathDate=D0 + timedelta(days=730))) is not None
    assert ev("A7", case(contractDate=D0, deathDate=D0 + timedelta(days=731))) is None
    assert ev("A7", case(contractDate=D0, deathDate=D0 - timedelta(days=1))) is None


def test_a8_payments_after_death():
    assert ev("A8", case(paymentsAfterDeath=1)) is not None
    assert ev("A8", case(paymentsAfterDeath=0)) is None


def test_a9_requisites_change():
    assert ev("A9", case(requisitesChangedDays=60)) is not None
    assert ev("A9", case(requisitesChangedDays=61)) is None
    assert "ОСНС" in RULES_BY_ID["A9"].products


# ---------- ОСНС ----------

def test_o1_salary():
    assert ev("O1", case(salaryAvg12=100_000, salaryLast=150_000)) is not None
    assert ev("O1", case(salaryAvg12=100_000, salaryLast=149_999)) is None
    assert ev("O1", case(salaryAvg12=0, salaryLast=150_000)) is None   # деление на ноль не ломает правило


def test_o2_fake_injury():
    saturday = date(2026, 3, 14)
    monday = date(2026, 3, 16)
    assert ev("O2", case(eventDate=saturday, witnesses=False)) == "признаки: событие в субботу; нет свидетелей"
    assert ev("O2", case(eventDate=saturday, witnesses=True, actDelayDays=10)) is None   # 1 признак, задержка = d
    assert ev("O2", case(eventDate=monday, actDelayDays=11, witnesses=False)) is not None
    assert ev("O2", case(eventDate=saturday), n=1) is not None


def test_o3_loss():
    assert ev("O3", case(lossPct=50, diagnosis="лёгкий")) is not None
    assert ev("O3", case(lossPct=49, diagnosis="лёгкий")) is None
    assert ev("O3", case(lossPct=90, diagnosis="тяжёлый")) is None


def test_o4_hire():
    assert ev("O4", case(hireDate=D0, eventDate=D0 + timedelta(days=30))) is not None
    assert ev("O4", case(hireDate=D0, eventDate=D0 + timedelta(days=31))) is None
    assert ev("O4", case(hireDate=D0 + timedelta(days=5), eventDate=D0)) is None


# ---------- НСЖ ----------

def test_n1_corporate_surrender():
    ctx = Context(corp={"ТОО А": 3, "ТОО Б": 2})
    c = case(employer="ТОО А", contractDate=D0, surrenderDate=D0 + timedelta(days=365))
    assert ev("N1", c, ctx) is not None
    c["surrenderDate"] = D0 + timedelta(days=425)
    assert ev("N1", c, ctx) is not None
    c["surrenderDate"] = D0 + timedelta(days=426)
    assert ev("N1", c, ctx) is None
    c2 = case(employer="ТОО Б", contractDate=D0, surrenderDate=D0 + timedelta(days=370))
    assert ev("N1", c2, ctx) is None


def test_n1_context_counts_window():
    cases = [case(id=f"N{i}", product="НСЖ", employer="ТОО", contractDate=D0,
                  surrenderDate=D0 + timedelta(days=d)) for i, d in enumerate([364, 365, 400, 425, 426])]
    ctx = build_context(cases, {"N1": {"d": 60}})
    assert ctx.corp["ТОО"] == 3


def test_n2_laundering():
    base = dict(amount=10_000_000, contractDate=D0, surrenderDate=D0 + timedelta(days=365))
    assert ev("N2", case(**base, payer="третье лицо")) is not None
    assert ev("N2", case(**base, payer="сам", payoutSameAccount=False)) is not None
    assert ev("N2", case(**base, payer="сам", payoutSameAccount=True)) is None
    assert ev("N2", case(**{**base, "amount": 9_999_999}, payer="третье лицо")) is None
    assert ev("N2", case(**{**base, "surrenderDate": D0 + timedelta(days=366)}, payer="третье лицо")) is None


def test_n3_shared_card():
    cases = [case(id="1", product="НСЖ", client="А", payerCard="K-1"),
             case(id="2", product="НСЖ", client="Б", payerCard="K-1"),
             case(id="3", product="НСЖ", client="В", payerCard="K-2"),
             case(id="4", product="НСЖ", client="В", payerCard="K-2")]   # один клиент — не считается дважды
    ctx = build_context(cases, {})
    assert ev("N3", cases[0], ctx) == "карта K-1 платит за 2 клиентов"
    assert ev("N3", cases[2], ctx) is None


def test_n4_agent_lapse():
    ctx = Context(lapse={"X": Lapse(n=3, lapsed=1), "Y": Lapse(n=2, lapsed=2)})
    first_year = dict(contractDate=D0, surrenderDate=D0 + timedelta(days=200))
    assert ev("N4", case(agent="X", **first_year), ctx) is not None      # 33 % ≥ 30 %
    assert ev("N4", case(agent="X", **first_year), ctx, r=34) is None
    assert ev("N4", case(agent="Y", **first_year), ctx) is None          # мало договоров
    assert ev("N4", case(agent="X", contractDate=D0, surrenderDate=D0 + timedelta(days=366)), ctx) is None


def test_n5_hidden_illness():
    base = dict(contractDate=D0, deathDate=D0 + timedelta(days=730))
    assert ev("N5", case(**base, medUnderwriting=False)) is not None
    assert ev("N5", case(**base, medUnderwriting=True, deathAbroad=True)) is not None
    assert ev("N5", case(**base, medUnderwriting=True, deathAbroad=False)) is None
    assert ev("N5", case(contractDate=D0, deathDate=D0 + timedelta(days=731), medUnderwriting=False)) is None


# ---------- скоринг и движок ----------

def test_score_capped_and_levels():
    assert score_hits([{"weight": 60}, {"weight": 70}]) == 100
    assert level_for(50) == "высокий" and level_for(49) == "средний"
    assert level_for(25) == "средний" and level_for(24) == "низкий"
    assert level_for(30, {"high": 30, "medium": 10}) == "высокий"


def test_rule_applies_only_to_its_products():
    c = case(product="НСЖ", paymentsAfterDeath=3)
    configs = [RuleConfig.default("A8")]
    assert evaluate_case(c, Context(), configs) == []


def test_disabled_rule_and_custom_weight():
    c = case(product="ПА", paymentsAfterDeath=3)
    cfg = RuleConfig.default("A8")
    cfg.weight = 7
    assert evaluate_case(c, Context(), [cfg])[0]["weight"] == 7
    cfg.enabled = False
    assert evaluate_case(c, Context(), [cfg]) == []


def test_rule_error_does_not_stop_run(monkeypatch):
    def boom(c, ctx, p):
        raise RuntimeError("сбой")

    from app.rules.base import RuleSpec

    spec = RULES_BY_ID["A1"]
    monkeypatch.setitem(RULES_BY_ID, "A1", RuleSpec(**{**spec.__dict__, "evaluate": boom}))
    cases = [case(product="ПА", commissionPct=5, paymentsAfterDeath=1)]
    results, _, errors = run(cases)
    assert [h["rule"] for h in results[0].hits] == ["A8"]
    assert errors and errors[0]["rule"] == "A1"
