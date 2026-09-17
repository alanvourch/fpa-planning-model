"""Headcount changes flow correctly into salary, taxes, benefits, start dates
and cash. Each test builds a tiny roster so the expected numbers can be
computed by hand."""

import numpy as np
import pandas as pd
import pytest

from model import engine, plan, workforce as wf_mod


def _months(start="2026-09", n=18):
    return wf_mod.month_range(start, n)


def test_single_hire_costs_exactly_the_loaded_salary(assumptions):
    a = assumptions
    months = _months()
    pos = wf_mod.make_positions([{"role": "Senior Software Engineer", "location": "Paris", "start": "2027-01", "origin": "plan"}], a)
    wf = wf_mod.monthly_workforce(pos, months, a, "base", vacancy_allowance=False)
    salary = a.salary("Senior Software Engineer", "Paris")
    tax, ben = a.location_param("Paris", "employer_tax_rate"), a.location_param("Paris", "benefits_rate")
    bonus_pct = a.value("bonus_pct_non_sales")
    assert wf["month"].min() == pd.Period("2027-01", freq="M")        # nothing before the start month
    first = wf[wf["month"] == pd.Period("2027-01", freq="M")].iloc[0]
    monthly = salary / 12
    assert first["salary"] == pytest.approx(monthly)
    assert first["bonus"] == pytest.approx(monthly * bonus_pct)
    assert first["employer_tax"] == pytest.approx((monthly + monthly * bonus_pct) * tax)
    assert first["benefits"] == pytest.approx(monthly * ben)
    assert first["recruiting"] == pytest.approx(salary * a.value("recruiting_cost_pct_salary"))
    assert first["capex"] == pytest.approx(a.value("capex_per_new_hire_usd"))
    later = wf[wf["month"] == pd.Period("2027-06", freq="M")].iloc[0]
    assert later["recruiting"] == 0.0 and later["capex"] == 0.0     # one-time costs only once
    assert later["salary"] == pytest.approx(monthly)                 # no merit in the start year


def test_merit_applies_every_january_after_start(assumptions):
    a = assumptions
    months = _months("2026-09", 18)
    pos = wf_mod.make_positions([{"role": "Software Engineer", "location": "Montreal", "start": "2026-10"}], a)
    wf = wf_mod.monthly_workforce(pos, months, a, "base", vacancy_allowance=False).set_index("month")
    base = a.salary("Software Engineer", "Montreal") / 12
    merit = a.value("merit_increase_pct_jan")
    assert wf.at[pd.Period("2026-12", freq="M"), "salary"] == pytest.approx(base)
    assert wf.at[pd.Period("2027-01", freq="M"), "salary"] == pytest.approx(base * (1 + merit))
    assert wf.at[pd.Period("2028-01", freq="M"), "salary"] == pytest.approx(base * (1 + merit) ** 2)
    # a January starter gets no increase in that same January
    pos = wf_mod.make_positions([{"role": "Software Engineer", "location": "Montreal", "start": "2027-01"}], a)
    wf = wf_mod.monthly_workforce(pos, months, a, "base", vacancy_allowance=False).set_index("month")
    assert wf.at[pd.Period("2027-01", freq="M"), "salary"] == pytest.approx(base)


def test_end_date_stops_cost(assumptions):
    a = assumptions
    months = _months("2026-09", 6)
    pos = wf_mod.make_positions([{"role": "Support Engineer", "location": "Montreal", "start": "2025-01", "end": "2026-11"}], a)
    wf = wf_mod.monthly_workforce(pos, months, a, "base", vacancy_allowance=False)
    assert sorted(str(m) for m in wf["month"]) == ["2026-09", "2026-10"]


def test_sales_roles_have_no_bonus_and_ae_ramp(assumptions):
    a = assumptions
    months = _months("2026-09", 8)
    pos = wf_mod.make_positions([{"role": "Account Executive", "location": "Austin", "start": "2026-10"}], a)
    wf = wf_mod.monthly_workforce(pos, months, a, "base", vacancy_allowance=False)
    assert (wf["bonus"] == 0).all()
    cap = wf_mod.ramped_capacity(wf, "Account Executive", a.value("ae_ramp_months"))
    expected = {"2026-10": 0.0, "2026-11": 0.25, "2026-12": 0.5, "2027-01": 0.75, "2027-02": 1.0, "2027-04": 1.0}
    for k, v in expected.items():
        assert cap[pd.Period(k, freq="M")] == pytest.approx(v)


