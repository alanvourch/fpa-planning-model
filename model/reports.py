"""CFO memo (one page) and board pack (five slides), generated from the
facts dictionary. Templates live here; numbers come from model/facts.py.

Outputs:
  output/cfo_memo.md, output/cfo_memo.pdf     one page, asserted
  output/board_pack.pdf                       five pages, asserted
"""

from __future__ import annotations

import datetime as dt
import textwrap
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.backends.backend_pdf import PdfPages  # noqa: E402
from fpdf import FPDF  # noqa: E402

from . import facts as fx  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "output"

# palette (dataviz reference instance, light surface)
BLUE, ORANGE, AQUA, RED = "#2a78d6", "#eb6834", "#1baf7a", "#e34948"
INK, INK2, MUTED, LINE, SURFACE = "#171715", "#4f4e4a", "#85837d", "#e6e5de", "#fcfcfb"
SCEN = {"base": BLUE, "upside": AQUA, "downside": ORANGE}
FONT = "DejaVu Sans"
SHORT_LINE = {"Cloud hosting": "Cloud", "Customer operations payroll": "Cust. ops payroll",
              "Sales and marketing payroll": "S&M payroll", "Marketing programmes": "Programmes",
              "Sales commission": "Commission", "Software seats": "Software", "R&D contractors": "Contractors",
              "Third-party software and data": "Third-party", "Payment processing": "Payments",
              "Customer operations recruiting": "Cust. ops recruiting", "Sales and marketing recruiting": "S&M recruiting"}


def _wrap(text, width):
    return "\n".join(textwrap.wrap(text, width))

plt.rcParams.update({"font.family": FONT, "font.size": 11, "axes.edgecolor": LINE, "axes.labelcolor": INK2,
                     "xtick.color": INK2, "ytick.color": INK2, "axes.spines.top": False, "axes.spines.right": False,
                     "figure.facecolor": SURFACE, "axes.facecolor": SURFACE})


# ---------------------------------------------------------------- memo ----

