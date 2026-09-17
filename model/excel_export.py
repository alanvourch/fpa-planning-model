"""Excel export a finance person can open, follow and audit without code.

Sheets (in reading order):
  README         what each sheet holds, sign conventions, how to audit
  Assumptions    every driver with base/upside/downside, unit, source label
  Change log     the versioned log of assumption changes
  Locations      employer tax, benefits, rent by location, with sources
  Salary table   annual salary by role and location
  Hiring plans   candidate hiring plans and the FY2026 budget plan
  Options        the allocation options evaluated, with the verdict
  Actuals P&L    monthly actuals Sep 2024 to Aug 2026 (values + formula subtotals)
  Budget FY2026  the budget as locked (values + formula subtotals)
  Bridge YTD     actual versus budget, Jan to Aug 2026, by driver component
  <Option> Base / Upside / Downside
                 the recommended option's three scenarios: P&L, ARR
                 roll-forward, cloud and cash, with formula subtotals and the
                 cash roll-forward as formulas
  Workforce      recommended option, base: FTE and people cost by function
                 and location per month
  Checks         formulas that recompute every subtotal from the detail and
                 show the difference (all must be zero)

Leaf values are written by Python; every subtotal, margin, roll-forward and
check is an Excel formula so the reader can click into the derivation.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd
from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

from . import assumptions as asm

HEAD = Font(bold=True)
TITLE = Font(bold=True, size=13)
NOTE = Font(italic=True, color="666666")
INPUT_FILL = PatternFill("solid", fgColor="FFF6DD")   # leaf values written by Python
FORMULA_FILL = PatternFill("solid", fgColor="E8F1FB")  # Excel formulas
MONEY = '#,##0;[Red](#,##0)'
PCT = '0.0%'
NUM = '#,##0.0'

PNL_ROWS = [
    # (label, key or formula-spec, number format)
    ("Platform revenue", "revenue_platform", MONEY),
    ("Insights revenue", "revenue_insights", MONEY),
    ("Revenue", ("sum", ["revenue_platform", "revenue_insights"]), MONEY),
    ("Cloud hosting", "cogs_cloud", MONEY),
    ("Third-party software and data", "cogs_third_party", MONEY),
    ("Payment processing", "cogs_payment", MONEY),
    ("Customer operations payroll", "cogs_payroll", MONEY),
    ("Customer operations recruiting", "cogs_recruiting", MONEY),
    ("Cost of revenue", ("sum", ["cogs_cloud", "cogs_third_party", "cogs_payment", "cogs_payroll", "cogs_recruiting"]), MONEY),
    ("Gross profit", ("diff", "revenue", "cogs"), MONEY),
    ("Gross margin", ("ratio", "gross_profit", "revenue"), PCT),
    ("R&D payroll", "rd_payroll", MONEY),
    ("R&D recruiting", "rd_recruiting", MONEY),
    ("R&D tooling", "rd_tooling", MONEY),
    ("R&D contractors", "rd_contractors", MONEY),
    ("R&D total", ("sum", ["rd_payroll", "rd_recruiting", "rd_tooling", "rd_contractors"]), MONEY),
    ("Sales and marketing payroll", "sm_payroll", MONEY),
    ("Sales and marketing recruiting", "sm_recruiting", MONEY),
    ("Sales commission", "sm_commission", MONEY),
    ("Marketing programmes", "sm_programs", MONEY),
    ("Sales and marketing total", ("sum", ["sm_payroll", "sm_recruiting", "sm_commission", "sm_programs"]), MONEY),
    ("G&A payroll", "ga_payroll", MONEY),
    ("G&A recruiting", "ga_recruiting", MONEY),
    ("Rent", "ga_rent", MONEY),
    ("Software seats", "ga_software", MONEY),
    ("Fixed G&A", "ga_fixed", MONEY),
    ("G&A total", ("sum", ["ga_payroll", "ga_recruiting", "ga_rent", "ga_software", "ga_fixed"]), MONEY),
    ("Operating expenses", ("sum3", ["rd_total", "sm_total", "ga_total"]), MONEY),
    ("EBITDA", ("diff", "gross_profit", "opex"), MONEY),
    ("EBITDA margin", ("ratio", "ebitda", "revenue"), PCT),
    ("FTE total", "fte_total", NUM),
    ("FTE customer operations", "fte_COGS", NUM),
    ("FTE R&D", "fte_R&D", NUM),
    ("FTE sales and marketing", "fte_S&M", NUM),
    ("FTE G&A", "fte_G&A", NUM),
    ("Total ARR (closing)", "arr_total", MONEY),
]
KEY_ALIASES = {"revenue": "Revenue", "cogs": "Cost of revenue", "gross_profit": "Gross profit",
               "rd_total": "R&D total", "sm_total": "Sales and marketing total", "ga_total": "G&A total",
               "opex": "Operating expenses", "ebitda": "EBITDA"}

ARR_ROWS = [
    ("Opening Platform ARR", "opening_arr", MONEY), ("New ARR", "new_arr", MONEY),
    ("Expansion ARR", "expansion_arr", MONEY), ("Price ARR", "price_arr", MONEY),
    ("Churned ARR", "churn_arr", MONEY),
    ("Closing Platform ARR", ("sum", ["opening_arr", "new_arr", "expansion_arr", "price_arr", "churn_arr"]), MONEY),
    ("Opening customers", "opening_customers", NUM), ("New logos", "new_logos", NUM),
    ("Churned customers", "churned_customers", NUM),
    ("Closing customers", ("sum", ["opening_customers", "new_logos", "churned_customers"]), NUM),
    ("Insights attach rate", "attach_rate", PCT), ("Insights customers", "insights_customers", NUM),
    ("Insights ARR per customer", "arpa_insights", MONEY), ("Insights ARR", "arr_insights", MONEY),
    ("Total ARR", ("sum", ["closing_arr", "arr_insights"]), MONEY),
]
CLOUD_ROWS = [
    ("Platform compute units", "units_platform", NUM), ("Insights compute units", "units_insights", NUM),
    ("Total units", ("sum", ["units_platform", "units_insights"]), NUM),
    ("Committed units", "commit_units", NUM), ("On-demand unit price", "unit_price", '0.0000'),
    ("Commitment discount", "commit_discount", PCT),
    ("Committed cost", ("cloud_commit",), MONEY), ("On-demand cost", ("cloud_ondemand",), MONEY),
    ("Fixed cloud cost", "cost_fixed", MONEY),
    ("Cloud hosting total", ("sum", ["cost_committed", "cost_ondemand", "cost_fixed"]), MONEY),
]
CASH_ROWS = [
    ("Opening cash", ("cash_open",), MONEY), ("EBITDA", "ebitda", MONEY), ("Equipment capex", "capex", MONEY),
    ("Change in receivables", "delta_ar", MONEY), ("Change in deferred revenue", "delta_deferred", MONEY),
    ("Financing", "financing", MONEY),
    ("Net cash flow", ("sum", ["ebitda", "capex", "delta_ar", "delta_deferred", "financing"]), MONEY),
    ("Closing cash", ("cash_close",), MONEY),
    ("Receivables", "ar", MONEY), ("Deferred revenue", "deferred_revenue", MONEY),
    ("Net burn, trailing 3 months", "net_burn_3m", MONEY), ("Runway (months)", "runway_months", NUM),
]


LABEL_KEYS = {"Revenue": "revenue", "Cost of revenue": "cogs", "Gross profit": "gross_profit",
              "R&D total": "rd_total", "Sales and marketing total": "sm_total", "G&A total": "ga_total",
              "Operating expenses": "opex", "EBITDA": "ebitda", "Closing Platform ARR": "closing_arr",
              "Closing customers": "customers", "Total units": "units", "Committed cost": "cost_committed",
              "On-demand cost": "cost_ondemand", "Cloud hosting total": "cloud_total", "Total ARR": "arr_total",
              "Net cash flow": "net_cash_flow", "Opening cash": "opening_cash", "Closing cash": "closing_cash",
              "Gross margin": "gross_margin", "EBITDA margin": "ebitda_margin"}


def _write_block(ws, top: int, title: str, rows: list, df: pd.DataFrame, months: list, key_to_row: dict,
                 checks: list, sheet_name: str, opening_cash: float | None = None) -> int:
    """Write a labelled block; return the next free row. key_to_row maps df
    keys to worksheet rows so later formulas can refer to them."""
    ws.cell(row=top, column=1, value=title).font = TITLE
    r = top + 1
    ws.cell(row=r, column=1, value="USD, monthly").font = NOTE
    for j, m in enumerate(months):
        c = ws.cell(row=r, column=2 + j, value=str(m))
        c.font = HEAD
        c.alignment = Alignment(horizontal="right")
    r += 1
    # first pass: assign a worksheet row to every key so formulas can refer
    # forward (the opening-cash row refers to the closing-cash row below it)
    for i, (label, spec, fmt) in enumerate(rows):
        key = spec if isinstance(spec, str) else LABEL_KEYS.get(label)
        if key:
            key_to_row[key] = r + i
    for label, spec, fmt in rows:
        ws.cell(row=r, column=1, value=label)
        if isinstance(spec, str):
            key_to_row[spec] = r
            for j, m in enumerate(months):
                c = ws.cell(row=r, column=2 + j, value=float(df.at[m, spec]))
                c.number_format = fmt
                c.fill = INPUT_FILL
        else:
            kind = spec[0]
            for j, m in enumerate(months):
                col = get_column_letter(2 + j)
                prev = get_column_letter(1 + j)
                if kind == "sum":
                    f = "=" + "+".join(f"{col}{key_to_row[k]}" for k in spec[1])
                elif kind == "sum3":
                    f = "=" + "+".join(f"{col}{key_to_row[k]}" for k in spec[1])
                elif kind == "diff":
                    f = f"={col}{key_to_row[spec[1]]}-{col}{key_to_row[spec[2]]}"
                elif kind == "ratio":
                    f = f"=IF({col}{key_to_row[spec[2]]}=0,0,{col}{key_to_row[spec[1]]}/{col}{key_to_row[spec[2]]})"
                elif kind == "cloud_commit":
                    f = f"=MIN({col}{key_to_row['units']},{col}{key_to_row['commit_units']})*{col}{key_to_row['unit_price']}*(1-{col}{key_to_row['commit_discount']})"
                elif kind == "cloud_ondemand":
                    f = f"=MAX({col}{key_to_row['units']}-{col}{key_to_row['commit_units']},0)*{col}{key_to_row['unit_price']}"
                elif kind == "cash_open":
                    f = f"={opening_cash}" if j == 0 else f"={prev}{key_to_row['closing_cash']}"
                elif kind == "cash_close":
                    f = f"={col}{key_to_row['opening_cash']}+{col}{key_to_row['net_cash_flow']}"
                else:
                    raise ValueError(kind)
                c = ws.cell(row=r, column=2 + j, value=f)
                c.number_format = fmt
                c.fill = FORMULA_FILL
            key = LABEL_KEYS.get(label)
            # every formula row is checked against the Python value in the Checks sheet
            if key and key in df.columns:
                checks.append((sheet_name, label, r, key, df, months))
        r += 1
    ws.cell(row=r, column=1, value="Shaded yellow: values from the model. Shaded blue: Excel formulas.").font = NOTE
    return r + 2


def _autosize(ws, first_width=34, other_width=13):
    ws.column_dimensions["A"].width = first_width
    for col in range(2, ws.max_column + 1):
        ws.column_dimensions[get_column_letter(col)].width = other_width
    ws.freeze_panes = "B3"


def _df_sheet(wb, name: str, df: pd.DataFrame, note: str | None = None, widths: dict | None = None):
    ws = wb.create_sheet(name)
    r = 1
    if note:
        ws.cell(row=1, column=1, value=note).font = NOTE
        r = 3
    for j, col in enumerate(df.columns):
        ws.cell(row=r, column=1 + j, value=str(col)).font = HEAD
    for i, row in enumerate(df.itertuples(index=False)):
        for j, v in enumerate(row):
            if isinstance(v, (pd.Period,)):
                v = str(v)
            elif pd.isna(v) if not isinstance(v, str) else False:
                v = None
            elif hasattr(v, "item"):
                v = v.item()
            ws.cell(row=r + 1 + i, column=1 + j, value=v)
    for j, col in enumerate(df.columns):
        ws.column_dimensions[get_column_letter(1 + j)].width = (widths or {}).get(col, 16)
    ws.freeze_panes = ws.cell(row=r + 1, column=1)
    return ws


def _result_sheet(wb, name: str, res, checks: list, opening_cash: float):
    ws = wb.create_sheet(name)
    months = res.months
    k = {}
    top = _write_block(ws, 1, f"{name}: P&L", PNL_ROWS, res.pnl, months, k, checks, name)
    ka = {}
    top = _write_block(ws, top, f"{name}: ARR roll-forward", ARR_ROWS, res.arr, months, ka, checks, name)
    kc = {}
    top = _write_block(ws, top, f"{name}: cloud hosting", CLOUD_ROWS, res.cloud, months, kc, checks, name)
    kcash = {}
    _write_block(ws, top, f"{name}: cash", CASH_ROWS, res.cash, months, kcash, checks, name, opening_cash=opening_cash)
    _autosize(ws)
    return ws


def export(path: Path, a: asm.Assumptions, actual, budget, bridge_ytd: pd.DataFrame, decision: dict) -> Path:
    wb = Workbook()
    ws = wb.active
    ws.title = "README"
    lines = [
        ("Northlight Software: driver-based planning model", TITLE),
        (f"Assumption set v{a.version}. Generated by run_model.py; every number in this file comes from the model outputs.", NOTE),
        ("", None),
        ("How to read this workbook", HEAD),
        ("1. Assumptions: every driver, its value in each scenario, and whether it is anchored on a published benchmark, derived from a published rate table, or a judgment call.", None),
        ("2. Change log: what changed since the FY2026 budget was locked (v1.0), when, by whom and why. Snapshot + log = current values.", None),
        ("3. Actuals P&L and Budget FY2026: monthly detail. Yellow cells are values from the model; blue cells are Excel formulas you can click into.", None),
        ("4. Bridge YTD: January to August 2026 actual versus budget, by driver component. Impact is the effect on EBITDA, favorable positive. The components sum to the EBITDA variance.", None),
        ("5. The three scenario sheets hold the recommended option: P&L, ARR roll-forward, cloud and cash, with subtotals and the cash roll-forward as formulas.", None),
        ("6. Workforce: FTE and people cost per month by function and location for the recommended option, base scenario.", None),
        ("7. Checks: every formula subtotal recomputed against the model value. All differences must be zero.", None),
        ("", None),
        ("Conventions", HEAD),
        ("Revenue = closing ARR / 12. Net revenue retention is all-in (includes the January price increase). Cloud cost = min(units, commitment) x price x (1 - discount) + overage x price + fixed.", None),
        ("Cash = opening + EBITDA - capex - change in receivables + change in deferred revenue + financing. Runway = closing cash / trailing three-month average net burn.", None),
        ("No interest, income tax, depreciation or capitalized development. Plan headcount carries a vacancy allowance (expected leavers x backfill lag) as a negative fractional seat.", None),
        ("", None),
        (f"Recommended option: {decision['chosen']} ({a.options.at[decision['chosen'], 'label']}). Basis: {decision['basis']}.", HEAD),
        (f"Guardrails: downside runway at least {decision['min_runway']:.0f} months in every month; base gross margin at least {decision['gm_floor']:.0%} in every month.", None),
    ]
    for i, (text, font) in enumerate(lines, start=1):
        c = ws.cell(row=i, column=1, value=text)
        if font:
            c.font = font
    ws.column_dimensions["A"].width = 150

    t = a.table.reset_index()
    _df_sheet(wb, "Assumptions", t[["id", "category", "name", "unit", "base", "upside", "downside", "source_type", "source"]],
              "One row per driver. source_type: benchmark = published survey figure (named), derived = computed from a published rate table, judgment = own call.",
              {"id": 34, "name": 60, "source": 90, "category": 16})
    _df_sheet(wb, "Change log", asm.read_changelog(), "Every change to assumptions.csv since v1.0. Replaying this log onto the v1.0 snapshot reproduces the current file (tested).", {"reason": 110, "assumption_id": 34})
    _df_sheet(wb, "Locations", a.locations.reset_index(), None, {"source": 120})
    _df_sheet(wb, "Salary table", a.salaries.reset_index(), "Annual salary in USD by role and location; sales_role = commission plan, no bonus accrual.", {"role": 28})
    _df_sheet(wb, "Hiring plans", a.hiring_plans, "phased and front_loaded are the candidate plans; fy2026_budget is the plan inside the FY2026 budget.", {"rationale": 40, "role": 28})
    verdict = decision["verdict"].copy()
    _df_sheet(wb, "Options", verdict, "One row per option: guardrail results and headline outcomes. Feasible = both guardrails hold.", {"label": 60})
    grid = decision["grid"].copy()
    _df_sheet(wb, "Option grid", grid, "Every option under every scenario: 18 runs of the same engine.")

    checks = []
    _result_sheet(wb, "Actuals", actual, checks, float(actual.cash["opening_cash"].iloc[0]))
    _result_sheet(wb, "Budget FY2026", budget, checks, float(budget.cash["opening_cash"].iloc[0]))
    _df_sheet(wb, "Bridge YTD", bridge_ytd[["line_label", "component", "budget", "actual", "impact", "material"]],
              "January to August 2026, actual versus budget. impact = effect on EBITDA (favorable positive). Components sum to the EBITDA variance.", {"line_label": 34})
    chosen = decision["chosen"]
    for sc in asm.SCENARIOS:
        res = decision["runs"][(chosen, sc)]
        _result_sheet(wb, f"Plan {sc}", res, checks, float(res.cash["opening_cash"].iloc[0]))
    base = decision["runs"][(chosen, "base")]
    wf = base.workforce.groupby(["month", "function", "location"], as_index=False)[["fte", "people_cost", "recruiting", "capex"]].sum()
    wf["month"] = wf["month"].astype(str)
    _df_sheet(wb, "Workforce", wf, f"Recommended option ({chosen}), base scenario. FTE is net of the vacancy allowance.")

    # Checks sheet: formula cell vs model value, difference must be zero
    wc = wb.create_sheet("Checks")
    wc.cell(row=1, column=1, value="Every formula subtotal in the workbook, recomputed against the model value. Difference must be 0.").font = NOTE
    hdr = ["Sheet", "Line", "Months checked", "Sum of formula cells", "Sum of model values", "Difference"]
    for j, h in enumerate(hdr):
        wc.cell(row=3, column=1 + j, value=h).font = HEAD
    r = 4
    for sheet, label, row, key, df, months in checks:
        first, last = get_column_letter(2), get_column_letter(1 + len(months))
        wc.cell(row=r, column=1, value=sheet)
        wc.cell(row=r, column=2, value=label)
        wc.cell(row=r, column=3, value=len(months))
        wc.cell(row=r, column=4, value=f"=SUM('{sheet}'!{first}{row}:{last}{row})").fill = FORMULA_FILL
        wc.cell(row=r, column=5, value=float(df[key].sum())).fill = INPUT_FILL
        wc.cell(row=r, column=6, value=f"=ROUND(D{r}-E{r},4)").fill = FORMULA_FILL
        r += 1
    wc.cell(row=r + 1, column=1, value="Total absolute difference").font = HEAD
    wc.cell(row=r + 1, column=6, value=f"=SUMPRODUCT(ABS(F4:F{r - 1}))").fill = FORMULA_FILL
    for col, w in zip("ABCDEF", (18, 34, 14, 22, 22, 14)):
        wc.column_dimensions[col].width = w

    wb.save(path)
    return path
