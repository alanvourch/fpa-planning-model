"""The actual-versus-plan bridge ties to the reported variance and recovers
the planted deviations."""

import numpy as np
import pandas as pd
import pytest

from model import bridge as bridge_mod


@pytest.fixture(scope="module")
def bridge(world):
    a, actual, budget = world["assumptions"], world["actual"], world["budget"]
    months = [m for m in budget.months if m <= actual.months[-1]]
    br = bridge_mod.build_bridge(actual, budget, months, a)
    return {"months": months, "components": br, "ytd": bridge_mod.ytd_summary(br, a), "lines": bridge_mod.line_summary(br)}


def test_components_tie_to_ebitda_every_month(world, bridge):
    actual, budget = world["actual"], world["budget"]
    br = bridge["components"]
    for m in bridge["months"]:
        total = br.loc[br["month"] == str(m), "impact"].sum()
        assert total == pytest.approx(actual.pnl.at[m, "ebitda"] - budget.pnl.at[m, "ebitda"], abs=0.005)


def test_components_tie_to_each_line(world, bridge):
    actual, budget = world["actual"], world["budget"]
    br = bridge["components"]
    for m in bridge["months"]:
        for line, g in br[br["month"] == str(m)].groupby("line"):
            sign = 1 if line.startswith("revenue") else -1
            assert g["impact"].sum() == pytest.approx(sign * (actual.pnl.at[m, line] - budget.pnl.at[m, line]), abs=0.005)


def test_ytd_ties_and_every_line_is_covered(world, bridge):
    actual, budget = world["actual"], world["budget"]
    months = bridge["months"]
    ytd = bridge["ytd"]
    assert ytd["impact"].sum() == pytest.approx(actual.pnl.loc[months, "ebitda"].sum() - budget.pnl.loc[months, "ebitda"].sum(), abs=0.01)
    covered = set(bridge["lines"]["line"])
    pnl_lines = {c for c in actual.pnl.columns if c.startswith(("revenue_", "cogs_", "rd_", "sm_", "ga_"))
                 and not c.endswith("_total") and c not in ("cogs",)}
    assert pnl_lines == covered


def test_materiality_rule_matches_assumptions(world, bridge):
    a = world["assumptions"]
    br = bridge["components"]
    abs_floor, pct, override = a.value("materiality_abs_usd"), a.value("materiality_pct"), a.value("materiality_abs_override_usd")
    expected = ((br["impact"].abs() >= abs_floor) & (br["impact"].abs() >= pct * br["budget"].abs())) | (br["impact"].abs() >= override)
    assert (expected == br["material"]).all()


def test_bridge_recovers_planted_deviations(bridge):
    """The six planted stories (model/dataset.py docstring) must show up as
    the right sign in the right component. This is the answer-key test."""
    ytd = bridge["ytd"].set_index(["line", "component"])
    imp = lambda line, comp: ytd.at[(line, comp), "impact"]  # noqa: E731
    assert imp("revenue_platform", "volume") < 0          # 1 and 2: fewer customers (logos and churn)
    assert imp("revenue_platform", "price") > 0           # 3: 6% price rise against 5%
    assert imp("cogs_cloud", "usage") < 0                 # 4: Insights usage step-up
    assert imp("rd_payroll", "headcount") > 0             # 5: late engineering hires
    assert imp("sm_programs", "rate") < 0                 # 6: programmes over budget per logo
    # the cloud usage story is material, and the late hires are material
    assert ytd.at[("cogs_cloud", "usage"), "material"]
    assert ytd.at[("rd_payroll", "headcount"), "material"]