def memo_text(F: dict) -> str:
    c = F["options"][F["chosen"]]
    front = F["options"].get("front_commit")
    hold = F["options"].get("hold_commit")
    od = F["options"].get(F["ondemand_twin"])
    lines = []
    lines.append("# CFO memo: headcount, cloud and product investment, next 18 months")
    lines.append("")
    lines.append(f"To: CEO, VP Engineering, Board finance committee. From: FP&A. "
                 f"Date: {dt.date.today().isoformat()}. Model: assumption set v{F['version']}, "
                 f"generated from the planning model, no figure typed by hand.")
    lines.append("")
    lines.append("## Decision")
    lines.append("")
    lines.append(f"Adopt the phased hiring plan with a one-year cloud commitment: {F['hires_total']} planned hires between "
                 f"{fx.month_name(F['first_hire_month'])} and {fx.month_name(F['last_hire_month'])} "
                 f"({F['hires_rd']} in R&D, {F['hires_sm']} in sales and marketing, {F['hires_ga']} in G&A), "
                 f"and a one-year cloud commitment of {F['commit_units']:,.0f} compute units a month at a "
                 f"{fx.pct(F['commit_discount'])} discount. Hold the front-loaded plan and the Insights "
                 f"contractor push until net retention recovers.")
    lines.append("")
    lines.append("## Where we stand")
    lines.append("")
    lines.append(f"ARR is {fx.musd(F['arr_now'])} at end {fx.month_name(F['as_of'])}, up {fx.pct(F['arr_growth_yoy'])} "
                 f"year on year, with {fx.musd(F['cash_now'])} of cash and a trailing net burn of {fx.kusd(F['burn_now'])} a month "
                 f"({fx.months_str(F['runway_now'])} of runway). Gross margin is {fx.pct(F['gm_now'], 1)} against "
                 f"{fx.pct(F['gm_budget_now'], 1)} budgeted for the month: cloud hosting has risen from {fx.pct(F['cloud_share_feb26'], 1)} of revenue in "
                 f"February to {fx.pct(F['cloud_share_now'], 1)} because Insights customers consume {fx.pct(F['insights_usage_step'])} more compute. Year to date, EBITDA is {fx.signed_kusd(F['ytd_ebitda_variance'])} against budget: "
                 f"late engineering hires ({fx.signed_kusd(F['bridge_rd_headcount'])}) and fewer new customers "
                 f"({fx.signed_kusd(F['bridge_platform_volume'])} of platform revenue) offset each other, while cloud usage "
                 f"({fx.signed_kusd(F['bridge_cloud_usage'])}) is the one variance that changes the plan.")
    lines.append("")
    lines.append("## Why this option")
    lines.append("")
    lines.append(f"- {F['n_options']} options were run through the same drivers under base, upside and downside "
                 f"({F['n_runs']} runs). Two guardrails apply: downside runway never below {F['min_runway']:.0f} months, "
                 f"and base gross margin never below {fx.pct(F['gm_floor'])}.")
    if front:
        lines.append(f"- The front-loaded plan ({front['listed_hires']} planned hires plus contractors) adds only "
                     f"{fx.musd(F['front_extra_arr_base'])} of ARR by {fx.month_name(F['horizon_end'])} in the base case and "
                     f"breaches the runway guardrail in the downside: {front['downside_runway_min']:.1f} months, "
                     f"{F['front_runway_shortfall']:.1f} short of the {F['min_runway']:.0f}-month floor, with cash bottoming at {fx.musd(front['cash_min_downside'])}.")
    if hold:
        lines.append(f"- The cost of the growth. Holding hiring also passes both guardrails. The phased plan burns "
                     f"{fx.musd(F['hold_burn_gap'])} more over 18 months to end {fx.musd(F['hold_arr_gap_base'])} higher in ARR, "
                     f"about USD {F['burn_per_extra_arr']:.1f} of burn per extra dollar of ARR, and gives the Insights product "
                     f"the squad its usage growth is paying for. The Q1 2027 retention review tests that trade.")
    if F["budget_floor_chosen"] != F["chosen"]:
        lines.append(f"- The runway floor decides the answer. At the budget's {F['budget_min_runway']:.0f}-month floor the model "
                     f"recommends {fx.option_phrase(F['budget_floor_chosen_label'])}; the board raised the floor to "
                     f"{F['min_runway']:.0f} months in {fx.month_name(F['runway_floor_changed'])}.")
    if od:
        lines.append(f"- Cloud on demand fails the margin floor (base minimum {fx.pct(od['base_gm_min'], 1)}). The "
                     f"commitment saves {fx.musd(F['commit_saving_base_18m'])} over 18 months in the base case and lifts "
                     f"the minimum gross margin by {fx.pts(F['commit_gm_gain_base'])}; the downside strands "
                     f"{fx.kusd(F['chosen_downside_stranded'])} of committed units, which is the price of the floor.")
    lines.append("")
    lines.append("## Scenarios for the recommended plan")
    lines.append("")
    lines.append("| Scenario | ARR at horizon end | Cash low point | Minimum runway | Minimum gross margin |")
    lines.append("|---|---|---|---|---|")
    for sc in ("base", "upside", "downside"):
        lines.append(f"| {sc.capitalize()} | {fx.musd(F[f'chosen_{sc}_arr_end'])} | {fx.musd(F[f'chosen_{sc}_cash_min'])} | "
                     f"{fx.months_str(F[f'chosen_{sc}_runway_min'])} | {fx.pct(F[f'chosen_{sc}_gm_min'], 1)} |")
    lines.append("")
    lines.append("## Risks")
    lines.append("")
    lines.append(f"- Net retention. The base assumes {fx.pct(F['nrr_base'])}; the downside {fx.pct(F['nrr_downside'])}. "
                 f"Each review of the change log has moved this driver down, not up.")
    lines.append(f"- Sales productivity. New customers per ramped account executive are {F['lpa_base']:.2f} a month in the base "
                 f"and {F['lpa_downside']:.2f} in the downside; the {F['hires_sm']} go-to-market hires only pay back if the "
                 f"base holds.")
    lines.append(f"- R&D weight. R&D is {fx.pct(F['rd_share_now'])} of revenue today, well above the benchmark range, which is "
                 f"why hiring is phased rather than front-loaded.")
    lines.append("")
    lines.append("## Asks")
    lines.append("")
    lines.append(f"1. Approve the phased hiring plan and the {F['hires_rd']} R&D requisitions in the order listed.")
    lines.append(f"2. Approve the one-year cloud commitment before the next renewal window.")
    lines.append(f"3. Revisit the front-loaded plan at the Q1 2027 review if net retention is at or above the base assumption.")
    return "\n".join(lines) + "\n"


