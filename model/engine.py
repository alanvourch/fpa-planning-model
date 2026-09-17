"""The finance engine: drivers and workforce in, P&L, product P&L and cash out.

The same function computes the actuals (from realized drivers) and every
plan scenario (from assumed drivers), so the bridge between the two compares
like with like. Nothing here reads assumptions directly: every input arrives
through the `drivers` table (one row per month) or the workforce table.

Drivers columns (per month):
  new_logos, churn_rate_m, expansion_rate_m, price_step, attach_rate,
  arpa_insights, acv_new, units_per_platform_customer,
  units_per_insights_customer, cloud_unit_price, cloud_fixed, commit_units,
  commit_discount, third_party_pct, payment_pct, annual_share, dso_days,
  commission_pct, marketing_programs, rd_contractors, rd_tooling_per_head,
  ga_software_per_head, ga_fixed

Opening state: customers, arr_platform, cash, ar, deferred.

Conventions (stated once, applied everywhere):
  revenue          = closing ARR / 12 (subscription, recognized monthly)
  churned ARR      = opening ARR x churn_rate_m
  expansion ARR    = opening ARR x expansion_rate_m (net retention excluding price)
  price ARR        = opening ARR x price_step (January only)
  new ARR          = new_logos x acv_new
  customers        = opening x (1 - churn_rate_m) + new_logos
  Insights ARR     = customers x attach_rate x arpa_insights (add-on)
  cloud cost       = min(units, commit) x price x (1 - discount)
                     + max(units - commit, 0) x price + fixed
  deferred revenue = annual_share x ARR x 5.5 / 12 (uniform renewal dates)
  receivables      = revenue x dso_days / 30
  cash movement    = EBITDA - capex - change in AR + change in deferred
  runway           = closing cash / average net burn of the trailing 3 months
No interest, income tax, depreciation or capitalized development: EBITDA is
the operating line and cash follows it directly.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from . import workforce as wf_mod

DRIVER_COLUMNS = [
    "new_logos", "churn_rate_m", "expansion_rate_m", "price_step", "attach_rate",
    "arpa_insights", "acv_new", "units_per_platform_customer",
    "units_per_insights_customer", "cloud_unit_price", "cloud_fixed", "commit_units",
    "commit_discount", "third_party_pct", "payment_pct", "annual_share", "dso_days",
    "commission_pct", "marketing_programs", "rd_contractors", "rd_tooling_per_head",
    "ga_software_per_head", "ga_fixed",
]


@dataclass
class Opening:
    customers: float
    arr_platform: float
    cash: float
    ar: float
    deferred: float


@dataclass
class Result:
    months: list
    pnl: pd.DataFrame
    arr: pd.DataFrame
    cloud: pd.DataFrame
    cash: pd.DataFrame
    product: pd.DataFrame
    workforce: pd.DataFrame
    workforce_summary: pd.DataFrame
    drivers: pd.DataFrame


def run(months: list, drivers: pd.DataFrame, workforce: pd.DataFrame, opening: Opening,
        assumptions) -> Result:
    missing = [c for c in DRIVER_COLUMNS if c not in drivers.columns]
    if missing:
        raise KeyError(f"drivers missing columns: {missing}")
    d = drivers.set_index("month").loc[months]
    wfs = wf_mod.summarize(workforce, months)
    rent_by_loc = {loc: assumptions.location_param(loc, "rent_per_head_month_usd")
                   for loc in assumptions.locations.index}
    fte_loc = workforce.groupby(["month", "location"])["fte"].sum().unstack("location").reindex(months).fillna(0.0)
    rent = sum(fte_loc[loc] * r for loc, r in rent_by_loc.items() if loc in fte_loc.columns)

    # --- ARR roll-forward (sequential) ---
    arr_rows = []
    cust, arr = opening.customers, opening.arr_platform
    for m in months:
        r = d.loc[m]
        churn = arr * r["churn_rate_m"]
        expansion = arr * r["expansion_rate_m"]
        price = arr * r["price_step"]
        new_arr = r["new_logos"] * r["acv_new"]
        churned_cust = cust * r["churn_rate_m"]
        closing = arr - churn + expansion + price + new_arr
        cust_close = cust - churned_cust + r["new_logos"]
        ins_cust = cust_close * r["attach_rate"]
        arr_ins = ins_cust * r["arpa_insights"]
        arr_rows.append({
            "month": m, "opening_arr": arr, "new_arr": new_arr, "expansion_arr": expansion,
            "price_arr": price, "churn_arr": -churn, "closing_arr": closing,
            "opening_customers": cust, "new_logos": r["new_logos"],
            "churned_customers": -churned_cust, "customers": cust_close,
            "attach_rate": r["attach_rate"], "insights_customers": ins_cust,
            "arpa_insights": r["arpa_insights"], "arr_insights": arr_ins,
            "arr_total": closing + arr_ins,
        })
        cust, arr = cust_close, closing
    arr_df = pd.DataFrame(arr_rows).set_index("month")

    # --- revenue and cloud ---
    rev_p = arr_df["closing_arr"] / 12.0
    rev_i = arr_df["arr_insights"] / 12.0
    revenue = rev_p + rev_i
    units_p = arr_df["customers"] * d["units_per_platform_customer"]
    units_i = arr_df["insights_customers"] * d["units_per_insights_customer"]
    units = units_p + units_i
    committed = np.minimum(units, d["commit_units"])
    ondemand = np.maximum(units - d["commit_units"], 0.0)
    cost_committed = committed * d["cloud_unit_price"] * (1.0 - d["commit_discount"])
    cost_ondemand = ondemand * d["cloud_unit_price"]
    cloud_total = cost_committed + cost_ondemand + d["cloud_fixed"]
    cloud_df = pd.DataFrame({
        "units_platform": units_p, "units_insights": units_i, "units": units,
        "commit_units": d["commit_units"], "committed_units_used": committed,
        "ondemand_units": ondemand, "unit_price": d["cloud_unit_price"],
        "commit_discount": d["commit_discount"], "cost_committed": cost_committed,
        "cost_ondemand": cost_ondemand, "cost_fixed": d["cloud_fixed"], "cloud_total": cloud_total,
        "stranded_units": np.maximum(d["commit_units"] - units, 0.0),
    })

    # --- P&L ---
    pnl = pd.DataFrame(index=pd.Index(months, name="month"))
    pnl["revenue_platform"] = rev_p
    pnl["revenue_insights"] = rev_i
    pnl["revenue"] = revenue
    pnl["cogs_cloud"] = cloud_total
    pnl["cogs_third_party"] = revenue * d["third_party_pct"]
    pnl["cogs_payment"] = revenue * (1.0 - d["annual_share"]) * d["payment_pct"]
    pnl["cogs_payroll"] = wfs["people_cost_COGS"]
    pnl["cogs_recruiting"] = wfs["recruiting_COGS"]
    pnl["cogs"] = pnl[["cogs_cloud", "cogs_third_party", "cogs_payment", "cogs_payroll", "cogs_recruiting"]].sum(axis=1)
    pnl["gross_profit"] = pnl["revenue"] - pnl["cogs"]
    pnl["gross_margin"] = pnl["gross_profit"] / pnl["revenue"]
    pnl["rd_payroll"] = wfs["people_cost_R&D"]
    pnl["rd_recruiting"] = wfs["recruiting_R&D"]
    pnl["rd_tooling"] = wfs["fte_R&D"] * d["rd_tooling_per_head"]
    pnl["rd_contractors"] = d["rd_contractors"]
    pnl["rd_total"] = pnl[["rd_payroll", "rd_recruiting", "rd_tooling", "rd_contractors"]].sum(axis=1)
    new_and_expansion = arr_df["new_arr"] + arr_df["expansion_arr"]
    pnl["sm_payroll"] = wfs["people_cost_S&M"]
    pnl["sm_recruiting"] = wfs["recruiting_S&M"]
    pnl["sm_commission"] = new_and_expansion * d["commission_pct"]
    pnl["sm_programs"] = d["marketing_programs"]
    pnl["sm_total"] = pnl[["sm_payroll", "sm_recruiting", "sm_commission", "sm_programs"]].sum(axis=1)
    pnl["ga_payroll"] = wfs["people_cost_G&A"]
    pnl["ga_recruiting"] = wfs["recruiting_G&A"]
    pnl["ga_rent"] = rent
    pnl["ga_software"] = wfs["fte_total"] * d["ga_software_per_head"]
    pnl["ga_fixed"] = d["ga_fixed"]
    pnl["ga_total"] = pnl[["ga_payroll", "ga_recruiting", "ga_rent", "ga_software", "ga_fixed"]].sum(axis=1)
    pnl["opex"] = pnl["rd_total"] + pnl["sm_total"] + pnl["ga_total"]
    pnl["ebitda"] = pnl["gross_profit"] - pnl["opex"]
    pnl["ebitda_margin"] = pnl["ebitda"] / pnl["revenue"]
    pnl["fte_total"] = wfs["fte_total"]
    for b in ["COGS", "R&D", "S&M", "G&A"]:
        pnl[f"fte_{b}"] = wfs[f"fte_{b}"]
    pnl["arr_total"] = arr_df["arr_total"]

    # --- cash ---
    capex = wfs["capex_COGS"] + wfs["capex_R&D"] + wfs["capex_S&M"] + wfs["capex_G&A"]
    deferred = d["annual_share"] * arr_df["arr_total"] * 5.5 / 12.0
    ar = revenue * d["dso_days"] / 30.0
    cash = pd.DataFrame(index=pnl.index)
    cash["ebitda"] = pnl["ebitda"]
    cash["capex"] = -capex
    prev_ar = pd.Series([opening.ar] + list(ar.iloc[:-1]), index=ar.index)
    prev_def = pd.Series([opening.deferred] + list(deferred.iloc[:-1]), index=deferred.index)
    cash["delta_ar"] = -(ar - prev_ar)
    cash["delta_deferred"] = deferred - prev_def
    cash["financing"] = d["financing"] if "financing" in d.columns else 0.0
    cash["net_cash_flow"] = cash[["ebitda", "capex", "delta_ar", "delta_deferred", "financing"]].sum(axis=1)
    cash["opening_cash"] = opening.cash + cash["net_cash_flow"].cumsum().shift(1, fill_value=0.0)
    cash["closing_cash"] = opening.cash + cash["net_cash_flow"].cumsum()
    cash["ar"] = ar
    cash["deferred_revenue"] = deferred
    operating_flow = cash["net_cash_flow"] - cash["financing"]
    burn = (-operating_flow).rolling(3, min_periods=1).mean()
    cash["net_burn_3m"] = burn
    cash["runway_months"] = np.where(burn > 0, cash["closing_cash"] / burn.replace(0, np.nan), np.inf)

    # --- product P&L (down to gross profit) ---
    prod_rows = []
    for m in months:
        share_units = {"Platform": units_p[m] / units[m] if units[m] else 0.0,
                       "Insights": units_i[m] / units[m] if units[m] else 0.0}
        share_rev = {"Platform": rev_p[m] / revenue[m] if revenue[m] else 0.0,
                     "Insights": rev_i[m] / revenue[m] if revenue[m] else 0.0}
        for prod, rv in (("Platform", rev_p[m]), ("Insights", rev_i[m])):
            cloud_c = (cost_committed[m] + cost_ondemand[m]) * share_units[prod] + d.at[m, "cloud_fixed"] * share_rev[prod]
            tp = pnl.at[m, "cogs_third_party"] * share_rev[prod]
            pay = pnl.at[m, "cogs_payment"] * share_rev[prod]
            ppl = (pnl.at[m, "cogs_payroll"] + pnl.at[m, "cogs_recruiting"]) * share_rev[prod]
            cogs = cloud_c + tp + pay + ppl
            prod_rows.append({"month": m, "product": prod, "revenue": rv, "cogs_cloud": cloud_c,
                              "cogs_third_party": tp, "cogs_payment": pay, "cogs_payroll": ppl,
                              "cogs": cogs, "gross_profit": rv - cogs,
                              "gross_margin": (rv - cogs) / rv if rv else 0.0})
    product = pd.DataFrame(prod_rows)

    return Result(months=months, pnl=pnl, arr=arr_df, cloud=cloud_df, cash=cash, product=product,
                  workforce=workforce, workforce_summary=wfs, drivers=d)
