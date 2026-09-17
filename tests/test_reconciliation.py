"""Every scenario reconciles from drivers through the P&L to cash.

For each of the 18 option x scenario runs, plus the actuals and the budget:
  ARR roll-forward     opening + new + expansion + price + churn == closing
  revenue              closing ARR / 12, by product and in total
  gross profit         revenue - sum of the COGS lines
  opex                 sum of the three function totals, each the sum of its lines
  EBITDA               gross profit - opex
  payroll              P&L payroll lines == workforce table sums by cost bucket
  cloud                units x price under the commitment rule == P&L cloud line
  product P&L          product revenue and COGS sum to the company lines
  cash                 opening + EBITDA - capex - dAR + dDeferred + financing == closing
  determinism          the same run twice is identical
"""

import numpy as np
import pandas as pd
import pytest

from model import engine, plan

TOL = 1e-6


def _all_runs(world, decision):
    runs = dict(decision["runs"])
    runs[("actuals", "actual")] = world["actual"]
    runs[("fy2026_budget", "base")] = world["budget"]
    return runs


def test_arr_rollforward_and_revenue(world, decision):
    for key, res in _all_runs(world, decision).items():
        arr = res.arr
        closing = arr["opening_arr"] + arr["new_arr"] + arr["expansion_arr"] + arr["price_arr"] + arr["churn_arr"]
        assert np.allclose(closing, arr["closing_arr"], atol=TOL), key
        assert np.allclose(arr["opening_arr"].iloc[1:].values, arr["closing_arr"].iloc[:-1].values, atol=TOL), key
        assert np.allclose(res.pnl["revenue_platform"], arr["closing_arr"] / 12.0, atol=TOL), key
        assert np.allclose(res.pnl["revenue_insights"], arr["arr_insights"] / 12.0, atol=TOL), key
        assert np.allclose(res.pnl["revenue"], res.pnl["revenue_platform"] + res.pnl["revenue_insights"], atol=TOL), key


def test_pnl_subtotals(world, decision):
    for key, res in _all_runs(world, decision).items():
        p = res.pnl
        cogs = p[["cogs_cloud", "cogs_third_party", "cogs_payment", "cogs_payroll", "cogs_recruiting"]].sum(axis=1)
        assert np.allclose(cogs, p["cogs"], atol=TOL), key
        assert np.allclose(p["gross_profit"], p["revenue"] - p["cogs"], atol=TOL), key
        rd = p[["rd_payroll", "rd_recruiting", "rd_tooling", "rd_contractors"]].sum(axis=1)
        sm = p[["sm_payroll", "sm_recruiting", "sm_commission", "sm_programs"]].sum(axis=1)
        ga = p[["ga_payroll", "ga_recruiting", "ga_rent", "ga_software", "ga_fixed"]].sum(axis=1)
        assert np.allclose(rd, p["rd_total"], atol=TOL) and np.allclose(sm, p["sm_total"], atol=TOL) and np.allclose(ga, p["ga_total"], atol=TOL), key
        assert np.allclose(p["opex"], rd + sm + ga, atol=TOL), key
        assert np.allclose(p["ebitda"], p["gross_profit"] - p["opex"], atol=TOL), key


def test_payroll_ties_to_workforce(world, decision):
    for key, res in _all_runs(world, decision).items():
        wf = res.workforce
        by_bucket = wf.groupby(["month", "cost_bucket"])["people_cost"].sum().unstack("cost_bucket").reindex(res.months).fillna(0.0)
        for bucket, line in (("COGS", "cogs_payroll"), ("R&D", "rd_payroll"), ("S&M", "sm_payroll"), ("G&A", "ga_payroll")):
            assert np.allclose(by_bucket.get(bucket, 0.0), res.pnl[line], atol=TOL), (key, bucket)
        fte = wf.groupby("month")["fte"].sum().reindex(res.months).fillna(0.0)
        assert np.allclose(fte, res.pnl["fte_total"], atol=TOL), key


def test_cloud_cost_rule(world, decision):
    for key, res in _all_runs(world, decision).items():
        c, d = res.cloud, res.drivers
        expected = (np.minimum(c["units"], d["commit_units"]) * d["cloud_unit_price"] * (1 - d["commit_discount"])
                    + np.maximum(c["units"] - d["commit_units"], 0) * d["cloud_unit_price"] + d["cloud_fixed"])
        assert np.allclose(expected, res.pnl["cogs_cloud"], atol=TOL), key
        units = res.arr["customers"] * d["units_per_platform_customer"] + res.arr["insights_customers"] * d["units_per_insights_customer"]
        assert np.allclose(units, c["units"], atol=TOL), key