def write_memo(F: dict) -> tuple[Path, Path]:
    md = memo_text(F)
    (OUT / "cfo_memo.md").write_text(md, encoding="utf-8")
    pdf = FPDF(orientation="P", unit="mm", format="A4")
    pdf.set_auto_page_break(auto=False)
    pdf.set_margins(16, 14, 16)
    pdf.add_page()
    width = 210 - 32
    for raw in md.splitlines():
        line = raw.rstrip()
        if not line:
            pdf.ln(1.6)
            continue
        if line.startswith("# "):
            pdf.set_font("Helvetica", "B", 13.5)
            pdf.multi_cell(width, 6, _latin(line[2:]))
            pdf.ln(0.5)
        elif line.startswith("## "):
            pdf.ln(0.8)
            pdf.set_font("Helvetica", "B", 10)
            pdf.multi_cell(width, 5, _latin(line[3:]))
        elif line.startswith("|"):
            cells = [c.strip() for c in line.strip("|").split("|")]
            if set("".join(cells)) <= set("-: "):
                continue
            pdf.set_font("Helvetica", "B" if cells[0] == "Scenario" else "", 8.2)
            w = [width * 0.16, width * 0.21, width * 0.21, width * 0.21, width * 0.21]
            for cw, cell in zip(w, cells):
                pdf.cell(cw, 4.6, _latin(cell), border="B")
            pdf.ln(4.6)
        elif line.startswith("- ") or line[:2].rstrip(".").isdigit():
            pdf.set_font("Helvetica", "", 8.6)
            pdf.set_x(20)
            pdf.multi_cell(width - 4, 4.1, _latin(line if not line.startswith("- ") else "- " + line[2:]))
        else:
            pdf.set_font("Helvetica", "", 8.6)
            pdf.multi_cell(width, 4.1, _latin(line))
    if pdf.pages_count != 1:
        raise AssertionError(f"memo must be one page, got {pdf.pages_count}")
    path = OUT / "cfo_memo.pdf"
    pdf.output(str(path))
    return OUT / "cfo_memo.md", path


def _latin(s: str) -> str:
    return s.encode("latin-1", "replace").decode("latin-1")


# ---------------------------------------------------------- board pack ----

def _title(fig, title, subtitle=None, n=None):
    fig.text(0.05, 0.93, title, fontsize=22, fontweight="bold", color=INK, va="top")
    if subtitle:
        fig.text(0.05, 0.865, subtitle, fontsize=12.5, color=INK2, va="top", wrap=True)
    fig.text(0.05, 0.035, "Northlight Software (fictional). Generated from the planning model; every figure traces to a model output.",
             fontsize=8.5, color=MUTED)
    if n:
        fig.text(0.95, 0.035, f"{n} / 5", fontsize=9, color=MUTED, ha="right")


def _tile(fig, x, y, w, h, label, value, note=None):
    fig.patches.append(plt.Rectangle((x, y), w, h, transform=fig.transFigure, facecolor="#ffffff",
                                     edgecolor=LINE, linewidth=1))
    fig.text(x + 0.015, y + h - 0.045, _wrap(label, 30), fontsize=10.5, color=MUTED, va="top")
    fig.text(x + 0.015, y + h - 0.11, value, fontsize=24, fontweight="bold", color=INK, va="top")
    if note:
        fig.text(x + 0.015, y + 0.03, _wrap(note, 36), fontsize=9.2, color=INK2, va="bottom", linespacing=1.25)


def _fmt_m(x, _=None):
    return f"{x / 1e6:.0f}M"


