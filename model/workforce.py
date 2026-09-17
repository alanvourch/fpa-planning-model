"""Workforce engine: positions in, monthly people cost out.

A position is one seat: role, function, cost bucket, location, start month,
optional end month (exclusive), annual salary at start. The engine turns a
positions table into one row per position per month with:

  fte           1.0 while the seat is filled, else the row is absent
  salary        annual salary / 12, after every January merit increase the
                person was present for
  bonus         salary x bonus rate (non-sales roles only; sales commission is
                computed on new ARR in the P&L engine, not here)
  employer_tax  (salary + bonus) x the location's employer tax rate
  benefits      salary x the location's benefits rate
  recruiting    one-time, start month only, salary_annual x recruiting rate
  capex         one-time, start month only, equipment per hire (cash, not P&L)
  tenure_months months since start (0 in the start month), used for ramps

Attrition is handled two ways, deliberately:
  actuals   the roster carries real end dates and real backfills
  plan      a vacancy allowance: expected leavers x backfill lag, applied as a
            negative row per month, cost bucket and location, so headcount
            in the plan is a fractional expected value, as in most corporate
            workforce plans
"""

from __future__ import annotations

import numpy as np
import pandas as pd

POSITION_COLUMNS = [
    "position_id", "role", "function", "cost_bucket", "sales_role", "location",
    "start", "end", "salary", "origin",
]
COST_COLUMNS = ["salary", "bonus", "employer_tax", "benefits", "recruiting", "capex"]


def month_range(start: str, n: int) -> list:
    p = pd.Period(start, freq="M")
    return [p + i for i in range(n)]


def make_positions(rows: list[dict], assumptions) -> pd.DataFrame:
    """Build a positions table from dicts with role, location, start, optional
    end, optional salary (defaults to the salary table), origin, count."""
    out = []
    for i, r in enumerate(rows):
        role = r["role"]
        if role not in assumptions.salaries.index:
            raise KeyError(f"role {role!r} not in salary table")
        loc = r["location"]
        if loc not in assumptions.locations.index:
            raise KeyError(f"location {loc!r} not in locations table")
        meta = assumptions.salaries.loc[role]
        count = int(r.get("count", 1))
        if count < 1:
            raise ValueError(f"count must be >= 1 for {role} {loc} {r['start']}")
        start = pd.Period(r["start"], freq="M")
        end = r.get("end")
        end = pd.Period(end, freq="M") if end not in (None, "", float("nan")) and not (isinstance(end, float) and np.isnan(end)) else pd.NaT
        if end is not pd.NaT and end <= start:
            raise ValueError(f"end must be after start for {role} {loc} {start}")
        salary = float(r["salary"]) if r.get("salary") not in (None, "") and not (isinstance(r.get("salary"), float) and np.isnan(r.get("salary"))) else assumptions.salary(role, loc)
        for k in range(count):
            out.append({
                "position_id": r.get("position_id") or f"{r.get('origin','pos')}-{i:04d}-{k}",
                "role": role,
                "function": meta["function"],
                "cost_bucket": meta["cost_bucket"],
                "sales_role": bool(meta["sales_role"]),
                "location": loc,
                "start": start,
                "end": end,
                "salary": salary,
                "origin": r.get("origin", "plan"),
            })
    df = pd.DataFrame(out, columns=POSITION_COLUMNS)
    # keep start/end as Period objects (an all-missing end column would otherwise
    # be coerced to datetime64 and refuse Period values later)
    df["start"] = pd.Series([o["start"] for o in out], dtype=object, index=df.index)
    df["end"] = pd.Series([o["end"] for o in out], dtype=object, index=df.index)
    return df