def test_hiring_plan_delta_flows_to_pnl_and_cash(world, opening, months, decision):
    """Adding one engineer to the phased plan must change EBITDA by exactly that
    seat's loaded cost (plus tooling, software, rent, and recruiting), and
    cash by the same amount plus the equipment capex."""
    a = world["assumptions"]
    roster = world["roster"]
    base = plan.build_plan(a, "base", "phased_commit", roster, opening, months, decision["commit_units"])
    extra = a.hiring_plans[a.hiring_plans["plan_id"] == "phased"].copy()
    new_row = pd.DataFrame([{"plan_id": "phased", "role": "Software Engineer", "location": "Montreal",
                             "start_month": "2027-03", "count": 1, "rationale": "test"}])
    a2 = a.with_override("nrr_annual", a.value("nrr_annual"))  # deep copy
    a2.hiring_plans = pd.concat([a.hiring_plans, new_row], ignore_index=True)
    more = plan.build_plan(a2, "base", "phased_commit", roster, opening, months, decision["commit_units"])
    start = pd.Period("2027-03", freq="M")
    active = [m for m in months if m >= start]
    salary = a.salary("Software Engineer", "Montreal")
    vac = (a.value("attrition_annual") / 12) * a.value("backfill_lag_months")
    expected = 0.0
    for m in active:
        n_jan = 1 if m >= pd.Period("2028-01", freq="M") else 0
        monthly = salary * (1 + a.value("merit_increase_pct_jan")) ** n_jan / 12
        people = monthly * (1 + a.value("bonus_pct_non_sales")) * (1 + a.location_param("Montreal", "employer_tax_rate")) \
            + monthly * a.location_param("Montreal", "benefits_rate")
        people *= (1 - vac)   # the vacancy allowance scales with the base it is applied to
        fte = 1 - vac
        expected += people + fte * (a.value("rd_tooling_per_head_month") + a.value("ga_software_per_employee_month")
                                    + a.location_param("Montreal", "rent_per_head_month_usd"))
    expected += salary * a.value("recruiting_cost_pct_salary")
    d_ebitda = base.pnl["ebitda"].sum() - more.pnl["ebitda"].sum()
    assert d_ebitda == pytest.approx(expected, rel=1e-9)
    d_cash = base.cash["closing_cash"].iloc[-1] - more.cash["closing_cash"].iloc[-1]
    assert d_cash == pytest.approx(expected + a.value("capex_per_new_hire_usd"), rel=1e-9)
    # revenue is untouched by an engineering hire
    assert np.allclose(base.pnl["revenue"], more.pnl["revenue"])


def test_ae_hire_changes_new_logos_only_after_ramp(world, opening, months, decision):
    a = world["assumptions"]
    base = plan.build_plan(a, "base", "hold_ondemand", world["roster"], opening, months)
    a2 = a.with_override("nrr_annual", a.value("nrr_annual"))
    a2.hiring_plans = pd.concat([a.hiring_plans, pd.DataFrame([{"plan_id": "hold_plus", "role": "Account Executive",
                                                                "location": "Austin", "start_month": "2027-01", "count": 1, "rationale": "test"}])], ignore_index=True)
    a2.options.loc["hold_plus"] = a2.options.loc["hold_ondemand"]
    a2.options.at["hold_plus", "hiring_plan"] = "hold_plus"
    more = plan.build_plan(a2, "base", "hold_plus", world["roster"], opening, months)
    diff = (more.arr["new_logos"] - base.arr["new_logos"])
    assert diff.loc[:pd.Period("2027-01", freq="M")].abs().max() == 0.0
    ramp = a.value("ae_ramp_months")
    lpa = a.value("logos_per_ramped_ae_month")
    assert diff[pd.Period("2027-02", freq="M")] == pytest.approx((1 / ramp) * lpa * a.seasonality[2])
    assert diff[pd.Period("2027-06", freq="M")] == pytest.approx(lpa * a.seasonality[6])


def test_engine_rejects_unknown_role_or_bad_dates(assumptions):
    with pytest.raises(KeyError):
        wf_mod.make_positions([{"role": "Wizard", "location": "Paris", "start": "2027-01"}], assumptions)
    with pytest.raises(KeyError):
        wf_mod.make_positions([{"role": "Software Engineer", "location": "Lisbon", "start": "2027-01"}], assumptions)
    with pytest.raises(ValueError):
        wf_mod.make_positions([{"role": "Software Engineer", "location": "Paris", "start": "2027-01", "end": "2026-12"}], assumptions)
    with pytest.raises(ValueError):
        wf_mod.make_positions([{"role": "Software Engineer", "location": "Paris", "start": "2027-01", "count": 0}], assumptions)