def slide_1(pdf, F):
    fig = plt.figure(figsize=(13.33, 7.5))
    c = F["options"][F["chosen"]]
    _title(fig, "Recommendation: " + c["label"], n=1)
    fig.text(0.05, 0.80, _wrap(f"{F['hires_total']} planned hires phased from {fx.month_name(F['first_hire_month'])} to {fx.month_name(F['last_hire_month'])}, "
             f"a one-year cloud commitment at a {fx.pct(F['commit_discount'])} discount, and the front-loaded plan held until net retention recovers.", 120),
             fontsize=13, color=INK2, va="top", linespacing=1.3)
    tiles = [
        ("ARR at end " + fx.month_name(F["as_of"]), fx.musd(F["arr_now"]), f"up {fx.pct(F['arr_growth_yoy'])} year on year"),
        ("Cash and runway", fx.musd(F["cash_now"]), f"{fx.months_str(F['runway_now'])} at the trailing burn of {fx.kusd(F['burn_now'])} a month"),
        ("Gross margin", fx.pct(F["gm_now"], 1), f"{fx.pts(F['gm_gap_vs_budget'])} below budget after the Insights usage step-up"),
        ("ARR at " + fx.month_name(F["horizon_end"]) + ", base", fx.musd(F["chosen_base_arr_end"]), f"{fx.musd(F['chosen_downside_arr_end'])} downside, {fx.musd(F['chosen_upside_arr_end'])} upside"),
    ]
    for i, (label, value, note) in enumerate(tiles):
        _tile(fig, 0.05 + i * 0.228, 0.42, 0.212, 0.26, label, value, note)
    fig.text(0.05, 0.33, "Guardrails applied to every option", fontsize=12, fontweight="bold", color=INK, va="top")
    fig.text(0.05, 0.285, _wrap(f"Downside cash runway never below {F['min_runway']:.0f} months in any month. "
             f"Base gross margin never below {fx.pct(F['gm_floor'])} in any month. "
             f"Objective: highest base-case ARR at {fx.month_name(F['horizon_end'])} among options that pass both.", 130),
             fontsize=11, color=INK2, va="top", linespacing=1.3)
    fig.text(0.05, 0.20, _wrap(f"Recommended plan in the downside: runway bottoms at {F['chosen_downside_runway_min']:.0f} months, cash at {fx.musd(F['chosen_downside_cash_min'])}, "
             f"gross margin at {fx.pct(F['chosen_downside_gm_min'], 1)}.", 130), fontsize=11, color=INK2, va="top", linespacing=1.3)
    pdf.savefig(fig)
    plt.close(fig)


def slide_2(pdf, F):
    fig = plt.figure(figsize=(13.33, 7.5))
    _title(fig, f"2026 so far: EBITDA {fx.signed_kusd(F['ytd_ebitda_variance'])} against budget",
           f"{fx.month_name(F['ytd_first'])} to {fx.month_name(F['ytd_last'])}. {F['n_material']} of {F['n_bridge_components']} driver components are material; the rest are grouped under All other.", n=2)
    ax = fig.add_axes([0.08, 0.30, 0.58, 0.48])
    rows = F["material_rows"]
    other = F["bridge_other"]
    steps = [("Budget EBITDA", F["ytd_budget_ebitda"], "total")] + \
            [(f"{SHORT_LINE.get(r['line_label'], r['line_label'])}, {r['component']}", r["impact"], "delta") for r in rows] + \
            [("All other", other, "delta"), ("Actual EBITDA", F["ytd_actual_ebitda"], "total")]
    level = 0.0
    labels = []
    for i, (label, val, kind) in enumerate(steps):
        if kind == "total":
            # totals as labelled reference levels, so the axis spans the deltas only
            level = val
            ax.hlines(val, i - 0.31, i + 0.31, color=INK, linewidth=2)
            below = i == len(steps) - 1
            ax.text(i, val - 12_000 if below else val + 12_000, fx.musd(val, 2), ha="center",
                    va="top" if below else "bottom", fontsize=8.5, color=INK2)
        else:
            bottom = level if val >= 0 else level + val
            height, color = abs(val), (BLUE if val >= 0 else RED)
            level += val
            ax.bar(i, height, bottom=bottom, color=color, width=0.62)
            ax.text(i, (bottom + height) + 12_000 if val >= 0 else bottom - 12_000, fx.signed_kusd(val), ha="center",
                    va="bottom" if val >= 0 else "top", fontsize=8.5, color=INK2)
        labels.append(label)
    ax.set_xticks(range(len(steps)))
    ax.set_xticklabels(labels, rotation=40, ha="right", fontsize=8)
    ax.yaxis.set_major_formatter(matplotlib.ticker.FuncFormatter(lambda x, _: f"{x / 1e6:.2f}M"))
    ax.margins(y=0.18)
    ax.grid(axis="y", color=LINE, linewidth=0.8)
    ax.set_axisbelow(True)
    ax.set_ylabel("USD, year to date")
    fig.text(0.70, 0.78, "What moved", fontsize=12, fontweight="bold", color=INK, va="top")
    notes = [
        f"Fewer customers than budget: {fx.signed_kusd(F['bridge_platform_volume'])} of platform revenue (sales productivity and churn).",
        f"Price increase landed at {fx.pct(F['price_step_actual_2026'])} against {fx.pct(F['price_step_budget_2026'])}: {fx.signed_kusd(F['bridge_platform_price'])}.",
        f"Insights compute usage up {fx.pct(F['insights_usage_step'])}: {fx.signed_kusd(F['bridge_cloud_usage'])} on cloud hosting.",
        f"Engineering hires two to five months late: {fx.signed_kusd(F['bridge_rd_headcount'])} on R&D payroll.",
        f"Programme spend per new customer over budget: {fx.signed_kusd(F['bridge_programs_rate'])}, more than offset by the smaller volume.",
    ]
    y = 0.73
    for n in notes:
        fig.text(0.70, y, _wrap("• " + n, 46), fontsize=9.6, color=INK2, va="top", linespacing=1.25)
        y -= 0.115
    pdf.savefig(fig)
    plt.close(fig)