def monthly_workforce(positions: pd.DataFrame, months: list, assumptions, scenario: str,
                      vacancy_allowance: bool) -> pd.DataFrame:
    """One row per filled position per month, plus vacancy rows if requested."""
    merit = assumptions.value("merit_increase_pct_jan", scenario)
    bonus_pct = assumptions.value("bonus_pct_non_sales", scenario)
    recruiting_pct = assumptions.value("recruiting_cost_pct_salary", scenario)
    capex_per_hire = assumptions.value("capex_per_new_hire_usd", scenario)
    first, last = months[0], months[-1]

    rows = []
    for p in positions.itertuples(index=False):
        if p.start > last:
            continue
        p_end = p.end
        tax = assumptions.location_param(p.location, "employer_tax_rate")
        ben = assumptions.location_param(p.location, "benefits_rate")
        for m in months:
            if m < p.start:
                continue
            if p_end is not pd.NaT and m >= p_end:
                continue
            # merit: count Januaries after the start month, up to and including m
            n_jan = sum(1 for y in range(p.start.year, m.year + 1)
                        if pd.Period(year=y, month=1, freq="M") > p.start
                        and pd.Period(year=y, month=1, freq="M") <= m)
            annual = p.salary * (1.0 + merit) ** n_jan
            salary_m = annual / 12.0
            bonus = 0.0 if p.sales_role else salary_m * bonus_pct
            is_start = (m == p.start) and (p.start >= first)
            rows.append({
                "month": m,
                "position_id": p.position_id,
                "role": p.role,
                "function": p.function,
                "cost_bucket": p.cost_bucket,
                "sales_role": p.sales_role,
                "location": p.location,
                "origin": p.origin,
                "fte": 1.0,
                "tenure_months": (m - p.start).n,
                "salary": salary_m,
                "bonus": bonus,
                "employer_tax": (salary_m + bonus) * tax,
                "benefits": salary_m * ben,
                "recruiting": p.salary * recruiting_pct if is_start else 0.0,
                "capex": capex_per_hire if is_start else 0.0,
            })
    wf = pd.DataFrame(rows)
    if wf.empty:
        raise ValueError("no positions active in the month window")

    if vacancy_allowance:
        attr_m = assumptions.value("attrition_annual", scenario) / 12.0
        lag = assumptions.value("backfill_lag_months", scenario)
        factor = attr_m * lag  # expected open-seat share of the filled base
        grp = wf.groupby(["month", "cost_bucket", "location"], as_index=False)[
            ["fte", "salary", "bonus", "employer_tax", "benefits"]].sum()
        vac = grp.copy()
        for c in ["fte", "salary", "bonus", "employer_tax", "benefits"]:
            vac[c] = -grp[c] * factor
        vac["position_id"] = "vacancy-allowance"
        vac["role"] = "Vacancy allowance"
        vac["function"] = vac["cost_bucket"].map(
            {"COGS": "Customer Operations", "R&D": "R&D", "S&M": "S&M", "G&A": "G&A"})
        vac["sales_role"] = False
        vac["origin"] = "vacancy"
        vac["tenure_months"] = 0
        vac["recruiting"] = 0.0
        vac["capex"] = 0.0
        wf = pd.concat([wf, vac[wf.columns]], ignore_index=True)

    wf["people_cost"] = wf["salary"] + wf["bonus"] + wf["employer_tax"] + wf["benefits"]
    return wf


def ramped_capacity(wf: pd.DataFrame, role: str, ramp_months: float) -> pd.Series:
    """Sum over positions of min(1, tenure/ramp): fully ramped equivalents per
    month for the given role. The start month counts as zero."""
    sub = wf[(wf["role"] == role) & (wf["fte"] > 0)].copy()
    if sub.empty:
        return pd.Series(dtype=float)
    ramp = max(float(ramp_months), 1e-9)
    sub["ramp"] = np.minimum(1.0, sub["tenure_months"] / ramp)
    return sub.groupby("month")["ramp"].sum()


def summarize(wf: pd.DataFrame, months: list) -> pd.DataFrame:
    """FTE and people cost by month and cost bucket (wide), for the P&L."""
    agg = wf.groupby(["month", "cost_bucket"])[["fte", "people_cost", "recruiting", "capex"]].sum()
    idx = pd.MultiIndex.from_product([months, ["COGS", "R&D", "S&M", "G&A"]],
                                     names=["month", "cost_bucket"])
    agg = agg.reindex(idx, fill_value=0.0)
    wide = agg.unstack("cost_bucket")
    wide.columns = [f"{a}_{b}" for a, b in wide.columns]
    wide["fte_total"] = wide[[c for c in wide.columns if c.startswith("fte_")]].sum(axis=1)
    return wide
