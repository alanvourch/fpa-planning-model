"""Decision engine: evaluate every allocation option under every scenario,
apply the guardrails, and pick.

Options (assumptions/options.csv): a hiring plan (hold, phased, front-loaded)
crossed with the cloud commitment (on demand, or a one-year commitment).
Scenarios: base, upside, downside, all built from the same drivers.

Guardrails (assumptions, category 'guardrail'):
  downside cash runway never below min_runway_months_downside, in any month
  base blended gross margin never below gross_margin_floor, in any month
Objective among the feasible options: highest total ARR at the end of the
horizon in the base scenario; ties go to the lower cumulative burn.

The cloud commitment is sized once, from the base scenario of the phased plan
run without commitment: commit_units = coverage x average monthly units. The
same commitment then applies to every option and scenario, so the downside
shows what a commitment strands.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from . import assumptions as asm, plan

METRIC_COLUMNS = [
    "option_id", "scenario", "arr_end", "arr_growth", "revenue_18m", "gross_profit_18m", "ebitda_18m",
    "cum_burn", "cash_end", "cash_min", "runway_min", "gm_min", "gm_avg", "fte_end", "rd_fte_end",
    "cloud_18m", "stranded_cost_18m", "plan_hires", "plan_hire_cost_18m",
]


def size_commitment(assumptions, roster, opening_state, months) -> float:
    ref = plan.build_plan(assumptions, "base", "phased_ondemand", roster, opening_state, months)
    return float(assumptions.value("cloud_commit_coverage") * ref.cloud["units"].mean())


def metrics(res, opening_state, assumptions) -> dict:
    pnl, cash, cloud, wf = res.pnl, res.cash, res.cloud, res.workforce
    op_flow = cash["net_cash_flow"] - cash["financing"]
    burn_months = cash["runway_months"][cash["net_burn_3m"] > 0]
    plan_rows = wf[wf["origin"].str.startswith("plan:") | wf["origin"].str.startswith("auto:")]
    plan_seats = plan_rows.drop_duplicates("position_id")
    disc = cloud["commit_discount"]
    return {
        "option_id": res.option_id, "scenario": res.scenario,
        "arr_end": float(pnl["arr_total"].iloc[-1]),
        "arr_growth": float(pnl["arr_total"].iloc[-1] / opening_state["arr_total"] - 1.0),
        "revenue_18m": float(pnl["revenue"].sum()),
        "gross_profit_18m": float(pnl["gross_profit"].sum()),
        "ebitda_18m": float(pnl["ebitda"].sum()),
        "cum_burn": float(-op_flow.sum()),
        "cash_end": float(cash["closing_cash"].iloc[-1]),
        "cash_min": float(cash["closing_cash"].min()),
        "runway_min": float(burn_months.min()) if len(burn_months) else float("inf"),
        "gm_min": float(pnl["gross_margin"].min()),
        "gm_avg": float(pnl["gross_profit"].sum() / pnl["revenue"].sum()),
        "fte_end": float(pnl["fte_total"].iloc[-1]),
        "rd_fte_end": float(pnl["fte_R&D"].iloc[-1]),
        "cloud_18m": float(pnl["cogs_cloud"].sum()),
        "stranded_cost_18m": float((cloud["stranded_units"] * cloud["unit_price"] * (1.0 - disc)).sum()),
        "plan_hires": int(len(plan_seats)),
        "plan_hire_cost_18m": float(plan_rows["people_cost"].sum() + plan_rows["recruiting"].sum()),
    }


def evaluate(assumptions, roster, opening_state, months) -> dict:
    commit_units = size_commitment(assumptions, roster, opening_state, months)
    runs, rows = {}, []
    for option_id in assumptions.options.index:
        if option_id == "fy2026_budget":
            continue
        for scenario in asm.SCENARIOS:
            res = plan.build_plan(assumptions, scenario, option_id, roster, opening_state, months, commit_units)
            runs[(option_id, scenario)] = res
            rows.append(metrics(res, opening_state, assumptions))
    grid = pd.DataFrame(rows, columns=METRIC_COLUMNS)

    min_runway = assumptions.value("min_runway_months_downside")
    gm_floor = assumptions.value("gross_margin_floor")
    verdict = []
    for option_id in grid["option_id"].unique():
        g = grid[grid["option_id"] == option_id].set_index("scenario")
        runway_ok = g.at["downside", "runway_min"] >= min_runway
        gm_ok = g.at["base", "gm_min"] >= gm_floor
        verdict.append({"option_id": option_id, "label": assumptions.options.at[option_id, "label"],
                        "downside_runway_min": g.at["downside", "runway_min"], "runway_ok": bool(runway_ok),
                        "base_gm_min": g.at["base", "gm_min"], "gm_ok": bool(gm_ok),
                        "feasible": bool(runway_ok and gm_ok),
                        "base_arr_end": g.at["base", "arr_end"], "base_cum_burn": g.at["base", "cum_burn"],
                        "upside_arr_end": g.at["upside", "arr_end"], "downside_arr_end": g.at["downside", "arr_end"],
                        "downside_cash_min": g.at["downside", "cash_min"]})
    verdict = pd.DataFrame(verdict)
    chosen, basis = choose(verdict, min_runway, gm_floor)
    return {"commit_units": commit_units, "grid": grid, "verdict": verdict, "chosen": chosen,
            "basis": basis, "runs": runs, "min_runway": min_runway, "gm_floor": gm_floor}


def choose(verdict: pd.DataFrame, min_runway: float, gm_floor: float) -> tuple[str, str]:
    """Apply the guardrails and the objective to a verdict table (one row per
    option, with option_id, downside_runway_min, base_gm_min, base_arr_end and
    base_cum_burn). Also used to show how the answer moves with the runway floor."""
    feasible = verdict[(verdict["downside_runway_min"] >= min_runway) & (verdict["base_gm_min"] >= gm_floor)]
    if feasible.empty:
        chosen = verdict.sort_values("downside_runway_min", ascending=False).iloc[0]["option_id"]
        basis = "no option satisfied both guardrails; the option with the longest downside runway is recommended"
    else:
        chosen = feasible.sort_values(["base_arr_end", "base_cum_burn"], ascending=[False, True]).iloc[0]["option_id"]
        basis = "highest base-scenario ARR at the end of the horizon among options that satisfy both guardrails"
    return str(chosen), basis