def slide_3(pdf, F):
    fig = plt.figure(figsize=(13.33, 7.5))
    _title(fig, "Six options, two guardrails, one survivor per hiring plan",
           "Three hiring plans crossed with cloud on demand or a one-year commitment, each run under base, upside and downside.", n=3)
    opts = list(F["options"].keys())
    short = {o: F["options"][o]["label"].replace("; ", "\n") for o in opts}
    ax1 = fig.add_axes([0.22, 0.2, 0.30, 0.55])
    vals = [F["options"][o]["downside_runway_min"] for o in opts]
    colors = [BLUE if F["options"][o]["runway_ok"] else RED for o in opts]
    ax1.barh(range(len(opts)), vals, color=colors, height=0.55)
    ax1.axvline(F["min_runway"], color=INK, linewidth=1.2)
    ax1.text(F["min_runway"] + 0.5, len(opts) - 0.45, f"floor {F['min_runway']:.0f} months", fontsize=9, color=INK2)
    for i, v in enumerate(vals):
        ax1.text(v + 0.5, i, f"{v:.0f}", va="center", fontsize=9, color=INK2)
    ax1.set_yticks(range(len(opts)))
    ax1.set_yticklabels([short[o].replace("Front-loaded plan with Insights contractors", "Front-loaded plan\n+ Insights contractors") for o in opts], fontsize=8.8)
    ax1.set_xlabel("Minimum downside runway, months")
    ax1.invert_yaxis()
    ax1.grid(axis="x", color=LINE, linewidth=0.8)
    ax1.set_axisbelow(True)
    ax2 = fig.add_axes([0.60, 0.2, 0.33, 0.55])
    gm = [F["options"][o]["base_gm_min"] * 100 for o in opts]
    colors = [BLUE if F["options"][o]["gm_ok"] else RED for o in opts]
    ax2.barh(range(len(opts)), gm, color=colors, height=0.55)
    ax2.axvline(F["gm_floor"] * 100, color=INK, linewidth=1.2)
    ax2.text(F["gm_floor"] * 100 + 0.1, len(opts) - 0.45, f"floor {fx.pct(F['gm_floor'])}", fontsize=9, color=INK2)
    for i, v in enumerate(gm):
        ax2.text(v + 0.1, i, f"{v:.1f}%", va="center", fontsize=9, color=INK2)
    ax2.set_yticks(range(len(opts)))
    ax2.set_yticklabels(["" for _ in opts])
    ax2.set_xlim(70, 78)
    ax2.set_xlabel("Minimum base gross margin")
    ax2.invert_yaxis()
    ax2.grid(axis="x", color=LINE, linewidth=0.8)
    ax2.set_axisbelow(True)
    c = F["options"][F["chosen"]]
    fig.text(0.05, 0.11, _wrap(f"Blue passes, red fails. Recommended: {c['label'].lower()}, ARR {fx.musd(c['base_arr_end'])} at {fx.month_name(F['horizon_end'])} in the base case, "
             f"{fx.musd(F['front_extra_arr_base'])} less than the front-loaded plan, which fails the runway floor by {F['front_runway_shortfall']:.1f} months.", 140),
             fontsize=10.5, color=INK2, va="top", linespacing=1.3)
    pdf.savefig(fig)
    plt.close(fig)