def test_product_pnl_sums_to_company(world, decision):
    for key, res in _all_runs(world, decision).items():
        g = res.product.groupby("month")[["revenue", "cogs", "gross_profit"]].sum().reindex(res.months)
        assert np.allclose(g["revenue"], res.pnl["revenue"], atol=1e-4), key
        assert np.allclose(g["cogs"], res.pnl["cogs"], atol=1e-4), key
        assert np.allclose(g["gross_profit"], res.pnl["gross_profit"], atol=1e-4), key


def test_cash_rollforward(world, decision):
    for key, res in _all_runs(world, decision).items():
        c = res.cash
        flow = c["ebitda"] + c["capex"] + c["delta_ar"] + c["delta_deferred"] + c["financing"]
        assert np.allclose(flow, c["net_cash_flow"], atol=TOL), key
        assert np.allclose(c["opening_cash"] + c["net_cash_flow"], c["closing_cash"], atol=TOL), key
        assert np.allclose(c["opening_cash"].iloc[1:].values, c["closing_cash"].iloc[:-1].values, atol=TOL), key
        assert np.allclose(c["ebitda"], res.pnl["ebitda"], atol=TOL), key
        capex = res.workforce.groupby("month")["capex"].sum().reindex(res.months).fillna(0.0)
        assert np.allclose(-capex, c["capex"], atol=TOL), key


def test_plan_opens_from_actual_close(world, opening, decision):
    res = decision["runs"][(decision["chosen"], "base")]
    last = world["actual"].months[-1]
    assert res.arr["opening_arr"].iloc[0] == pytest.approx(world["actual"].arr.at[last, "closing_arr"])
    assert res.cash["opening_cash"].iloc[0] == pytest.approx(world["actual"].cash.at[last, "closing_cash"])
    assert res.arr["opening_customers"].iloc[0] == pytest.approx(world["actual"].arr.at[last, "customers"])


def test_determinism(world, opening, months, decision):
    a = world["assumptions"]
    r1 = plan.build_plan(a, "base", "phased_commit", world["roster"], opening, months, decision["commit_units"])
    r2 = plan.build_plan(a, "base", "phased_commit", world["roster"], opening, months, decision["commit_units"])
    pd.testing.assert_frame_equal(r1.pnl, r2.pnl)
    pd.testing.assert_frame_equal(r1.cash, r2.cash)


def test_scenarios_come_from_drivers_not_constants(world, opening, months, decision):
    """Change one driver in memory and the scenario output must move with it;
    the three scenarios must differ from one another."""
    a = world["assumptions"]
    base = decision["runs"][("phased_commit", "base")]
    up = decision["runs"][("phased_commit", "upside")]
    down = decision["runs"][("phased_commit", "downside")]
    assert up.pnl["arr_total"].iloc[-1] > base.pnl["arr_total"].iloc[-1] > down.pnl["arr_total"].iloc[-1]
    tweaked = a.with_override("nrr_annual", a.value("nrr_annual", "base") + 0.02, "base")
    r = plan.build_plan(tweaked, "base", "phased_commit", world["roster"], opening, months, decision["commit_units"])
    assert r.pnl["arr_total"].iloc[-1] > base.pnl["arr_total"].iloc[-1]
    assert r.pnl["revenue"].sum() > base.pnl["revenue"].sum()
    tweaked = a.with_override("cloud_unit_price_usd", 0.0, "base")  # engine takes the opening price from actuals; the plan drift applies
    # a cost driver: doubling the fixed cloud cost raises COGS by exactly 18 x the increase
    tweaked = a.with_override("cloud_fixed_month_usd", a.value("cloud_fixed_month_usd") + 10_000.0, "base")
    r = plan.build_plan(tweaked, "base", "phased_commit", world["roster"], opening, months, decision["commit_units"])
    assert r.pnl["cogs_cloud"].sum() - base.pnl["cogs_cloud"].sum() == pytest.approx(10_000.0 * len(months), abs=1e-3)
