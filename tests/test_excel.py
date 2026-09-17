"""The Excel export agrees with the Python output.

Two layers:
  1. openpyxl reads the workbook back: every value cell (yellow) equals the
     model output it was written from, sheet by sheet; every formula cell
     references rows on its own sheet (no broken references).
  2. If Microsoft Excel is installed (Windows COM), the workbook is opened,
     recalculated, and every formula result is compared to the Python
     value, including the Checks sheet whose total difference must be 0.
     Skipped cleanly where Excel is absent.
"""

import os
import re
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
from openpyxl import load_workbook

from model import assumptions as asm

ROOT = Path(__file__).resolve().parents[1]
XLSX = ROOT / "output" / "northlight_planning_model.xlsx"


@pytest.fixture(scope="module")
def wb():
    if not XLSX.exists():
        pytest.skip("run run_model.py first")
    return load_workbook(XLSX)


def _block_values(ws, title_prefix: str) -> dict:
    """Return {row label: [values...]} for the block whose title starts with prefix."""
    rows = list(ws.iter_rows(values_only=True))
    start = next(i for i, r in enumerate(rows) if r[0] and str(r[0]).startswith(title_prefix))
    out = {}
    for r in rows[start + 2:]:
        if r[0] is None or str(r[0]).startswith("Shaded"):
            break
        out[r[0]] = list(r[1:])
    return out


def test_value_cells_match_model_outputs(wb, world):
    actual = world["actual"]
    blk = _block_values(wb["Actuals"], "Actuals: P&L")
    assert np.allclose([v for v in blk["Platform revenue"] if v is not None], actual.pnl["revenue_platform"].values)
    assert np.allclose([v for v in blk["Cloud hosting"] if v is not None], actual.pnl["cogs_cloud"].values)
    assert np.allclose([v for v in blk["FTE total"] if v is not None], actual.pnl["fte_total"].values)
    blk = _block_values(wb["Actuals"], "Actuals: cash")
    assert np.allclose([v for v in blk["EBITDA"] if v is not None], actual.cash["ebitda"].values)
    assert np.allclose([v for v in blk["Runway (months)"] if v is not None], actual.cash["runway_months"].values)


def test_assumptions_sheet_matches_registry(wb, assumptions):
    ws = wb["Assumptions"]
    rows = list(ws.iter_rows(min_row=3, values_only=True))
    header, body = rows[0], rows[1:]
    df = pd.DataFrame(body, columns=header).set_index("id")
    for aid in assumptions.table.index:
        for sc in asm.SCENARIOS:
            assert float(df.at[aid, sc]) == pytest.approx(assumptions.value(aid, sc))


def test_formulas_reference_own_sheet_rows(wb):
    ref = re.compile(r"\$?([A-Z]{1,3})\$?(\d+)")
    for name in ("Actuals", "Budget FY2026", "Plan base", "Plan upside", "Plan downside"):
        ws = wb[name]
        max_row = ws.max_row
        n_formula = 0
        for row in ws.iter_rows():
            for c in row:
                if isinstance(c.value, str) and c.value.startswith("="):
                    n_formula += 1
                    assert "!" not in c.value, (name, c.coordinate)
                    for _, rr in ref.findall(c.value):
                        assert 1 <= int(rr) <= max_row, (name, c.coordinate, c.value)
        assert n_formula > 100, name


def test_bridge_sheet_ties(wb, world):
    ws = wb["Bridge YTD"]
    rows = list(ws.iter_rows(min_row=3, values_only=True))
    df = pd.DataFrame(rows[1:], columns=rows[0])
    actual, budget = world["actual"], world["budget"]
    months = [m for m in budget.months if m <= actual.months[-1]]
    assert df["impact"].sum() == pytest.approx(actual.pnl.loc[months, "ebitda"].sum() - budget.pnl.loc[months, "ebitda"].sum(), abs=0.05)


@pytest.mark.skipif(os.name != "nt", reason="Excel COM recalculation is Windows-only")
def test_excel_recalculates_to_python_values(world, decision):
    try:
        import win32com.client  # noqa: F401
    except ImportError:
        pytest.skip("pywin32 not installed")
    import pythoncom
    pythoncom.CoInitialize()
    try:
        app = win32com.client.DispatchEx("Excel.Application")
    except Exception as e:  # Excel not installed
        pytest.skip(f"Excel not available: {e}")
    app.Visible = False
    app.DisplayAlerts = False
    try:
        book = app.Workbooks.Open(str(XLSX), ReadOnly=True)
        app.CalculateFullRebuild()
        checks = book.Worksheets("Checks")
        last = checks.Cells(checks.Rows.Count, 1).End(-4162).Row  # xlUp
        total_cell = checks.Cells(last, 6).Value
        assert total_cell is not None
        assert abs(float(total_cell)) < 0.01, f"Checks sheet total difference {total_cell}"
        n = 0
        for r in range(4, last - 1):
            diff = checks.Cells(r, 6).Value
            if diff is None:
                continue
            assert abs(float(diff)) < 0.01, (checks.Cells(r, 1).Value, checks.Cells(r, 2).Value, diff)
            n += 1
        assert n >= 40
        # spot check: recalculated EBITDA in the plan base sheet equals Python
        res = decision["runs"][(decision["chosen"], "base")]
        ws = book.Worksheets("Plan base")
        labels = {ws.Cells(i, 1).Value: i for i in range(1, 60)}
        row = labels["EBITDA"]
        got = [ws.Cells(row, 2 + j).Value for j in range(len(res.months))]
        assert np.allclose(got, res.pnl["ebitda"].values, atol=0.01)
        book.Close(SaveChanges=False)
        del ws, checks, book
    finally:
        app.Quit()
        del app
        pythoncom.CoUninitialize()