def slide_4(pdf, F):
    fig = plt.figure(figsize=(13.33, 7.5))
    _title(fig, "The recommended plan: cash under three scenarios",
           _wrap(f"{F['hires_total']} planned hires ({F['hires_rd']} R&D, {F['hires_sm']} sales and marketing) plus a {F['commit_units']:,.0f}-unit cloud commitment. "
           f"Plan people cost over 18 months: {fx.musd(F['plan_hire_cost_18m'])}.", 125), n=4)
    ax = fig.add_axes([0.07, 0.17, 0.55, 0.58])
    for sc in ("upside", "base", "downside"):
        s = F[f"chosen_{sc}_series"]
        x = range(len(s["months"]))
        ax.plot(x, s["cash"], color=SCEN[sc], linewidth=2, label=sc.capitalize())
        ax.plot(x[-1], s["cash"][-1], "o", color=SCEN[sc], markersize=6, markeredgecolor=SURFACE, markeredgewidth=1.5)
        ax.text(x[-1] + 0.3, s["cash"][-1], f"{sc.capitalize()} {fx.musd(s['cash'][-1])}", fontsize=9, color=INK2, va="center")
    s = F["chosen_base_series"]
    ax.set_xticks(range(0, len(s["months"]), 3))
    ax.set_xticklabels([s["months"][i] for i in range(0, len(s["months"]), 3)], fontsize=9)
    ax.yaxis.set_major_formatter(matplotlib.ticker.FuncFormatter(_fmt_m))
    ax.set_ylabel("Closing cash, USD")
    ax.set_ylim(0, None)
    ax.grid(axis="y", color=LINE, linewidth=0.8)
    ax.set_axisbelow(True)
    ax.legend(frameon=False, loc="lower left", fontsize=9)
    ax.set_xlim(-0.5, len(s["months"]) + 4.5)
    # right: hiring table and outcomes
    fig.text(0.68, 0.74, "Hires by function and location", fontsize=12, fontweight="bold", color=INK, va="top")
    y = 0.69
    for func, n in F["hires_by_function"].items():
        fig.text(0.68, y, f"{func}: {n}", fontsize=10.5, color=INK2, va="top")
        y -= 0.045
    for loc, n in F["hires_by_location"].items():
        fig.text(0.82, 0.69 - 0.045 * list(F["hires_by_location"]).index(loc), f"{loc}: {n}", fontsize=10.5, color=INK2, va="top")
    fig.text(0.68, 0.47, "Outcomes at " + fx.month_name(F["horizon_end"]), fontsize=12, fontweight="bold", color=INK, va="top")
    y = 0.42
    for sc in ("base", "upside", "downside"):
        fig.text(0.68, y, _wrap(f"{sc.capitalize()}: ARR {fx.musd(F[f'chosen_{sc}_arr_end'])}, cash low {fx.musd(F[f'chosen_{sc}_cash_min'])}, "
                 f"runway min {fx.months_str(F[f'chosen_{sc}_runway_min'])}", 48), fontsize=9.8, color=INK2, va="top", linespacing=1.25)
        y -= 0.075
    pdf.savefig(fig)
    plt.close(fig)


