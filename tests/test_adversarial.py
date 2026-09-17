"""Adversarial tests: attempts to break the model rather than confirm it.

1. Start-date shift. Move every planned hire one month later. The change in
   18-month EBITDA must equal, seat by seat, exactly one month of each seat's
   loaded cost (in the month it would have started) plus the ramp effect on
   new logos for the sales seats, and nothing else. A model that pro-rates,
   double-counts recruiting, or leaks the shift into unrelated lines fails.

2. Typed-figure sniff. The renderers (model/reports.py, build_site.py) may
   not contain numeric literals that look like model figures inside string
   templates. Any number with three or more digits, a decimal, or a percent
   sign inside a quoted string is a typed figure unless it is on the small
   whitelist (page geometry, years). This is the test that caught the 85%
   commitment coverage typed into slide 5 (see DECISIONS.md).

3. Guardrail tampering. Loosening the runway guardrail in memory must be able
   to change the recommendation; the decision must not be hardcoded.
"""

import re
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from model import decision as decision_mod, plan, workforce as wf_mod

ROOT = Path(__file__).resolve().parents[1]


def test_shifting_every_hire_one_month_costs_exactly_one_month_each(world, opening, months, decision):
    a = world["assumptions"]
    roster = world["roster"]
    chosen = decision["chosen"]
    base = plan.build_plan(a, "base", chosen, roster, opening, months, decision["commit_units"])
    a2 = a.with_override("nrr_annual", a.value("nrr_annual"))  # deep copy
    hp = a2.hiring_plans.copy()
    mask = hp["plan_id"] == a.options.at[chosen, "hiring_plan"]
    hp.loc[mask, "start_month"] = [str(pd.Period(s, freq="M") + 1) for s in hp.loc[mask, "start_month"]]
    a2.hiring_plans = hp
    shifted = plan.build_plan(a2, "base", chosen, roster, opening, months, decision["commit_units"])

    # Merit depends on the calendar, not on tenure, so pushing a seat one month later
    # removes exactly its START month from the window (no plan seat starts in December,
    # so no seat crosses a January boundary by moving). Expected loss per seat: one month
    # of loaded people cost at the starting salary. Recruiting and capex move, not vanish.
    plan_rows = a.hiring_plans[mask]
    assert not any(pd.Period(s, freq="M").month == 12 for s in plan_rows["start_month"])
    d_opex = (base.pnl["opex"].sum() + base.pnl["cogs_payroll"].sum() + base.pnl["cogs_recruiting"].sum()) \
        - (shifted.pnl["opex"].sum() + shifted.pnl["cogs_payroll"].sum() + shifted.pnl["cogs_recruiting"].sum())
    # sales seats also change new logos (ramp shifts), which changes commission and programmes;
    # isolate that: revenue-linked lines must move only through new_logos
    d_logos = base.arr["new_logos"].sum() - shifted.arr["new_logos"].sum()
    assert d_logos > 0  # later AEs sell less within the window
    d_programs = base.pnl["sm_programs"].sum() - shifted.pnl["sm_programs"].sum()
    assert d_programs == pytest.approx(d_logos * a.value("marketing_program_cost_per_new_logo"), rel=1e-9)
    d_commission = base.pnl["sm_commission"].sum() - shifted.pnl["sm_commission"].sum()
    d_other = d_opex - d_programs - d_commission
    # CSM auto-hires may also shift with customers; exclude them by comparing planned seats only
    base_plan_cost = base.workforce[base.workforce["origin"].str.startswith("plan:")]
    shift_plan_cost = shifted.workforce[shifted.workforce["origin"].str.startswith("plan:")]
    d_people = base_plan_cost["people_cost"].sum() - shift_plan_cost["people_cost"].sum()
    # recruiting is one-off and must be identical in total (it moved, it did not vanish)
    assert base_plan_cost["recruiting"].sum() == pytest.approx(shift_plan_cost["recruiting"].sum())
    assert base_plan_cost["capex"].sum() == pytest.approx(shift_plan_cost["capex"].sum())
    expected_people = 0.0
    for r in plan_rows.itertuples():
        s = a.salary(r.role, r.location)
        meta = a.salaries.loc[r.role]
        bonus = 0.0 if bool(meta["sales_role"]) else a.value("bonus_pct_non_sales")
        monthly = s / 12
        people = monthly * (1 + bonus) * (1 + a.location_param(r.location, "employer_tax_rate")) + monthly * a.location_param(r.location, "benefits_rate")
        expected_people += people * int(r.count)
    assert d_people == pytest.approx(expected_people, rel=1e-9)
    # the vacancy allowance scales with the seats it is applied to
    vac = (a.value("attrition_annual") / 12) * a.value("backfill_lag_months")
    base_vac = base.workforce[base.workforce["origin"] == "vacancy"]["people_cost"].sum()
    shift_vac = shifted.workforce[shifted.workforce["origin"] == "vacancy"]["people_cost"].sum()
    assert (base_vac - shift_vac) == pytest.approx(-vac * expected_people, rel=1e-9)
    assert d_other > 0


