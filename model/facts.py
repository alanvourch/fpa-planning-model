"""One flat dictionary of every number the memo, the board pack and the web
page are allowed to show. Each value is read from a model output; the
reports format them, never type them. tests/test_reports.py and
tests/test_site.py check the rendered documents against this dictionary.
"""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from . import assumptions as asm

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "output"
DATA = ROOT / "data"


def _pnl(name: str) -> pd.DataFrame:
    return pd.read_csv(OUT / "scenarios" / f"{name}_pnl.csv", index_col="month")


def _cash(name: str) -> pd.DataFrame:
    return pd.read_csv(OUT / "scenarios" / f"{name}_cash.csv", index_col="month")


def _cloud(name: str) -> pd.DataFrame:
    return pd.read_csv(OUT / "scenarios" / f"{name}_cloud.csv", index_col="month")


def _wf(name: str) -> pd.DataFrame:
    return pd.read_csv(OUT / "scenarios" / f"{name}_workforce.csv")


def build() -> dict:
    a = asm.load()
    d = json.loads((OUT / "decision.json").read_text())
    grid = pd.read_csv(OUT / "option_grid.csv").set_index(["option_id", "scenario"])
    verdict = pd.read_csv(OUT / "option_verdict.csv").set_index("option_id")
    ytd = pd.read_csv(OUT / "bridge_ytd.csv")
    actual = pd.read_csv(DATA / "actuals_pnl.csv", index_col="month")
    actual_cash = pd.read_csv(DATA / "actuals_cash.csv", index_col="month")
    budget = pd.read_csv(DATA / "budget_fy2026_pnl.csv", index_col="month")
    opening = d["opening"]
    chosen = d["chosen"]
    hiring = a.hiring_plans[a.hiring_plans["plan_id"] == a.options.at[chosen, "hiring_plan"]]
    F = {}
    F["version"] = a.version
    F["chosen"] = chosen
    F["chosen_label"] = a.options.at[chosen, "label"]
    F["basis"] = d["basis"]
    F["horizon_start"], F["horizon_end"] = d["horizon"]
    F["as_of"] = opening["as_of"]
    F["min_runway"] = d["min_runway"]
    F["gm_floor"] = d["gm_floor"]
    F["commit_units"] = d["commit_units"]
    F["commit_discount"] = a.value("cloud_commit_discount")
    F["n_assumptions"] = int(len(a.table))
    F["n_benchmark"] = int((a.table.source_type == "benchmark").sum())
    F["n_derived_locations"] = int(len(a.locations))
    F["n_judgment"] = int((a.table.source_type == "judgment").sum())
    F["n_changelog"] = int(len(asm.read_changelog()))
    F["n_options"] = int(len(verdict))
    F["n_runs"] = int(len(grid))

    # where the company stands (last actual month)
    last = actual.index[-1]
    F["arr_now"] = opening["arr_total"]
    F["arr_platform_now"] = opening["arr_platform"]
    F["customers_now"] = opening["customers"]
    F["attach_now"] = opening["attach_rate"]
    F["cash_now"] = opening["cash"]
    F["fte_now"] = opening["fte_total"]
    F["revenue_month_now"] = float(actual.at[last, "revenue"])
    F["gm_now"] = float(actual.at[last, "gross_margin"])
    F["ebitda_month_now"] = float(actual.at[last, "ebitda"])
    F["ebitda_margin_now"] = float(actual.at[last, "ebitda_margin"])
    F["burn_now"] = float(actual_cash.at[last, "net_burn_3m"])
    F["runway_now"] = float(actual_cash.at[last, "runway_months"])
    prior = actual.index[-13]
    F["arr_growth_yoy"] = float(actual.at[last, "arr_total"] / actual.at[prior, "arr_total"] - 1.0)
    F["rd_share_now"] = float(actual.at[last, "rd_total"] / actual.at[last, "revenue"])
    F["sm_share_now"] = float(actual.at[last, "sm_total"] / actual.at[last, "revenue"])
    F["ga_share_now"] = float(actual.at[last, "ga_total"] / actual.at[last, "revenue"])
    F["gm_budget_now"] = float(budget.at[last, "gross_margin"])
    F["gm_gap_vs_budget"] = F["gm_budget_now"] - F["gm_now"]
    F["cloud_share_feb26"] = float(actual.at["2026-02", "cogs_cloud"] / actual.at["2026-02", "revenue"])
    F["cloud_share_now"] = float(actual.at[last, "cogs_cloud"] / actual.at[last, "revenue"])
    F["commit_coverage"] = a.value("cloud_commit_coverage")
    F["actual_months"] = int(len(actual))
    F["actual_first"], F["actual_last"] = actual.index[0], last

    # YTD 2026 bridge
    bm = [m for m in budget.index if m <= last]
    F["ytd_budget_ebitda"] = float(budget.loc[bm, "ebitda"].sum())
    F["ytd_actual_ebitda"] = float(actual.loc[bm, "ebitda"].sum())
    F["ytd_ebitda_variance"] = F["ytd_actual_ebitda"] - F["ytd_budget_ebitda"]
    F["ytd_budget_revenue"] = float(budget.loc[bm, "revenue"].sum())
    F["ytd_actual_revenue"] = float(actual.loc[bm, "revenue"].sum())
    F["ytd_revenue_variance"] = F["ytd_actual_revenue"] - F["ytd_budget_revenue"]
    F["ytd_months"] = len(bm)
    F["ytd_first"], F["ytd_last"] = bm[0], bm[-1]
    F["n_bridge_components"] = int(len(ytd))
    F["n_material"] = int(ytd["material"].sum())
    key = ytd.set_index(["line", "component"])["impact"]
    F["bridge_platform_volume"] = float(key[("revenue_platform", "volume")])
    F["bridge_platform_price"] = float(key[("revenue_platform", "price")])
    F["bridge_insights_volume"] = float(key[("revenue_insights", "volume")])
    F["bridge_insights_price"] = float(key[("revenue_insights", "price")])
    F["bridge_cloud_usage"] = float(key[("cogs_cloud", "usage")])
    F["bridge_cloud_rate"] = float(key[("cogs_cloud", "rate")])
    F["bridge_rd_headcount"] = float(key[("rd_payroll", "headcount")])
    F["bridge_sm_headcount"] = float(key[("sm_payroll", "headcount")])
    F["bridge_programs_volume"] = float(key[("sm_programs", "volume")])
    F["bridge_programs_rate"] = float(key[("sm_programs", "rate")])
    F["bridge_commission"] = float(key[("sm_commission", "spend")])
    mat = ytd[ytd["material"]].sort_values("impact", key=abs, ascending=False)
    F["material_rows"] = mat[["line_label", "component", "impact"]].to_dict("records")
    F["bridge_other"] = F["ytd_ebitda_variance"] - float(mat["impact"].sum())
    # the planted price and usage stories, read from the data rather than typed
    drivers = pd.read_csv(DATA / "drivers_actuals.csv", index_col="month")
    F["price_step_actual_2026"] = float(drivers.at["2026-01", "price_step"])
    F["price_step_budget_2026"] = asm.load_snapshot("1.0").value("price_increase_pct_jan")
    upic = drivers["units_per_insights_customer"]
    F["insights_usage_step"] = float(upic.loc["2026-03":"2026-08"].mean() / upic.loc["2025-09":"2026-02"].mean() - 1.0)

    # option grid
    F["options"] = {}
    for opt in verdict.index:
        v = verdict.loc[opt]
        F["options"][opt] = {
            "label": a.options.at[opt, "label"], "feasible": bool(v["feasible"]),
            "runway_ok": bool(v["runway_ok"]), "gm_ok": bool(v["gm_ok"]),
            "downside_runway_min": float(v["downside_runway_min"]), "base_gm_min": float(v["base_gm_min"]),
            "base_arr_end": float(v["base_arr_end"]), "upside_arr_end": float(v["upside_arr_end"]),
            "downside_arr_end": float(v["downside_arr_end"]), "downside_cash_min": float(v["downside_cash_min"]),
            "base_cum_burn": float(v["base_cum_burn"]),
            "base_cash_end": float(grid.at[(opt, "base"), "cash_end"]),
            "base_ebitda_18m": float(grid.at[(opt, "base"), "ebitda_18m"]),
            "plan_hires": int(grid.at[(opt, "base"), "plan_hires"]),
            "fte_end_base": float(grid.at[(opt, "base"), "fte_end"]),
            "cloud_18m_base": float(grid.at[(opt, "base"), "cloud_18m"]),
            "stranded_downside": float(grid.at[(opt, "downside"), "stranded_cost_18m"]),
            "cash_min_downside": float(grid.at[(opt, "downside"), "cash_min"]),
        }
    F["feasible_options"] = [o for o, v in F["options"].items() if v["feasible"]]
    F["rejected_runway"] = [o for o, v in F["options"].items() if not v["runway_ok"]]
    F["rejected_gm"] = [o for o, v in F["options"].items() if not v["gm_ok"]]

    # the chosen option in detail
    c = F["options"][chosen]
    for k, v in c.items():
        F[f"chosen_{k}"] = v
    F["chosen_base_arr_growth"] = c["base_arr_end"] / F["arr_now"] - 1.0
    F["chosen_downside_arr_growth"] = c["downside_arr_end"] / F["arr_now"] - 1.0
    F["chosen_upside_arr_growth"] = c["upside_arr_end"] / F["arr_now"] - 1.0
    for sc in asm.SCENARIOS:
        p, cs, cl = _pnl(f"{chosen}__{sc}"), _cash(f"{chosen}__{sc}"), _cloud(f"{chosen}__{sc}")
        F[f"chosen_{sc}_arr_end"] = float(p["arr_total"].iloc[-1])
        F[f"chosen_{sc}_cash_end"] = float(cs["closing_cash"].iloc[-1])
        F[f"chosen_{sc}_cash_min"] = float(cs["closing_cash"].min())
        F[f"chosen_{sc}_runway_min"] = float(cs["runway_months"][cs["net_burn_3m"] > 0].min()) if (cs["net_burn_3m"] > 0).any() else float("inf")
        F[f"chosen_{sc}_gm_min"] = float(p["gross_margin"].min())
        F[f"chosen_{sc}_gm_avg"] = float(p["gross_profit"].sum() / p["revenue"].sum())
        F[f"chosen_{sc}_ebitda_end_month"] = float(p["ebitda"].iloc[-1])
        F[f"chosen_{sc}_revenue_18m"] = float(p["revenue"].sum())
        F[f"chosen_{sc}_cloud_18m"] = float(p["cogs_cloud"].sum())
        F[f"chosen_{sc}_fte_end"] = float(p["fte_total"].iloc[-1])
        F[f"chosen_{sc}_stranded"] = float((cl["stranded_units"] * cl["unit_price"] * (1 - cl["commit_discount"])).sum())
        F[f"chosen_{sc}_breakeven_month"] = next((m for m, v in p["ebitda"].items() if v >= 0), None)
        F[f"chosen_{sc}_series"] = {
            "months": list(p.index), "arr": [float(x) for x in p["arr_total"]],
            "cash": [float(x) for x in cs["closing_cash"]], "gm": [float(x) for x in p["gross_margin"]],
            "ebitda": [float(x) for x in p["ebitda"]], "revenue": [float(x) for x in p["revenue"]],
            "fte": [float(x) for x in p["fte_total"]],
        }
    # the same hiring plan on demand, for the cloud-commit comparison
    ondemand = chosen.replace("_commit", "_ondemand")
    F["ondemand_twin"] = ondemand
    if ondemand in F["options"]:
        F["commit_saving_base_18m"] = F["options"][ondemand]["cloud_18m_base"] - c["cloud_18m_base"]
        F["commit_gm_gain_base"] = c["base_gm_min"] - F["options"][ondemand]["base_gm_min"]
        p_od = _pnl(f"{ondemand}__base")
        F["ondemand_base_gm_avg"] = float(p_od["gross_profit"].sum() / p_od["revenue"].sum())
    # the next-larger plan, for the "why not more" argument
    F["front_option"] = "front_commit"
    fo = F["options"].get("front_commit")
    if fo:
        F["front_extra_arr_base"] = fo["base_arr_end"] - c["base_arr_end"]
        F["front_runway_shortfall"] = F["min_runway"] - fo["downside_runway_min"]
        F["front_extra_hires"] = fo["plan_hires"] - c["plan_hires"]
        F["front_cash_min_downside"] = fo["cash_min_downside"]
    ho = F["options"].get("hold_commit")
    if ho:
        F["hold_arr_gap_base"] = c["base_arr_end"] - ho["base_arr_end"]
        F["hold_cash_end_gap"] = ho["base_cash_end"] - c["base_cash_end"]

    # hiring plan composition (chosen)
    F["hiring_rows"] = hiring[["role", "location", "start_month", "count", "rationale"]].to_dict("records")
    F["hires_total"] = int(hiring["count"].sum())
    by_func = hiring.merge(a.salaries[["function"]], left_on="role", right_index=True).groupby("function")["count"].sum()
    F["hires_by_function"] = {k: int(v) for k, v in by_func.items()}
    F["hires_by_location"] = {k: int(v) for k, v in hiring.groupby("location")["count"].sum().items()}
    F["hires_rd"] = int(by_func.get("R&D", 0))
    F["hires_sm"] = int(by_func.get("S&M", 0))
    F["hires_ga"] = int(by_func.get("G&A", 0))
    front_plan = a.hiring_plans[a.hiring_plans["plan_id"] == "front_loaded"].merge(a.salaries[["function"]], left_on="role", right_index=True)
    F["front_hires_rd"] = int(front_plan.loc[front_plan["function"] == "R&D", "count"].sum())
    F["front_hires_total"] = int(front_plan["count"].sum())
    F["hires_ga"] = int(by_func.get("G&A", 0))
    front_plan = a.hiring_plans[a.hiring_plans["plan_id"] == "front_loaded"].merge(a.salaries[["function"]], left_on="role", right_index=True)
    F["front_hires_rd"] = int(front_plan.loc[front_plan["function"] == "R&D", "count"].sum())
    F["front_hires_total"] = int(front_plan["count"].sum())
    F["hires_ga"] = int(by_func.get("G&A", 0))
    front_plan = a.hiring_plans[a.hiring_plans["plan_id"] == "front_loaded"].merge(a.salaries[["function"]], left_on="role", right_index=True)
    F["front_hires_rd"] = int(front_plan.loc[front_plan["function"] == "R&D", "count"].sum())
    F["front_hires_total"] = int(front_plan["count"].sum())
    F["hires_ga"] = int(by_func.get("G&A", 0))
    front_plan = a.hiring_plans[a.hiring_plans["plan_id"] == "front_loaded"].merge(a.salaries[["function"]], left_on="role", right_index=True)
    F["front_hires_rd"] = int(front_plan.loc[front_plan["function"] == "R&D", "count"].sum())
    F["front_hires_total"] = int(front_plan["count"].sum())
    wfb = _wf(f"{chosen}__base")
    plan_rows = wfb[wfb["origin"].str.startswith("plan:")]
    F["plan_hire_cost_18m"] = float(plan_rows["people_cost"].sum() + plan_rows["recruiting"].sum())
    auto = wfb[wfb["origin"].str.startswith("auto:")].drop_duplicates("position_id")
    F["auto_csm_hires_base"] = int(len(auto))
    F["first_hire_month"] = str(hiring["start_month"].min())
    F["last_hire_month"] = str(hiring["start_month"].max())
    # fully loaded cost comparison for one senior engineer by location (annual, year one, no merit)
    def loaded(role, loc):
        s = a.salary(role, loc)
        return s * (1 + a.value("bonus_pct_non_sales")) * (1 + a.location_param(loc, "employer_tax_rate")) + s * a.location_param(loc, "benefits_rate")
    F["loaded_senior_eng"] = {loc: loaded("Senior Software Engineer", loc) for loc in a.locations.index}
    F["salary_senior_eng"] = {loc: a.salary("Senior Software Engineer", loc) for loc in a.locations.index}
    F["employer_tax"] = {loc: a.location_param(loc, "employer_tax_rate") for loc in a.locations.index}

    # benchmarks quoted (from the assumption sources, for the page)
    F["nrr_base"] = a.value("nrr_annual")
    F["nrr_downside"] = a.value("nrr_annual", "downside")
    F["nrr_upside"] = a.value("nrr_annual", "upside")
    F["grr_base"] = a.value("grr_annual")
    F["lpa_base"] = a.value("logos_per_ramped_ae_month")
    F["lpa_downside"] = a.value("logos_per_ramped_ae_month", "downside")
    F["lpa_upside"] = a.value("logos_per_ramped_ae_month", "upside")
    F["price_step"] = a.value("price_increase_pct_jan")
    F["attrition"] = a.value("attrition_annual")
    F["customers_per_csm"] = a.value("customers_per_csm")
    F["materiality_abs"] = a.value("materiality_abs_usd")
    F["materiality_pct"] = a.value("materiality_pct")
    F["materiality_override"] = a.value("materiality_abs_override_usd")
    return F


# ---- formatting helpers shared by every renderer ----

def musd(x: float, digits: int = 1) -> str:
    return f"USD {x / 1e6:,.{digits}f}M"


def kusd(x: float) -> str:
    return f"USD {x / 1e3:,.0f}k"


def pct(x: float, digits: int = 0) -> str:
    return f"{x * 100:.{digits}f}%"


def pts(x: float, digits: int = 1) -> str:
    return f"{x * 100:.{digits}f} points"


def months_str(x: float) -> str:
    return "not applicable (cash positive)" if x == float("inf") else f"{x:.0f} months"


def signed_kusd(x: float) -> str:
    return f"{'+' if x >= 0 else '-'}USD {abs(x) / 1e3:,.0f}k"


def month_name(m: str) -> str:
    return pd.Period(m, freq="M").strftime("%B %Y")
