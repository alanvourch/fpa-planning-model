"""Plan builder: assumptions + option + opening state -> drivers and workforce
for the planning horizon, then the engine.

Order of operations (each step feeds the next):
  1. positions   = roster active at plan start (no end dates)
                 + the option's hiring plan lines
  2. workforce   = monthly cost of those positions, with the vacancy allowance
  3. new_logos   = ramped AE capacity x logos per ramped AE x seasonality
  4. drivers     = every other driver from the assumption table
  5. customers   = engine ARR roll-forward, from which
  6. CSM hires   = added when ramped CSM capacity falls below customers /
                   customers_per_csm (driver-based hiring), then steps 2 to 5
                   run once more with the extra seats (CSMs do not change
                   revenue, so one extra pass converges)
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from . import engine, workforce as wf_mod


def horizon(start: str = "2026-09", n: int = 18) -> list:
    return wf_mod.month_range(start, n)


def plan_positions(assumptions, roster: pd.DataFrame, plan_id: str, plan_start) -> pd.DataFrame:
    """Roster seats filled at plan start, plus the named hiring plan."""
    # seats filled in the month before the plan starts; future leavers are unknown
    # at planning time, so end dates are dropped and the vacancy allowance applies
    active = roster[(roster["start"] <= plan_start - 1) &
                    (roster["end"].isna() | (roster["end"] > plan_start - 1))].copy()
    active["end"] = pd.NaT
    active["origin"] = "roster"
    rows = []
    if plan_id != "hold":
        plan = assumptions.hiring_plans[assumptions.hiring_plans["plan_id"] == plan_id]
        if plan.empty:
            raise KeyError(f"hiring plan {plan_id!r} has no rows")
        for r in plan.itertuples(index=False):
            if pd.Period(r.start_month, freq="M") < plan_start:
                raise ValueError(f"hiring plan {plan_id}: start {r.start_month} is before the plan window")
            rows.append({"role": r.role, "location": r.location, "start": r.start_month,
                         "count": int(r.count), "origin": f"plan:{plan_id}"})
    hires = wf_mod.make_positions(rows, assumptions) if rows else pd.DataFrame(columns=wf_mod.POSITION_COLUMNS)
    return pd.concat([active[wf_mod.POSITION_COLUMNS], hires], ignore_index=True)


def build_drivers(assumptions, scenario: str, months: list, new_logos: pd.Series,
                  opening_attach: float, opening_arpa_insights: float, opening_acv: float,
                  opening_unit_price: float, commit_units: float, option) -> pd.DataFrame:
    v = lambda k: assumptions.value(k, scenario)  # noqa: E731
    n = len(months)
    # NRR is all-in (it includes the January list-price increase), so the
    # month-to-month expansion rate excludes the price step carried separately
    churn_m = 1.0 - v("grr_annual") ** (1.0 / 12.0)
    exp_m = (v("nrr_annual") - v("price_increase_pct_jan")) ** (1.0 / 12.0) - v("grr_annual") ** (1.0 / 12.0)
    attach = []
    a = opening_attach
    uplift = float(option.get("attach_gain_uplift_pts", 0.0))
    uplift_lag = int(option.get("attach_gain_uplift_lag_months", 0))
    for i, m in enumerate(months):
        gain = v("attach_gain_pts_month") / 100.0
        if uplift and i >= uplift_lag:
            gain += uplift / 100.0
        a = min(v("attach_rate_cap"), a + gain)
        attach.append(a)
    arpa_ins = [opening_arpa_insights * (1.0 + v("insights_usage_growth_month")) ** (i + 1) for i in range(n)]
    price_step = [v("price_increase_pct_jan") if m.month == 1 else 0.0 for m in months]
    # new-customer ACV follows the list price: it steps with each January increase
    acv, acv_path = opening_acv, []
    for m in months:
        if m.month == 1:
            acv *= 1.0 + v("price_increase_pct_jan")
        acv_path.append(acv)
    unit_price = [opening_unit_price * (1.0 + v("cloud_unit_price_drift_month")) ** (i + 1) for i in range(n)]
    extra = float(option.get("rd_contractors_extra_month", 0.0))
    extra_n = int(option.get("rd_contractors_extra_months", 0))
    contractors = [v("rd_contractors_month") + (extra if i < extra_n else 0.0) for i in range(n)]
    programs = new_logos.reindex(months).fillna(0.0).values * v("marketing_program_cost_per_new_logo")
    return pd.DataFrame({
        "month": months,
        "new_logos": new_logos.reindex(months).fillna(0.0).values,
        "churn_rate_m": churn_m,
        "expansion_rate_m": exp_m,
        "price_step": price_step,
        "attach_rate": attach,
        "arpa_insights": arpa_ins,
        "acv_new": acv_path,
        "units_per_platform_customer": v("cloud_units_per_platform_customer"),
        "units_per_insights_customer": v("cloud_units_per_insights_customer"),
        "cloud_unit_price": unit_price,
        "cloud_fixed": v("cloud_fixed_month_usd"),
        "commit_units": commit_units,
        "commit_discount": v("cloud_commit_discount") if commit_units > 0 else 0.0,
        "third_party_pct": v("third_party_cogs_pct_rev"),
        "payment_pct": v("payment_processing_pct_monthly_billed"),
        "annual_share": v("annual_upfront_billing_share"),
        "dso_days": v("dso_days"),
        "commission_pct": v("sales_commission_pct_new_arr"),
        "marketing_programs": programs,
        "rd_contractors": contractors,
        "rd_tooling_per_head": v("rd_tooling_per_head_month"),
        "ga_software_per_head": v("ga_software_per_employee_month"),
        "ga_fixed": v("ga_fixed_month_usd"),
    })


def new_logos_from_capacity(wf: pd.DataFrame, assumptions, scenario: str, months: list) -> pd.Series:
    cap = wf_mod.ramped_capacity(wf, "Account Executive", assumptions.value("ae_ramp_months", scenario))
    cap = cap.reindex(months).fillna(0.0)
    seas = pd.Series([assumptions.seasonality[m.month] for m in months], index=months)
    return cap * assumptions.value("logos_per_ramped_ae_month", scenario) * seas


def build_plan(assumptions, scenario: str, option_id: str, roster: pd.DataFrame, opening_state: dict,
               months: list, commit_units: float = 0.0, csm_location: str = "Austin") -> engine.Result:
    option = assumptions.options.loc[option_id].to_dict()
    if not bool(int(option["cloud_commit"])):
        commit_units = 0.0
    plan_start = months[0]
    positions = plan_positions(assumptions, roster, option["hiring_plan"], plan_start)
    opening = engine.Opening(
        customers=opening_state["customers"], arr_platform=opening_state["arr_platform"],
        cash=opening_state["cash"], ar=opening_state["ar"], deferred=opening_state["deferred"])

    def _run(pos):
        wf = wf_mod.monthly_workforce(pos, months, assumptions, scenario, vacancy_allowance=True)
        logos = new_logos_from_capacity(wf, assumptions, scenario, months)
        drivers = build_drivers(assumptions, scenario, months, logos, opening_state["attach_rate"],
                                opening_state["arpa_insights"], opening_state["acv_new"],
                                opening_state["cloud_unit_price"], commit_units, option)
        return engine.run(months, drivers, wf, opening, assumptions), wf

    result, wf = _run(positions)
    # driver-based CSM hiring: keep coverage at customers_per_csm
    per_csm = assumptions.value("customers_per_csm", scenario)
    ramp = assumptions.value("csm_ramp_months", scenario)
    extra_rows = []
    cap = wf_mod.ramped_capacity(wf, "Customer Success Manager", ramp).reindex(months).fillna(0.0)
    pending = []  # (start_month) of auto hires already decided
    for m in months:
        need = result.arr.at[m, "customers"] / per_csm
        have = cap[m] + sum(min(1.0, max(0, (m - s).n) / ramp) for s in pending if s <= m)
        short = need - have
        while short > 1.0:
            pending.append(m)
            extra_rows.append({"role": "Customer Success Manager", "location": csm_location,
                               "start": str(m), "count": 1, "origin": "auto:coverage"})
            short -= 1.0
    if extra_rows:
        extra = wf_mod.make_positions(extra_rows, assumptions)
        extra["position_id"] = [f"auto-csm-{i:03d}" for i in range(len(extra))]
        positions = pd.concat([positions, extra], ignore_index=True)
        result, wf = _run(positions)
    result.positions = positions
    result.option_id = option_id
    result.scenario = scenario
    return result