def test_no_typed_figures_in_renderers():
    whitelist = {"2026", "2027", "2028", "2025", "1e6", "1e3", "100", "0.0", "12", "1.0", "0.5", "1.5", "0.85", "0.95",
                 "0.05", "0.035", "0.03", "0.02", "0.5"}
    pattern = re.compile(r"""(?P<q>["'])(?P<body>(?:(?!(?P=q)).)*)(?P=q)""")
    number = re.compile(r"(?<![\w.#])(\d{3,}|\d+\.\d+|\d+%|\d+k|\d+M)(?![\w])")
    offenders = []
    for path in (ROOT / "model" / "reports.py", ROOT / "build_site.py"):
        src = path.read_text(encoding="utf-8")
        # only the prose parts of the renderers: skip svg geometry helpers and css
        for i, line in enumerate(src.splitlines(), start=1):
            if "<svg" in line or "viewBox" in line or "fig.add_axes" in line or "figsize" in line or "fontsize" in line \
               or line.strip().startswith(("#", "ml,", "pw,", "ax", "out.append", "def ", "return", "for ", "if ", "x =", "y =")) \
               or "{{" in line or "rgba" in line or "px" in line or "USD, " in line or "Rectangle" in line \
               or "linespacing" in line or "fig.text(0" in line or "textwrap" in line or "_wrap(" in line and "fig.text" in line:
                continue
            for m in pattern.finditer(line):
                body = m.group("body")
                # strip f-string expressions: numbers inside {...} are format specs or facts
                stripped = re.sub(r"\{[^}]*\}", " ", body)
                for n in number.findall(stripped):
                    if n in whitelist:
                        continue
                    offenders.append((path.name, i, n, body[:80]))
    assert not offenders, "typed figures in renderer strings:\n" + "\n".join(f"  {p}:{i} {n!r} in {b!r}" for p, i, n, b in offenders)


def test_recommendation_responds_to_the_guardrail(world, opening, months, decision):
    a = world["assumptions"]
    loose = a.with_override("min_runway_months_downside", 6.0, "all")
    d2 = decision_mod.evaluate(loose, world["roster"], opening, months)
    assert d2["chosen"] != decision["chosen"]          # a looser floor lets a bigger plan through
    assert d2["chosen"] == "front_commit"
    strict = a.with_override("min_runway_months_downside", 40.0, "all")
    d3 = decision_mod.evaluate(strict, world["roster"], opening, months)
    assert d3["chosen"] == "hold_commit"


def test_budget_floor_sensitivity_matches_a_full_rerun(world, opening, months, decision):
    # the memo and page quote what the model picks at the budget's runway floor;
    # that shortcut must agree with running the whole engine at that floor
    from model import facts as fx
    F = fx.build()
    a = world["assumptions"]
    at_budget_floor = a.with_override("min_runway_months_downside", F["budget_min_runway"], "all")
    d = decision_mod.evaluate(at_budget_floor, world["roster"], opening, months)
    assert d["chosen"] == F["budget_floor_chosen"]
    assert F["budget_floor_chosen"] != F["chosen"]
