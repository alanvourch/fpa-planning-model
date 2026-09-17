"""Synthetic actuals for Northlight Software: 24 months (September 2024 to
August 2026) of realized drivers, a workforce roster with real start and end
dates, and the P&L, ARR, cloud and cash that follow from them, plus the FY2026
budget as it was locked in December 2025 (assumption snapshot v1.0).

Everything is generated from one fixed seed. The realized drivers deviate from
the budget in six planted ways, listed here (this docstring is the answer key
that tests/test_bridge.py checks against) and recovered by the bridge:

  1. New logos per ramped account executive ran at 0.92 against 1.10 budgeted
  2. Gross retention fell to 87.5% (annualized) in H1 2026 against 90%; net
     retention 103% against 106%
  3. The January 2026 price increase landed at 6% against 5%
  4. Insights customers' compute usage stepped up from 1,500 to 2,000 units a
     month from March 2026 (the budget carried 1,500)
  5. Ten budgeted R&D hires started two to five months late, two never started
  6. Marketing programmes ran at USD 30.7k per new logo against 28k, plus a
     USD 120k conference in May 2026

The actual P&L is produced by the same engine as the plan, from these
realized drivers, so the bridge compares like with like. That is also the
reason it reconciles exactly (see README, Known limitations).
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

from . import assumptions as asm, engine, plan, workforce as wf_mod

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
SEED = 20260917
ACTUAL_START, N_ACTUAL = "2024-09", 24
BUDGET_START, N_BUDGET = "2026-01", 12
BUDGET_VERSION = "1.0"

# (role, location, count) filled at September 2024
INITIAL_ROSTER = [
    ("Software Engineer", "Montreal", 15), ("Senior Software Engineer", "Montreal", 10),
    ("Engineering Manager", "Montreal", 3), ("Product Manager", "Montreal", 3),
    ("Product Designer", "Montreal", 2), ("Data Engineer", "Montreal", 2),
    ("Software Engineer", "Paris", 6), ("Senior Software Engineer", "Paris", 6),
    ("Engineering Manager", "Paris", 1), ("Product Manager", "Paris", 1), ("Data Engineer", "Paris", 2),
    ("Site Reliability Engineer", "Montreal", 3), ("Site Reliability Engineer", "Paris", 1),
    ("Customer Success Manager", "Austin", 7), ("Customer Success Manager", "Montreal", 4),
    ("Support Engineer", "Montreal", 7),
    ("Account Executive", "Austin", 7), ("Sales Development Rep", "Austin", 5),
    ("Marketing Manager", "Austin", 5), ("Marketing Manager", "Montreal", 1),
    ("Finance & Operations", "Montreal", 5), ("People & Talent", "Montreal", 3),
    ("Executive", "Montreal", 4), ("Executive", "Austin", 1),
]

# realized hires September 2024 to December 2025 (role, location, start, count)
HIRES_2024_2025 = [
    ("Software Engineer", "Montreal", "2024-10", 1), ("Account Executive", "Austin", "2024-11", 1),
    ("Software Engineer", "Paris", "2024-11", 1), ("Software Engineer", "Montreal", "2025-01", 2),
    ("Customer Success Manager", "Austin", "2025-01", 1), ("Sales Development Rep", "Austin", "2025-01", 1),
    ("Senior Software Engineer", "Paris", "2025-02", 1), ("Account Executive", "Austin", "2025-02", 1),
    ("Software Engineer", "Paris", "2025-03", 2), ("Product Manager", "Montreal", "2025-03", 1),
    ("Account Executive", "Austin", "2025-04", 1), ("Support Engineer", "Montreal", "2025-04", 1),
    ("Software Engineer", "Montreal", "2025-05", 2), ("Data Engineer", "Paris", "2025-05", 1),
    ("Customer Success Manager", "Austin", "2025-06", 1), ("Marketing Manager", "Austin", "2025-06", 1),
    ("Account Executive", "Austin", "2025-07", 2), ("Sales Development Rep", "Austin", "2025-07", 1),
    ("Senior Software Engineer", "Montreal", "2025-08", 1), ("Software Engineer", "Paris", "2025-09", 2),
    ("Product Designer", "Montreal", "2025-09", 1), ("Account Executive", "Austin", "2025-10", 1),
    ("Customer Success Manager", "Montreal", "2025-10", 1), ("Finance & Operations", "Montreal", "2025-10", 1),
    ("Software Engineer", "Montreal", "2025-11", 1), ("Site Reliability Engineer", "Montreal", "2025-11", 1),
    ("People & Talent", "Montreal", "2025-12", 1),
]

# realized 2026 hires against the FY2026 budget plan (planted deviation 5)
HIRES_2026 = [
    ("Software Engineer", "Montreal", "2026-03", 2), ("Software Engineer", "Montreal", "2026-05", 1),
    ("Senior Software Engineer", "Montreal", "2026-04", 1), ("Senior Software Engineer", "Montreal", "2026-07", 1),
    ("Software Engineer", "Paris", "2026-04", 2), ("Software Engineer", "Paris", "2026-07", 1),
    ("Data Engineer", "Paris", "2026-05", 1),
    ("Account Executive", "Austin", "2026-01", 2), ("Sales Development Rep", "Austin", "2026-02", 1),
    ("Customer Success Manager", "Austin", "2026-03", 2), ("Finance & Operations", "Montreal", "2026-03", 1),
]

OPENING_2024_09 = {
    "customers": 380.0, "arr_platform": 11_500_000.0, "attach_rate": 0.12,
    "arpa_insights": 11_500.0, "acv_new": 34_000.0, "cloud_unit_price": 0.44, "cash": 21_000_000.0,
}
SERIES_C_EXTENSION = {"month": "2026-03", "amount": 25_000_000.0}


def _months():
    return wf_mod.month_range(ACTUAL_START, N_ACTUAL)


def build_roster(a: asm.Assumptions, rng: np.random.Generator) -> pd.DataFrame:
    months = _months()
    rows, pid = [], 0
    first = pd.Period("2019-01", freq="M")
    span = (pd.Period("2024-08", freq="M") - first).n
    for role, loc, n in INITIAL_ROSTER:
        for _ in range(n):
            start = first + int(rng.integers(0, span + 1))
            rows.append({"position_id": f"emp-{pid:04d}", "role": role, "location": loc,
                         "start": str(start), "salary": a.salary(role, loc) * rng.uniform(0.92, 1.10),
                         "origin": "roster"})
            pid += 1
    for role, loc, start, n in HIRES_2024_2025 + HIRES_2026:
        for _ in range(n):
            rows.append({"position_id": f"emp-{pid:04d}", "role": role, "location": loc, "start": start,
                         "salary": a.salary(role, loc) * rng.uniform(0.97, 1.05), "origin": "roster"})
            pid += 1
    roster = wf_mod.make_positions(rows, a)
    roster["position_id"] = [r["position_id"] for r in rows]
    # leavers: 0.9% a month, executives excluded; 70% backfilled two or three months later
    monthly_p = 0.009
    backfills = []
    for m in months:
        active = roster[(roster["start"] <= m) & (roster["end"].isna()) & (roster["role"] != "Executive")]
        for idx in active.index:
            if rng.uniform() < monthly_p:
                roster.at[idx, "end"] = m + 1  # last month worked is m
                if rng.uniform() < 0.70:
                    lag = int(rng.integers(2, 4))
                    backfills.append({"position_id": f"emp-{pid:04d}", "role": roster.at[idx, "role"],
                                      "location": roster.at[idx, "location"], "start": str(m + 1 + lag),
                                      "salary": a.salary(roster.at[idx, "role"], roster.at[idx, "location"]) * rng.uniform(0.97, 1.05),
                                      "origin": "roster"})
                    pid += 1
    if backfills:
        bf = wf_mod.make_positions(backfills, a)
        bf["position_id"] = [b["position_id"] for b in backfills]
        roster = pd.concat([roster, bf], ignore_index=True)
    roster = roster[roster["start"] <= months[-1]].reset_index(drop=True)
    return roster


def realized_drivers(a: asm.Assumptions, wf: pd.DataFrame, rng: np.random.Generator) -> pd.DataFrame:
    months = _months()
    n = len(months)
    y26 = np.array([m.year == 2026 for m in months])
    h1_26 = np.array([m.year == 2026 and m.month <= 6 for m in months])
    from_mar26 = np.array([m >= pd.Period("2026-03", freq="M") for m in months])

    grr = np.where(h1_26, 0.875, np.where(y26, 0.885, 0.90))
    nrr = np.where(y26, 1.03, 1.06)          # all-in, including the January price increase
    price_year = np.where(y26, 0.06, 0.05)   # the price step is carried separately below
    churn_m = (1.0 - grr ** (1 / 12)) * rng.uniform(0.92, 1.08, n)
    exp_m = ((nrr - price_year) ** (1 / 12) - grr ** (1 / 12)) * rng.uniform(0.92, 1.08, n)
    price_step = np.array([0.05 if m == pd.Period("2025-01", freq="M") else 0.06 if m == pd.Period("2026-01", freq="M") else 0.0 for m in months])
    lpa = np.where(y26, 0.92, 1.08)
    cap = wf_mod.ramped_capacity(wf, "Account Executive", a.value("ae_ramp_months")).reindex(months).fillna(0.0).values
    seas = np.array([a.seasonality[m.month] for m in months])
    new_logos = np.round(cap * lpa * seas * rng.uniform(0.90, 1.10, n))
    attach = OPENING_2024_09["attach_rate"] + np.cumsum(np.where(y26, 0.005, 0.006))
    arpa_ins = OPENING_2024_09["arpa_insights"] * np.cumprod(np.full(n, 1.01))
    acv = OPENING_2024_09["acv_new"] * np.cumprod(1.0 + price_step)
    upc = 200.0 * rng.uniform(0.97, 1.03, n)
    upic = np.where(from_mar26, 2000.0, 1500.0) * rng.uniform(0.97, 1.03, n)
    unit_price = OPENING_2024_09["cloud_unit_price"] * np.cumprod(np.full(n, 0.998))
    cloud_fixed = np.where(y26, 28_000.0, 25_000.0)
    programs = new_logos * np.where(y26, 30_700.0, 28_000.0) + np.array([120_000.0 if m == pd.Period("2026-05", freq="M") else 0.0 for m in months])
    contractors = np.where(y26, 60_000.0, 55_000.0)
    ga_fixed = np.where(y26, 75_000.0, 72_000.0)
    financing = np.array([SERIES_C_EXTENSION["amount"] if str(m) == SERIES_C_EXTENSION["month"] else 0.0 for m in months])
    return pd.DataFrame({
        "month": months, "new_logos": new_logos, "churn_rate_m": churn_m, "expansion_rate_m": exp_m,
        "price_step": price_step, "attach_rate": attach, "arpa_insights": arpa_ins, "acv_new": acv,
        "units_per_platform_customer": upc, "units_per_insights_customer": upic,
        "cloud_unit_price": unit_price, "cloud_fixed": cloud_fixed, "commit_units": 0.0,
        "commit_discount": 0.0, "third_party_pct": 0.03, "payment_pct": 0.025, "annual_share": 0.40,
        "dso_days": 45.0, "commission_pct": 0.10, "marketing_programs": programs,
        "rd_contractors": contractors, "rd_tooling_per_head": 450.0, "ga_software_per_head": 180.0,
        "ga_fixed": ga_fixed, "financing": financing,
    })


def opening_actuals() -> engine.Opening:
    o = OPENING_2024_09
    arr_total = o["arr_platform"] + o["customers"] * o["attach_rate"] * o["arpa_insights"]
    revenue = arr_total / 12.0
    return engine.Opening(customers=o["customers"], arr_platform=o["arr_platform"], cash=o["cash"],
                          ar=revenue * 45.0 / 30.0, deferred=0.40 * arr_total * 5.5 / 12.0)


def state_after(result: engine.Result, month) -> dict:
    """Opening state for a plan that starts the month after `month`."""
    arr, cash, d = result.arr, result.cash, result.drivers
    return {
        "as_of": str(month), "customers": float(arr.at[month, "customers"]),
        "arr_platform": float(arr.at[month, "closing_arr"]), "attach_rate": float(arr.at[month, "attach_rate"]),
        "arpa_insights": float(arr.at[month, "arpa_insights"]), "acv_new": float(d.at[month, "acv_new"]),
        "cloud_unit_price": float(d.at[month, "cloud_unit_price"]), "cash": float(cash.at[month, "closing_cash"]),
        "ar": float(cash.at[month, "ar"]), "deferred": float(cash.at[month, "deferred_revenue"]),
        "arr_total": float(arr.at[month, "arr_total"]), "fte_total": float(result.pnl.at[month, "fte_total"]),
    }


def generate(write: bool = True):
    a = asm.load()
    rng = np.random.default_rng(SEED)
    months = _months()
    roster = build_roster(a, rng)
    wf = wf_mod.monthly_workforce(roster, months, a, "base", vacancy_allowance=False)
    drivers = realized_drivers(a, wf, rng)
    actual = engine.run(months, drivers, wf, opening_actuals(), a)

    # FY2026 budget: snapshot v1.0, base scenario, roster as known at December 2025
    snap = asm.load_snapshot(BUDGET_VERSION)
    dec25 = pd.Period("2025-12", freq="M")
    budget_months = wf_mod.month_range(BUDGET_START, N_BUDGET)
    budget = plan.build_plan(snap, "base", "fy2026_budget", roster, state_after(actual, dec25), budget_months)

    if write:
        DATA.mkdir(exist_ok=True)
        r = roster.copy()
        r["start"] = r["start"].astype(str)
        r["end"] = r["end"].apply(lambda x: "" if x is pd.NaT else str(x))
        r.to_csv(DATA / "roster_actuals.csv", index=False)
        drivers.assign(month=drivers["month"].astype(str)).to_csv(DATA / "drivers_actuals.csv", index=False)
        _write_result(actual, DATA, "actuals")
        _write_result(budget, DATA, "budget_fy2026")
        (DATA / "opening_state_2026-09.json").write_text(json.dumps(state_after(actual, months[-1]), indent=2))
    return a, roster, wf, drivers, actual, budget


def _write_result(res: engine.Result, folder: Path, prefix: str) -> None:
    for name in ("pnl", "arr", "cloud", "cash"):
        df = getattr(res, name).copy()
        df.index = df.index.astype(str)
        df.to_csv(folder / f"{prefix}_{name}.csv", index_label="month")
    p = res.product.copy()
    p["month"] = p["month"].astype(str)
    p.to_csv(folder / f"{prefix}_product.csv", index=False)
    w = res.workforce.copy()
    w["month"] = w["month"].astype(str)
    w.to_csv(folder / f"{prefix}_workforce.csv", index=False)


if __name__ == "__main__":
    a, roster, wf, drivers, actual, budget = generate()
    last = actual.months[-1]
    print(f"actuals {actual.months[0]} to {last}: roster rows {len(roster)}, FTE at end {actual.pnl.at[last, 'fte_total']:.0f}")
    print(f"ARR total at {last}: {actual.arr.at[last, 'arr_total']/1e6:.2f}M; revenue {actual.pnl.at[last, 'revenue']/1e6:.3f}M/month")
    print(f"gross margin {actual.pnl.at[last, 'gross_margin']:.1%}; EBITDA {actual.pnl.at[last, 'ebitda']/1e6:.3f}M; cash {actual.cash.at[last, 'closing_cash']/1e6:.1f}M")