def slide_5(pdf, F):
    fig = plt.figure(figsize=(13.33, 7.5))
    _title(fig, "Risks, and what the board is asked to approve", n=5)
    risks = [
        ("Net retention keeps slipping", f"Base {fx.pct(F['nrr_base'])}, downside {fx.pct(F['nrr_downside'])}. Every review since the budget has moved it down. The downside case already carries {fx.pct(F['nrr_downside'])} and still passes both guardrails for the recommended plan."),
        ("Sales productivity does not recover", f"{F['lpa_base']:.2f} new customers per ramped account executive a month in the base, {F['lpa_downside']:.2f} in the downside. The {F['hires_sm']} go-to-market hires are the first to defer if Q4 2026 stays at the 2026 run rate."),
        ("Committed cloud units go unused", f"The downside strands {fx.kusd(F['chosen_downside_stranded'])} over 18 months against a base-case saving of {fx.musd(F['commit_saving_base_18m'])}. The commitment is sized at {fx.pct(F['commit_coverage'])} of expected base usage for this reason."),
        ("R&D weight", f"R&D is {fx.pct(F['rd_share_now'])} of revenue, above the benchmark range for equity-backed SaaS. The phased plan grows R&D more slowly than revenue; the front-loaded plan would not."),
    ]
    y = 0.80
    for title, body in risks:
        fig.text(0.05, y, title, fontsize=12, fontweight="bold", color=INK, va="top")
        fig.text(0.05, y - 0.045, _wrap(body, 78), fontsize=9.8, color=INK2, va="top", linespacing=1.25)
        y -= 0.17
    fig.text(0.60, 0.80, "Decisions requested", fontsize=12, fontweight="bold", color=INK, va="top")
    asks = [
        f"Approve the phased hiring plan: {F['hires_total']} requisitions, {fx.month_name(F['first_hire_month'])} to {fx.month_name(F['last_hire_month'])}.",
        "Approve the one-year cloud commitment before the next renewal window.",
        "Defer the front-loaded plan and the Insights contractor push to the Q1 2027 review, conditional on net retention at or above the base assumption.",
        f"Keep the two guardrails as standing policy: {F['min_runway']:.0f} months of downside runway, {fx.pct(F['gm_floor'])} gross margin floor.",
    ]
    y = 0.74
    for i, a in enumerate(asks, start=1):
        fig.text(0.60, y, _wrap(f"{i}. {a}", 56), fontsize=10.5, color=INK2, va="top", linespacing=1.25)
        y -= 0.13
    pdf.savefig(fig)
    plt.close(fig)


def write_board_pack(F: dict) -> Path:
    path = OUT / "board_pack.pdf"
    with PdfPages(path) as pdf:
        for fn in (slide_1, slide_2, slide_3, slide_4, slide_5):
            fn(pdf, F)
        n = pdf.get_pagecount()
    if n != 5:
        raise AssertionError(f"board pack must be five pages, got {n}")
    return path


def write_og_image(F: dict) -> Path:
    """1200x630 link preview for the case page: the recommendation and its two numbers."""
    fig = plt.figure(figsize=(12, 6.3), dpi=100)
    fig.text(0.06, 0.80, "HEADCOUNT AND CLOUD PLAN", fontsize=13, fontweight="bold", color=BLUE, va="top")
    fig.text(0.06, 0.70, "Hire in phases, commit the cloud.", fontsize=34, fontweight="bold", color=INK, va="top")
    fig.text(0.06, 0.555, "Hold the bigger plan until retention proves out.", fontsize=19, color=INK2, va="top")
    fig.text(0.06, 0.40, _wrap(f"{fx.musd(F['chosen_base_arr_end'])} of ARR by {fx.month_name(F['horizon_end'])} in the base case, "
             f"runway never below {F['chosen_downside_runway_min']:.0f} months in the downside. Front-loading adds "
             f"{fx.musd(F['front_extra_arr_base'])} of ARR and breaks the {F['min_runway']:.0f}-month runway floor.", 110),
             fontsize=13, color=INK2, va="top", linespacing=1.5)
    fig.add_artist(plt.Line2D([0.06, 0.94], [0.21, 0.21], transform=fig.transFigure, color=LINE, linewidth=1.2))
    fig.text(0.06, 0.13, "Alan Vourc'h   |   alanvourch.com/fpa-planning-model   |   synthetic data, real method",
             fontsize=11.5, color=MUTED, va="top")
    path = OUT / "og.png"
    fig.savefig(path, dpi=100, facecolor=SURFACE, metadata={"Software": None})
    plt.close(fig)
    return path


def write_all() -> dict:
    F = fx.build()
    md, pdf = write_memo(F)
    pack = write_board_pack(F)
    og = write_og_image(F)
    return {"facts": F, "memo_md": md, "memo_pdf": pdf, "board_pack": pack, "og": og}
