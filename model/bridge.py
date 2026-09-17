"""Actual-versus-plan bridge: every P&L line split into driver components
whose sum is exactly the reported EBITDA variance.

Sign convention: impact is the effect on EBITDA, positive when favorable.
  revenue lines   impact = actual - budget
  cost lines      impact = budget - actual

Decompositions (b = budget, a = actual):
  revenue_platform, revenue_insights
      volume = (customers_a - customers_b) x ARPA_b
      price  = (ARPA_a - ARPA_b) x customers_a
  cogs_cloud
      usage  = (units_a - units_b) x unit_cost_b        (variable cost only)
      rate   = (unit_cost_a - unit_cost_b) x units_a
      fixed  = fixed_a - fixed_b
  payroll lines (cogs, rd, sm, ga)
      headcount = (fte_a - fte_b) x cost_per_fte_b
      rate      = (cost_per_fte_a - cost_per_fte_b) x fte_a
  sm_programs
      volume = (new_logos_a - new_logos_b) x cost_per_logo_b
      rate   = (cost_per_logo_a - cost_per_logo_b) x new_logos_a
  every other line: one 'spend' component
volume + price (or usage + rate + fixed, or headcount + rate) equals the line
variance exactly; the module raises if any month fails to tie to the cent.

Materiality (assumptions, category 'materiality'): a component is material
when |impact| >= the absolute floor AND |impact| >= the percentage of the
budget line, OR |impact| >= the absolute override.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

REVENUE_LINES = ["revenue_platform", "revenue_insights"]
PAYROLL_LINES = {"cogs_payroll": "COGS", "rd_payroll": "R&D", "sm_payroll": "S&M", "ga_payroll": "G&A"}
SPEND_LINES = ["cogs_third_party", "cogs_payment", "cogs_recruiting", "rd_recruiting", "rd_tooling",
               "rd_contractors", "sm_recruiting", "sm_commission", "ga_recruiting",
               "ga_rent", "ga_software", "ga_fixed"]
LINE_LABELS = {
    "revenue_platform": "Platform revenue", "revenue_insights": "Insights revenue",
    "cogs_cloud": "Cloud hosting", "cogs_third_party": "Third-party software and data",
    "cogs_payment": "Payment processing", "cogs_payroll": "Customer operations payroll",
    "cogs_recruiting": "Customer operations recruiting", "rd_payroll": "R&D payroll",
    "rd_recruiting": "R&D recruiting", "rd_tooling": "R&D tooling", "rd_contractors": "R&D contractors",
    "sm_payroll": "Sales and marketing payroll", "sm_recruiting": "Sales and marketing recruiting",
    "sm_commission": "Sales commission", "sm_programs": "Marketing programmes",
    "ga_payroll": "G&A payroll", "ga_recruiting": "G&A recruiting", "ga_rent": "Rent",
    "ga_software": "Software seats", "ga_fixed": "Fixed G&A",
}
TOL = 0.005  # USD


def _safe_div(a, b):
    return a / b if b else 0.0


def build_bridge(actual, budget, months: list, assumptions) -> pd.DataFrame:
    pa, pb = actual.pnl, budget.pnl
    aa, ab = actual.arr, budget.arr
    ca, cb = actual.cloud, budget.cloud
    abs_floor = assumptions.value("materiality_abs_usd")
    pct_floor = assumptions.value("materiality_pct")
    abs_override = assumptions.value("materiality_abs_override_usd")
    rows = []

    def add(m, line, component, bval, aval, impact, detail):
        rows.append({"month": m, "line": line, "line_label": LINE_LABELS[line], "component": component,
                     "budget": bval, "actual": aval, "impact": impact, "detail": detail})

    for m in months:
        # revenue: volume and price
        for line, cust_col, arpa_note in (("revenue_platform", "customers", "Platform"),
                                          ("revenue_insights", "insights_customers", "Insights")):
            cb_, ca_ = ab.at[m, cust_col], aa.at[m, cust_col]
            rb, ra = pb.at[m, line], pa.at[m, line]
            arpa_b, arpa_a = _safe_div(rb, cb_), _safe_div(ra, ca_)
            vol = (ca_ - cb_) * arpa_b
            price = (arpa_a - arpa_b) * ca_
            add(m, line, "volume", rb, ra, vol,
                f"{arpa_note} customers {ca_:,.0f} against {cb_:,.0f} budgeted")
            add(m, line, "price", rb, ra, price,
                f"{arpa_note} revenue per customer {arpa_a:,.0f} against {arpa_b:,.0f} budgeted (monthly)")
        # cloud: usage, rate, fixed
        ub, ua = cb.at[m, "units"], ca.at[m, "units"]
        vb = cb.at[m, "cost_committed"] + cb.at[m, "cost_ondemand"]
        va = ca.at[m, "cost_committed"] + ca.at[m, "cost_ondemand"]
        pb_u, pa_u = _safe_div(vb, ub), _safe_div(va, ua)
        add(m, "cogs_cloud", "usage", pb.at[m, "cogs_cloud"], pa.at[m, "cogs_cloud"], -((ua - ub) * pb_u),
            f"{ua:,.0f} compute units against {ub:,.0f} budgeted")
        add(m, "cogs_cloud", "rate", pb.at[m, "cogs_cloud"], pa.at[m, "cogs_cloud"], -((pa_u - pb_u) * ua),
            f"effective unit cost {pa_u:.4f} against {pb_u:.4f} budgeted")
        add(m, "cogs_cloud", "fixed", pb.at[m, "cogs_cloud"], pa.at[m, "cogs_cloud"],
            -(ca.at[m, "cost_fixed"] - cb.at[m, "cost_fixed"]),
            f"fixed cloud {ca.at[m, 'cost_fixed']:,.0f} against {cb.at[m, 'cost_fixed']:,.0f} budgeted")
        # payroll: headcount and rate
        for line, bucket in PAYROLL_LINES.items():
            fb, fa = pb.at[m, f"fte_{bucket}"], pa.at[m, f"fte_{bucket}"]
            cost_b, cost_a = pb.at[m, line], pa.at[m, line]
            rate_b, rate_a = _safe_div(cost_b, fb), _safe_div(cost_a, fa)
            add(m, line, "headcount", cost_b, cost_a, -((fa - fb) * rate_b),
                f"{fa:,.1f} FTE against {fb:,.1f} budgeted (budget net of vacancy allowance)")
            add(m, line, "rate", cost_b, cost_a, -((rate_a - rate_b) * fa),
                f"loaded cost per FTE {rate_a:,.0f} against {rate_b:,.0f} budgeted (monthly)")
        # marketing programmes: volume (new logos) and rate (spend per logo)
        lb, la = ab.at[m, "new_logos"], aa.at[m, "new_logos"]
        sb, sa = pb.at[m, "sm_programs"], pa.at[m, "sm_programs"]
        cpl_b, cpl_a = _safe_div(sb, lb), _safe_div(sa, la)
        add(m, "sm_programs", "volume", sb, sa, -((la - lb) * cpl_b),
            f"{la:,.0f} new logos against {lb:,.1f} budgeted")
        add(m, "sm_programs", "rate", sb, sa, -((cpl_a - cpl_b) * la),
            f"programme spend per new logo {cpl_a:,.0f} against {cpl_b:,.0f} budgeted")
        for line in SPEND_LINES:
            add(m, line, "spend", pb.at[m, line], pa.at[m, line], -(pa.at[m, line] - pb.at[m, line]),
                f"{pa.at[m, line]:,.0f} against {pb.at[m, line]:,.0f} budgeted")

    br = pd.DataFrame(rows)
    # the components must tie to each line and to EBITDA, every month
    for m in months:
        sub = br[br["month"] == m]
        for line, grp in sub.groupby("line"):
            sign = 1.0 if line in REVENUE_LINES else -1.0
            expected = sign * (pa.at[m, line] - pb.at[m, line])
            if abs(grp["impact"].sum() - expected) > TOL:
                raise AssertionError(f"bridge {m} {line}: components {grp['impact'].sum():.4f} != variance {expected:.4f}")
        d_ebitda = pa.at[m, "ebitda"] - pb.at[m, "ebitda"]
        if abs(sub["impact"].sum() - d_ebitda) > TOL:
            raise AssertionError(f"bridge {m}: total {sub['impact'].sum():.4f} != EBITDA variance {d_ebitda:.4f}")

    br["budget_line"] = br["budget"]
    br["material"] = ((br["impact"].abs() >= abs_floor) &
                      (br["impact"].abs() >= pct_floor * br["budget_line"].abs())) | \
                     (br["impact"].abs() >= abs_override)
    br["month"] = br["month"].astype(str)
    return br


def ytd_summary(bridge: pd.DataFrame, assumptions) -> pd.DataFrame:
    """Sum the monthly components over the bridge window and re-test materiality."""
    abs_floor = assumptions.value("materiality_abs_usd")
    pct_floor = assumptions.value("materiality_pct")
    abs_override = assumptions.value("materiality_abs_override_usd")
    g = bridge.groupby(["line", "line_label", "component"], as_index=False, sort=False)[["budget", "actual", "impact"]].sum()
    # budget/actual are per-line values repeated per component; take them once per line
    line_tot = bridge.drop_duplicates(["month", "line"]).groupby("line")[["budget", "actual"]].sum()
    g["budget"] = g["line"].map(line_tot["budget"])
    g["actual"] = g["line"].map(line_tot["actual"])
    g["material"] = ((g["impact"].abs() >= abs_floor) & (g["impact"].abs() >= pct_floor * g["budget"].abs())) | \
                    (g["impact"].abs() >= abs_override)
    return g


def line_summary(bridge: pd.DataFrame) -> pd.DataFrame:
    line_tot = bridge.drop_duplicates(["month", "line"]).groupby(["line", "line_label"], sort=False)[["budget", "actual"]].sum().reset_index()
    imp = bridge.groupby("line")["impact"].sum()
    line_tot["impact"] = line_tot["line"].map(imp)
    return line_tot
