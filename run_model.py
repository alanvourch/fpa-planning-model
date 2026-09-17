"""Run the whole model: dataset, bridge, scenarios, decision, exports, reports, site.

Usage: .venv/Scripts/python.exe run_model.py
Deterministic: two runs produce identical files apart from the timestamp line.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd

from model import assumptions as asm, bridge as bridge_mod, dataset, decision as decision_mod, excel_export, plan, reports

ROOT = Path(__file__).resolve().parent
OUT = ROOT / "output"


def main(argv=None) -> None:
    OUT.mkdir(exist_ok=True)
    (OUT / "scenarios").mkdir(exist_ok=True)
    a = asm.load()
    print(f"assumptions v{a.version}: {len(a.table)} drivers, {int((a.table.source_type == 'benchmark').sum())} benchmark-anchored, "
          f"{int((a.table.source_type == 'judgment').sum())} judgment calls")

    print("--- 1. dataset (actuals Sep 2024 to Aug 2026, FY2026 budget) ---")
    a, roster, wf, drivers, actual, budget = dataset.generate()
    last = actual.months[-1]
    print(f"ARR {actual.arr.at[last, 'arr_total']/1e6:.1f}M, revenue {actual.pnl.at[last, 'revenue']/1e6:.2f}M/month, "
          f"gross margin {actual.pnl.at[last, 'gross_margin']:.1%}, cash {actual.cash.at[last, 'closing_cash']/1e6:.1f}M, FTE {actual.pnl.at[last, 'fte_total']:.0f}")

    print("--- 2. actual-versus-plan bridge (Jan to Aug 2026) ---")
    bridge_months = [m for m in budget.months if m <= last]
    br = bridge_mod.build_bridge(actual, budget, bridge_months, a)
    br.to_csv(OUT / "bridge_components.csv", index=False)
    ytd = bridge_mod.ytd_summary(br, a)
    ytd.to_csv(OUT / "bridge_ytd.csv", index=False)
    d_ebitda = actual.pnl.loc[bridge_months, "ebitda"].sum() - budget.pnl.loc[bridge_months, "ebitda"].sum()
    print(f"EBITDA variance {d_ebitda/1e3:,.0f}k, {len(ytd)} components, {int(ytd.material.sum())} material YTD, "
          f"bridge total {ytd.impact.sum()/1e3:,.0f}k (ties: {abs(ytd.impact.sum()-d_ebitda) < 0.01})")

    print("--- 3. scenarios and decision ---")
    opening = json.loads((ROOT / "data" / "opening_state_2026-09.json").read_text())
    months = plan.horizon()
    dec = decision_mod.evaluate(a, roster, opening, months)
    dec["grid"].to_csv(OUT / "option_grid.csv", index=False)
    dec["verdict"].to_csv(OUT / "option_verdict.csv", index=False)
    for (opt, sc), res in dec["runs"].items():
        dataset._write_result(res, OUT / "scenarios", f"{opt}__{sc}")
    pd.set_option("display.width", 220)
    v = dec["verdict"].copy()
    for c in ["base_arr_end", "base_cum_burn", "upside_arr_end", "downside_arr_end", "downside_cash_min"]:
        v[c] = (v[c] / 1e6).round(1)
    v["downside_runway_min"] = v["downside_runway_min"].round(1)
    v["base_gm_min"] = (v["base_gm_min"] * 100).round(1)
    print(v.drop(columns=["label"]).to_string(index=False))
    print(f"commit sized at {dec['commit_units']:,.0f} units/month; chosen: {dec['chosen']} ({dec['basis']})")
    summary = {"version": a.version, "chosen": dec["chosen"], "basis": dec["basis"], "commit_units": dec["commit_units"],
               "min_runway": dec["min_runway"], "gm_floor": dec["gm_floor"], "horizon": [str(months[0]), str(months[-1])],
               "opening": opening}
    (OUT / "decision.json").write_text(json.dumps(summary, indent=2))

    print("--- 4. Excel export ---")
    xlsx = excel_export.export(OUT / "northlight_planning_model.xlsx", a, actual, budget, ytd, dec)
    print(f"wrote {xlsx.name}")

    print("--- 5. memo and board pack ---")
    docs = reports.write_all()
    print(f"wrote {docs['memo_md'].name}, {docs['memo_pdf'].name} (1 page), {docs['board_pack'].name} (5 pages)")

    print("--- 6. web page ---")
    import build_site
    print(f"wrote {build_site.build().relative_to(ROOT)}")
    return a, roster, actual, budget, br, ytd, dec


if __name__ == "__main__":
    main(sys.argv[1:])
