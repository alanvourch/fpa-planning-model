"""Build site/index.html, a single self-contained page, from the model
outputs. Every number on the page comes from model/facts.py; charts are
inline SVG drawn here. The page works opened from disk and on a static host.

Also copies the Excel model, the memo and the board pack into site/assets/
so the page's links resolve relative to itself.

Run: .venv/Scripts/python.exe build_site.py   (after run_model.py)
"""

from __future__ import annotations

import html
import shutil
from pathlib import Path

from model import assumptions as asm, facts as fx

ROOT = Path(__file__).resolve().parent
SITE = ROOT / "site"
OUT = ROOT / "output"

BLUE, ORANGE, AQUA, RED = "#2a78d6", "#eb6834", "#1baf7a", "#e34948"
MUTED, LINE, INK2 = "#85837d", "#e6e5de", "#4f4e4a"
SCEN = {"base": BLUE, "upside": AQUA, "downside": ORANGE}


# ------------------------------------------------------------ svg helpers --

def _nice_ticks(lo: float, hi: float, n: int = 5) -> list[float]:
    import math
    span = hi - lo if hi > lo else 1.0
    raw = span / n
    mag = 10 ** math.floor(math.log10(raw))
    step = min((s for s in (1, 2, 2.5, 5, 10) if s * mag >= raw), key=lambda s: s) * mag
    start = math.floor(lo / step) * step
    ticks = []
    t = start
    while t <= hi + 1e-9:
        ticks.append(round(t, 10))
        t += step
    if ticks[-1] < hi - 1e-9:
        ticks.append(round(t, 10))
    return ticks


def line_chart(series: dict, months: list, ylabel: str, fmt, width=760, height=320, y0_zero=True,
               floor: float | None = None, floor_label: str = "", mr: int = 150) -> str:
    """series: {name: (values, color)}. Legend + end labels, hairline grid, hover titles."""
    ml, mt, mb = 56, 18, 44
    pw, ph = width - ml - mr, height - mt - mb
    allv = [v for vals, _ in series.values() for v in vals]
    lo = 0.0 if y0_zero else min(allv)
    hi = max(allv)
    if floor is not None:
        lo, hi = min(lo, floor), max(hi, floor)
    ticks = _nice_ticks(lo, hi)
    lo, hi = ticks[0], ticks[-1]
    sx = lambda i: ml + pw * i / max(1, len(months) - 1)  # noqa: E731
    sy = lambda v: mt + ph * (1 - (v - lo) / (hi - lo))  # noqa: E731
    out = [f'<svg class="chart" viewBox="0 0 {width} {height}" role="img" aria-label="{html.escape(ylabel)} by month">']
    for t in ticks:
        out.append(f'<line x1="{ml}" x2="{ml + pw}" y1="{sy(t):.1f}" y2="{sy(t):.1f}" stroke="{LINE}" stroke-width="1"/>')
        out.append(f'<text x="{ml - 8}" y="{sy(t) + 4:.1f}" text-anchor="end" class="tick axis">{fmt(t)}</text>')
    step = 3
    for i in range(0, len(months), step):
        out.append(f'<text x="{sx(i):.1f}" y="{height - mb + 18}" text-anchor="middle" class="tick">{months[i]}</text>')
    if floor is not None:
        out.append(f'<line x1="{ml}" x2="{ml + pw}" y1="{sy(floor):.1f}" y2="{sy(floor):.1f}" stroke="#171715" stroke-width="1.2"/>')
        out.append(f'<text x="{ml + 6}" y="{sy(floor) - 6:.1f}" class="tick">{html.escape(floor_label)}</text>')
    for name, (vals, color) in series.items():
        pts = " ".join(f"{sx(i):.1f},{sy(v):.1f}" for i, v in enumerate(vals))
        out.append(f'<polyline points="{pts}" fill="none" stroke="{color}" stroke-width="2" stroke-linejoin="round" stroke-linecap="round"/>')
        for i, v in enumerate(vals):
            out.append(f'<circle cx="{sx(i):.1f}" cy="{sy(v):.1f}" r="4" fill="{color}" stroke="#fcfcfb" stroke-width="2" opacity="{1 if i == len(vals) - 1 else 0}"><title>{html.escape(name)}, {months[i]}: {fmt(v)}</title></circle>')
        out.append(f'<text x="{ml + pw + 10}" y="{sy(vals[-1]) + 4:.1f}" class="endlabel">{html.escape(name)} {fmt(vals[-1])}</text>')
    out.append(f'<text x="{ml}" y="{12}" class="tick">{html.escape(ylabel)}</text>')
    out.append("</svg>")
    legend = "".join(f'<span class="lg"><i style="background:{c}"></i>{html.escape(n)}</span>' for n, (_, c) in series.items())
    return f'<div class="legend">{legend}</div>' + "".join(out)


def waterfall(steps: list, width=760, height=420) -> str:
    """steps: [(label, value, kind)] kind in total|delta. Favorable blue, unfavorable red."""
    ml, mr, mt, mb = 70, 20, 24, 150
    pw, ph = width - ml - mr, height - mt - mb
    level, lows, highs = 0.0, [], []
    bars = []
    for label, val, kind in steps:
        if kind == "total":
            bottom, top = min(0.0, val), max(0.0, val)
            level = val
            color = MUTED
        else:
            bottom, top = (level, level + val) if val >= 0 else (level + val, level)
            level += val
            color = BLUE if val >= 0 else RED
        bars.append((label, val, kind, bottom, top, color))
        lows.append(bottom)
        highs.append(top)
    # the two totals are drawn as labelled reference lines, so the axis spans the
    # deltas only and the bars are readable (a full-height total bar would dwarf them)
    deltas = [(b, t) for (_, _, k, b, t, _) in bars if k == "delta"]
    ticks = _nice_ticks(min(b for b, _ in deltas), max(t for _, t in deltas))
    lo, hi = ticks[0], ticks[-1]
    sy = lambda v: mt + ph * (1 - (v - lo) / (hi - lo))  # noqa: E731
    n = len(bars)
    slot = pw / n
    bw = min(24, slot * 0.6)
    out = [f'<svg class="chart" viewBox="0 0 {width} {height}" role="img" aria-label="Bridge from budget EBITDA to actual EBITDA">']
    for t in ticks:
        out.append(f'<line x1="{ml}" x2="{ml + pw}" y1="{sy(t):.1f}" y2="{sy(t):.1f}" stroke="{LINE}" stroke-width="1"/>')
        out.append(f'<text x="{ml - 8}" y="{sy(t) + 4:.1f}" text-anchor="end" class="tick axis">{t / 1e6:.2f}M</text>')
    for i, (label, val, kind, bottom, top, color) in enumerate(bars):
        x = ml + slot * i + (slot - bw) / 2
        if kind == "total":
            yv = sy(val)
            out.append(f'<line x1="{x:.1f}" x2="{x + bw:.1f}" y1="{yv:.1f}" y2="{yv:.1f}" stroke="#171715" stroke-width="2"><title>{html.escape(label)}: {fx.musd(val, 2)}</title></line>')
            below = i == len(bars) - 1
            out.append(f'<text x="{x + bw / 2:.1f}" y="{yv + 14 if below else yv - 6:.1f}" text-anchor="middle" class="tick">{fx.musd(val, 2)}</text>')
        else:
            y, h = sy(top), max(1.0, sy(bottom) - sy(top))
            out.append(f'<rect x="{x:.1f}" y="{y:.1f}" width="{bw:.1f}" height="{h:.1f}" fill="{color}" rx="3"><title>{html.escape(label)}: {fx.signed_kusd(val)}</title></rect>')
            ty = y - 5 if val >= 0 else y + h + 12
            out.append(f'<text x="{x + bw / 2:.1f}" y="{ty:.1f}" text-anchor="middle" class="tick">{fx.signed_kusd(val)}</text>')
        # wrapped category label
        words = label.split(" ")
        lines_, cur = [], ""
        for w in words:
            if len(cur) + len(w) + 1 > 16 and cur:
                lines_.append(cur)
                cur = w
            else:
                cur = (cur + " " + w).strip()
        lines_.append(cur)
        out.append(f'<text transform="translate({x + bw / 2:.1f},{mt + ph + 10}) rotate(-38)" text-anchor="end" class="tick">{html.escape(label)}</text>')
    out.append("</svg>")
    return "".join(out)


def hbar_chart(rows: list, floor: float, floor_label: str, fmt, width=440, height=270, xmin=0.0, xmax=None) -> str:
    """rows: [(label, value, ok)]; blue passes, red fails, floor as a vertical line."""
    ml, mr, mt, mb = 200, 60, 10, 30
    pw, ph = width - ml - mr, height - mt - mb
    vals = [v for _, v, _ in rows]
    xmax = xmax if xmax is not None else max(vals + [floor]) * 1.1
    sx = lambda v: ml + pw * (v - xmin) / (xmax - xmin)  # noqa: E731
    slot = ph / len(rows)
    bh = min(22, slot * 0.6)
    out = [f'<svg class="chart" viewBox="0 0 {width} {height}" role="img" aria-label="{html.escape(floor_label)} by option">']
    ys = [mt + slot * i + (slot - bh) / 2 for i in range(len(rows))]
    # layer order: bars, then the floor line across them, then value labels with a
    # surface-coloured halo so the line never runs through a label
    for (label, v, ok), y in zip(rows, ys):
        parts = label.replace("Front-loaded plan with Insights contractors", "Front-loaded + contractors").split("; ")
        if len(parts) == 2:
            out.append(f'<text x="{ml - 8}" y="{y + bh / 2 - 2:.1f}" text-anchor="end" class="tick">{html.escape(parts[0])}</text>')
            out.append(f'<text x="{ml - 8}" y="{y + bh / 2 + 10:.1f}" text-anchor="end" class="tick">{html.escape(parts[1])}</text>')
        else:
            out.append(f'<text x="{ml - 8}" y="{y + bh / 2 + 4:.1f}" text-anchor="end" class="tick">{html.escape(label)}</text>')
        out.append(f'<rect x="{ml}" y="{y:.1f}" width="{max(1, sx(v) - ml):.1f}" height="{bh:.1f}" fill="{BLUE if ok else RED}" rx="3"><title>{html.escape(label)}: {fmt(v)}</title></rect>')
    out.append(f'<line x1="{sx(floor):.1f}" x2="{sx(floor):.1f}" y1="{mt}" y2="{mt + ph}" stroke="#171715" stroke-width="1.2"/>')
    out.append(f'<text x="{sx(floor) + 4:.1f}" y="{height - 8}" class="tick">{html.escape(floor_label)}</text>')
    for (label, v, ok), y in zip(rows, ys):
        out.append(f'<text x="{sx(v) + 6:.1f}" y="{y + bh / 2 + 4:.1f}" class="tick" paint-order="stroke" stroke="#ffffff" stroke-width="5" stroke-linejoin="round">{fmt(v)}</text>')
    out.append("</svg>")
    return "".join(out)


def table(headers: list, rows: list, cls: str = "tbl") -> str:
    h = "".join(f"<th>{html.escape(str(x))}</th>" for x in headers)
    # data-label carries the column header into each cell, so on phones every row
    # can be shown as a stacked block of label and value pairs instead of a wide table
    b = "".join("<tr>" + "".join(f'<td data-label="{html.escape(str(hd))}">{x if isinstance(x, str) and x.startswith("<") else html.escape(str(x))}</td>'
                                 for hd, x in zip(headers, r)) + "</tr>" for r in rows)
    return f'<div class="tblwrap"><table class="{cls}"><thead><tr>{h}</tr></thead><tbody>{b}</tbody></table></div>'


# ------------------------------------------------------------------ page --

def build() -> Path:
    F = fx.build()
    a = asm.load()
    SITE.mkdir(exist_ok=True)
    (SITE / "assets").mkdir(exist_ok=True)
    for src in ("northlight_planning_model.xlsx", "cfo_memo.pdf", "board_pack.pdf", "cfo_memo.md"):
        shutil.copy(OUT / src, SITE / "assets" / src)

    c = F["options"][F["chosen"]]
    front = F["options"]["front_commit"]
    hold = F["options"]["hold_commit"]
    od = F["options"][F["ondemand_twin"]]
    M = fx.musd
    P = fx.pct
    horizon_end = fx.month_name(F["horizon_end"])
    as_of = fx.month_name(F["as_of"])

    # charts
    months = F["chosen_base_series"]["months"]
    cash_chart = line_chart({sc.capitalize(): (F[f"chosen_{sc}_series"]["cash"], SCEN[sc]) for sc in ("upside", "base", "downside")},
                            months, "Closing cash, USD", lambda v: f"{v / 1e6:.0f}M", width=440, height=300, mr=110)
    arr_chart = line_chart({sc.capitalize(): (F[f"chosen_{sc}_series"]["arr"], SCEN[sc]) for sc in ("upside", "base", "downside")},
                           months, "Total ARR, USD", lambda v: f"{v / 1e6:.0f}M", width=440, height=300, mr=110)
    gm_chart = line_chart({"With commitment (base)": (F["chosen_base_series"]["gm"], BLUE),
                           "On demand (base)": ([g for g in _ondemand_gm()], ORANGE)},
                          months, "Gross margin", lambda v: f"{v * 100:.0f}%", y0_zero=False,
                          floor=F["gm_floor"], floor_label=f"floor {P(F['gm_floor'])}")
    mat = F["material_rows"]
    other = F["bridge_other"]
    steps = [("Budget EBITDA", F["ytd_budget_ebitda"], "total")] + \
            [(f"{r['line_label']}, {r['component']}", r["impact"], "delta") for r in mat] + \
            [("All other", other, "delta"), ("Actual EBITDA", F["ytd_actual_ebitda"], "total")]
    bridge_chart = waterfall(steps)
    opts = list(F["options"].keys())
    runway_chart = hbar_chart([(F["options"][o]["label"], F["options"][o]["downside_runway_min"], F["options"][o]["runway_ok"]) for o in opts],
                              F["min_runway"], f"floor {F['min_runway']:.0f} months", lambda v: f"{v:.0f}")
    gm_bar = hbar_chart([(F["options"][o]["label"], F["options"][o]["base_gm_min"] * 100, F["options"][o]["gm_ok"]) for o in opts],
                        F["gm_floor"] * 100, f"floor {P(F['gm_floor'])}", lambda v: f"{v:.1f}%", xmin=70, xmax=78)

    option_rows = []
    for o in opts:
        v = F["options"][o]
        verdict = "Recommended" if o == F["chosen"] else ("Passes" if v["feasible"] else
                  ("Fails runway" if not v["runway_ok"] else "Fails margin"))
        option_rows.append([v["label"], f"{v['plan_hires']}", M(v["base_arr_end"]), M(v["upside_arr_end"]), M(v["downside_arr_end"]),
                            f"{v['downside_runway_min']:.0f}", P(v["base_gm_min"], 1), verdict])
    scen_rows = [[sc.capitalize(), M(F[f"chosen_{sc}_arr_end"]), P(F[f"chosen_{sc}_arr_end"] / F["arr_now"] - 1),
                  M(F[f"chosen_{sc}_cash_min"]), fx.months_str(F[f"chosen_{sc}_runway_min"]), P(F[f"chosen_{sc}_gm_min"], 1),
                  fx.month_name(F[f"chosen_{sc}_breakeven_month"]) if F[f"chosen_{sc}_breakeven_month"] else "not within horizon"]
                 for sc in ("base", "upside", "downside")]
    bridge_rows = [[r["line_label"], r["component"], fx.signed_kusd(r["impact"])] for r in mat]
    bench = a.table[a.table["source_type"] == "benchmark"]
    assumption_rows = [[html.escape(r.name), f"{r.base:g}", f"{r.upside:g}", f"{r.downside:g}", r.unit, r.source_type] for r in a.table.reset_index().itertuples()]
    log_rows = [[r.version, r.date, r.assumption_id, r.scenario, r.old_value, r.new_value, r.reason] for r in asm.read_changelog().itertuples()]
    hire_rows = [[r["role"], r["location"], fx.month_name(r["start_month"]), r["count"], r["rationale"]] for r in F["hiring_rows"]]
    loaded = F["loaded_senior_eng"]
    sal = F["salary_senior_eng"]
    tax = F["employer_tax"]
    loc_rows = [[loc, f"USD {sal[loc]:,.0f}", P(tax[loc], 1), f"USD {loaded[loc]:,.0f}"] for loc in ("Montreal", "Paris", "Austin")]

    page = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Alan Vourc'h &middot; Driver-based planning for a SaaS scale-up</title>
<meta name="description" content="A portfolio project by Alan Vourc'h, FP&A: an 18-month driver-based plan for a SaaS scale-up that decides headcount, cloud and product investment under base, upside and downside scenarios, with an actual-versus-plan bridge, versioned assumptions and an auditable Excel export.">
<style>
  :root {{ --bg:#fcfcfb; --surface:#fff; --ink:#171715; --ink-2:#4f4e4a; --muted:#85837d; --line:#e6e5de;
          --accent:#2a78d6; --accent-ink:#1d5aa6; --accent-soft:#e9f2fc; --bad:#c23434; --warn-bg:#fdf6e7; --warn-line:#e8d9b0;
          --sys-bg:#f2f1ec; --sys-ink:#6b6a63; --card-shadow:0 1px 2px rgba(20,20,15,.04),0 8px 24px rgba(20,20,15,.05); }}
  * {{ box-sizing:border-box; margin:0; }}
  html {{ scroll-behavior:smooth; }}
  body {{ background:var(--bg); color:var(--ink); font:16px/1.6 "Segoe UI",system-ui,-apple-system,"Helvetica Neue",Arial,sans-serif; -webkit-font-smoothing:antialiased; }}
  .wrap {{ max-width:1000px; margin:0 auto; padding:0 24px; }}
  section {{ padding:60px 0; border-top:1px solid var(--line); }}
  h1 {{ font-size:clamp(30px,5vw,43px); line-height:1.14; letter-spacing:-.018em; }}
  h2 {{ font-size:clamp(21px,3vw,27px); line-height:1.2; letter-spacing:-.01em; }}
  h3 {{ font-size:16px; }}
  p {{ color:var(--ink-2); }}
  a {{ color:var(--accent-ink); }}
  .kicker {{ display:block; font-size:12.5px; font-weight:700; letter-spacing:.07em; color:var(--muted); text-transform:uppercase; margin-bottom:12px; }}
  .lead {{ font-size:17px; max-width:44em; }}
  .muted {{ color:var(--muted); font-size:14px; }}
  .hero {{ padding:78px 0 58px; }}
  .hero .eyebrow {{ display:inline-block; font-size:13px; color:var(--accent-ink); font-weight:600; background:var(--accent-soft); border-radius:99px; padding:5px 14px; margin-bottom:22px; }}
  .hero h1 {{ max-width:17em; }}
  .hero p {{ margin-top:18px; font-size:18px; max-width:42em; }}
  .cta-row {{ margin-top:28px; display:flex; gap:12px; flex-wrap:wrap; align-items:center; }}
  .btn {{ display:inline-block; padding:11px 20px; border-radius:8px; font-weight:600; font-size:15px; text-decoration:none; border:1px solid var(--line); color:var(--ink); background:var(--surface); }}
  .btn.primary {{ background:var(--accent); border-color:var(--accent); color:#fff; }}
  .btn.primary:hover {{ background:var(--accent-ink); }}
  .btn:hover {{ border-color:var(--muted); }}
  .stats {{ display:grid; grid-template-columns:repeat(4,minmax(0,1fr)); gap:16px; margin-top:26px; }}
  .stat {{ border-left:3px solid var(--accent); padding:4px 0 4px 14px; }}
  .stat b {{ display:block; font-size:22px; color:var(--ink); line-height:1.1; }}
  .stat span {{ font-size:13.5px; color:var(--muted); }}
  .card {{ background:var(--surface); border:1px solid var(--line); border-radius:14px; padding:22px; box-shadow:var(--card-shadow); }}
  .two {{ display:grid; grid-template-columns:minmax(0,1fr) minmax(0,1fr); gap:22px; margin-top:24px; align-items:start; }}
  .tiles {{ display:grid; grid-template-columns:repeat(3,minmax(0,1fr)); gap:14px; margin-top:24px; }}
  .tile {{ border:1px solid var(--line); background:var(--surface); border-radius:12px; padding:20px; }}
  .tile h3 {{ margin-bottom:5px; }}
  .tile p {{ font-size:14px; color:var(--muted); }}
  .tile.pick {{ border-color:var(--accent); background:var(--accent-soft); }}
  .tile .tag {{ display:inline-block; font-size:11px; font-weight:700; letter-spacing:.06em; text-transform:uppercase; padding:2px 7px; border-radius:5px; background:var(--sys-bg); color:var(--sys-ink); margin-bottom:8px; }}
  .tile.pick .tag {{ background:var(--accent); color:#fff; }}
  .tile.fail .tag {{ background:#fbeaea; color:#a12626; }}
  .proof {{ margin-top:16px; background:var(--warn-bg); border:1px solid var(--warn-line); border-radius:12px; padding:18px 20px; }}
  .proof b {{ color:var(--ink); }}
  .flow {{ display:grid; grid-template-columns:repeat(5,minmax(0,1fr)); gap:10px; margin-top:26px; }}
  /* grid children may shrink below their content width, so wide tables and code scroll inside their own box instead of widening the page on phones */
  .stats > *, .two > *, .tiles > *, .flow > * {{ min-width:0; }}
  .node {{ position:relative; border-radius:12px; padding:16px 14px; border:1px solid var(--line); background:var(--surface); }}
  .node .role {{ font-size:11px; font-weight:700; letter-spacing:.06em; text-transform:uppercase; margin-bottom:8px; display:inline-block; padding:2px 7px; border-radius:5px; background:var(--sys-bg); color:var(--sys-ink); }}
  .node.you {{ border-color:var(--accent); background:var(--accent-soft); }}
  .node.you .role {{ background:var(--accent); color:#fff; }}
  .node h3 {{ font-size:14.5px; margin-bottom:4px; }}
  .node p {{ font-size:12.5px; line-height:1.45; }}
  .node::after {{ content:"\\2192"; position:absolute; right:-11px; top:50%; transform:translateY(-50%); color:var(--muted); font-size:16px; z-index:2; }}
  .node:last-child::after {{ content:none; }}
  .chart {{ width:100%; height:auto; display:block; margin-top:8px; }}
  .chart .tick {{ font:11.5px "Segoe UI",system-ui,sans-serif; fill:var(--muted); }}
  .chart .endlabel {{ font:12px "Segoe UI",system-ui,sans-serif; fill:var(--ink-2); font-weight:600; }}
  .legend {{ display:flex; gap:16px; flex-wrap:wrap; font-size:13px; color:var(--ink-2); margin-top:14px; }}
  .legend i {{ display:inline-block; width:11px; height:11px; border-radius:3px; margin-right:6px; vertical-align:-1px; }}
  .tblwrap {{ overflow-x:auto; margin-top:14px; border:1px solid var(--line); border-radius:8px; background:var(--surface); }}
  table.tbl {{ border-collapse:collapse; width:100%; font-size:13.5px; }}
  .tbl th, .tbl td {{ padding:8px 10px; border-bottom:1px solid var(--line); text-align:left; vertical-align:top; }}
  .tbl th {{ color:var(--muted); font-weight:600; font-size:12.5px; white-space:nowrap; }}
  .tbl tr:last-child td {{ border-bottom:none; }}
  .tbl td.num, .tbl th.num {{ text-align:right; font-variant-numeric:tabular-nums; }}
  details {{ margin-top:16px; }}
  details > summary {{ cursor:pointer; font-size:14px; color:var(--accent-ink); font-weight:600; }}
  .caption {{ margin-top:10px; font-size:14px; color:var(--muted); }}
  ul.plain {{ margin:12px 0 0 20px; color:var(--ink-2); }}
  ul.plain li {{ margin-bottom:8px; }}
  code {{ font:13px Consolas,"Cascadia Mono",Menlo,monospace; background:var(--sys-bg); padding:1px 5px; border-radius:4px; }}
  pre {{ font:12.5px/1.6 Consolas,"Cascadia Mono",Menlo,monospace; background:#1b1b18; color:#d9d7cf; padding:18px 20px; border-radius:12px; overflow-x:auto; margin-top:14px; }}
  .about b {{ font-size:18px; }}
  .about .title {{ color:var(--muted); font-size:14px; display:block; }}
  .contact {{ margin-top:18px; display:flex; gap:12px; flex-wrap:wrap; }}
  footer {{ border-top:1px solid var(--line); padding:30px 0 54px; font-size:13px; color:var(--muted); }}
  @media (max-width:820px) {{ .flow {{ grid-template-columns:minmax(0,1fr); }} .node::after {{ content:"\\2193"; right:50%; top:auto; bottom:-15px; transform:translateX(50%); }} .two {{ grid-template-columns:minmax(0,1fr); }} }}
  @media (max-width:640px) {{ .stats {{ grid-template-columns:repeat(2,minmax(0,1fr)); }} .tiles {{ grid-template-columns:minmax(0,1fr); }}
    .card {{ padding:18px 16px; }}
    .tblwrap {{ overflow-x:visible; }}
    table.tbl, .tbl tbody, .tbl tr, .tbl td {{ display:block; width:100%; }}
    .tbl thead {{ display:none; }}
    .tbl tr {{ padding:10px 12px; border-bottom:1px solid var(--line); }}
    .tbl tr:last-child {{ border-bottom:none; }}
    .tbl td {{ display:grid; grid-template-columns:minmax(0,42%) minmax(0,1fr); gap:10px; padding:3px 0; border-bottom:none; font-size:13px; overflow-wrap:anywhere; }}
    .tbl td::before {{ content:attr(data-label); color:var(--muted); font-size:12px; font-weight:600; }}
    .tbl td:first-child {{ font-weight:700; color:var(--ink); }}
    pre {{ white-space:pre-wrap; overflow-wrap:anywhere; padding:14px 14px; }} }}
</style>
</head>
<body>

<header class="hero">
  <div class="wrap">
    <span class="eyebrow">Alan Vourc'h &middot; FP&amp;A, planning and scenarios</span>
    <h1>Hire in phases, commit the cloud, and hold the bigger plan until retention proves out.</h1>
    <p>That is what this planning model tells the CFO and the head of engineering of a
    {M(F['arr_now'], 0)} ARR software company to do over the next 18 months. It reaches
    {M(F['chosen_base_arr_end'], 0)} of ARR by {horizon_end} in the base case, keeps at least
    {F['chosen_downside_runway_min']:.0f} months of cash runway even in the downside, and holds
    gross margin above {P(F['gm_floor'])}. The front-loaded alternative buys
    {M(F['front_extra_arr_base'])} more ARR and breaks the runway guardrail.</p>
    <div class="cta-row">
      <a class="btn primary" href="#decision">The decision in 90 seconds</a>
      <a class="btn" href="#numbers">Check the numbers</a>
      <a class="btn" href="assets/northlight_planning_model.xlsx">Download the Excel model</a>
    </div>
  </div>
</header>

<section id="decision">
  <div class="wrap">
    <span class="kicker">1 &middot; The decision</span>
    <h2>One question, three options, two guardrails</h2>
    <p class="lead" style="margin-top:10px;">Northlight is a fictional but realistic Series C software company:
    two products, {F['fte_now']:.0f} people in Montréal, Paris and Austin, growing {P(F['arr_growth_yoy'])} a year and
    burning {fx.kusd(F['burn_now'])} a month. Cloud hosting has climbed from {P(F['cloud_share_feb26'], 1)} of revenue in February to {P(F['cloud_share_now'], 1)} in August. The question every scale-up CFO gets asked: how much to hire,
    where, and what to commit on cloud, without running out of cash or margin.</p>
    <div class="stats">
      <div class="stat"><b>{M(F['arr_now'])}</b><span>ARR at end {as_of}</span></div>
      <div class="stat"><b>{M(F['cash_now'])}</b><span>cash, {fx.months_str(F['runway_now'])} of runway</span></div>
      <div class="stat"><b>{P(F['gm_now'], 1)}</b><span>gross margin, {fx.pts(F['gm_gap_vs_budget'])} below budget</span></div>
      <div class="stat"><b>{P(F['rd_share_now'])}</b><span>of revenue spent on R&amp;D</span></div>
    </div>
    <div class="tiles">
      <div class="tile"><span class="tag">Option</span><h3>Hold hiring</h3><p>Backfills only. Ends with {M(hold['base_cash_end'])} of cash and
        {M(hold['base_arr_end'])} of ARR in the base case, {M(F['hold_arr_gap_base'])} below the recommended plan.</p></div>
      <div class="tile pick"><span class="tag">Recommended</span><h3>Phased plan</h3><p>{F['hires_total']} hires from {fx.month_name(F['first_hire_month'])} to
        {fx.month_name(F['last_hire_month'])}, {F['hires_rd']} of them in R&amp;D. {M(c['base_arr_end'])} of ARR in the base case; runway never below
        {c['downside_runway_min']:.0f} months in the downside.</p></div>
      <div class="tile fail"><span class="tag">Fails a guardrail</span><h3>Front-loaded plan</h3><p>{front['plan_hires']} hires by early 2027 plus product contractors.
        Only {M(F['front_extra_arr_base'])} more ARR than the phased plan, and downside runway falls to {front['downside_runway_min']:.1f} months, {F['front_runway_shortfall']:.1f} short of the floor.</p></div>
    </div>
    <div class="proof">
      <p><b>On cloud, the model is unambiguous.</b> Running on demand fails the gross margin floor
      (the base case bottoms at {P(od['base_gm_min'], 1)}). A one-year commitment of {F['commit_units']:,.0f} compute units a month
      at a {P(F['commit_discount'])} discount saves {M(F['commit_saving_base_18m'])} over 18 months and lifts the minimum margin by
      {fx.pts(F['commit_gm_gain_base'])}. The cost of that insurance in the downside: {fx.kusd(F['chosen_downside_stranded'])} of committed units nobody uses.</p>
    </div>
    <p style="margin-top:22px;"><b>What a company does differently because of this.</b></p>
    <ul class="plain">
      <li>Engineering opens {F['hires_rd']} requisitions in a fixed order over eight months instead of {F['front_hires_rd']} inside a quarter, and the Insights contractor push waits for the Q1 2027 retention review.</li>
      <li>The cloud commitment is signed before the renewal window, sized at {P(F['commit_coverage'])} of expected usage so the downside does not strand much.</li>
      <li>Two guardrails become standing policy: {F['min_runway']:.0f} months of downside runway and a {P(F['gm_floor'])} gross margin floor, checked every month against the same drivers.</li>
    </ul>
    <p class="caption">Read the <a href="assets/cfo_memo.pdf">one-page CFO memo</a> and the <a href="assets/board_pack.pdf">five-slide board pack</a>, both generated from the model.</p>
  </div>
</section>

<section id="numbers">
  <div class="wrap">
    <span class="kicker">2 &middot; The numbers</span>
    <h2>The recommended plan under three scenarios</h2>
    <p class="lead" style="margin-top:10px;">Same drivers, three settings. Base uses {P(F['nrr_base'])} net revenue retention and
    {F['lpa_base']:.2f} new customers per ramped account executive a month; the downside {P(F['nrr_downside'])} and {F['lpa_downside']:.2f};
    the upside {P(F['nrr_upside'])} and {F['lpa_upside']:.2f}.</p>
    <div class="two">
      <div class="card"><h3>Closing cash</h3>{cash_chart}</div>
      <div class="card"><h3>Total ARR</h3>{arr_chart}</div>
    </div>
    {table(["Scenario", "ARR at " + horizon_end, "Growth over 18 months", "Cash low point", "Minimum runway", "Minimum gross margin", "EBITDA break-even"], scen_rows)}
    <h3 style="margin-top:34px;">Every option against both guardrails</h3>
    <div class="two">
      <div class="card"><h3>Minimum downside runway, months</h3>{runway_chart}</div>
      <div class="card"><h3>Minimum base gross margin</h3>{gm_bar}</div>
    </div>
    {table(["Option", "Hires", "ARR base", "ARR upside", "ARR downside", "Downside runway (months)", "Base gross margin min", "Verdict"], option_rows)}
    <p class="caption">Objective: the highest base-case ARR at {horizon_end} among options that pass both guardrails. {F['n_options']} options, {F['n_runs']} runs of the same engine.</p>
    <div class="card" style="margin-top:22px;"><h3>Gross margin with and without the cloud commitment, base case</h3>{gm_chart}</div>
  </div>
</section>

<section id="how">
  <div class="wrap">
    <span class="kicker">3 &middot; How the numbers are built</span>
    <h2>Drivers in, cash out, nothing typed in between</h2>
    <div class="flow">
      <div class="node"><span class="role">Inputs</span><h3>{F['n_assumptions']} drivers</h3><p>{F['n_benchmark']} anchored on published SaaS benchmarks, {F['n_judgment']} labelled as judgment calls, each with its source.</p></div>
      <div class="node"><span class="role">Engine</span><h3>Workforce</h3><p>Every seat costed by role and location: salary, bonus, employer taxes, benefits, recruiting, merit, ramp.</p></div>
      <div class="node"><span class="role">Engine</span><h3>Revenue and cloud</h3><p>New customers from ramped sales capacity; retention, price and attach; compute units per customer.</p></div>
      <div class="node"><span class="role">Engine</span><h3>P&amp;L and cash</h3><p>By function and by product to gross profit; receivables, deferred revenue, runway.</p></div>
      <div class="node you"><span class="role">Me</span><h3>Guardrails and memo</h3><p>The options, the guardrails, the objective and the recommendation are finance decisions, written as rules the model applies.</p></div>
    </div>
    <div class="two">
      <div class="card">
        <h3>A hire flows through to cash</h3>
        <p class="caption">One senior software engineer, first-year cost, from the salary and location tables. Employer tax rates are derived from the 2026 Québec, French and United States rate tables.</p>
        {table(["Location", "Salary", "Employer tax", "Loaded cost, year one"], loc_rows)}
        <p class="caption">Loaded cost = salary plus {P(a.value('bonus_pct_non_sales'))} bonus, employer tax on both, and benefits. Recruiting adds {P(a.value('recruiting_cost_pct_salary'))} of salary once; equipment adds USD {a.value('capex_per_new_hire_usd'):,.0f} to cash. A start month later means exactly one month less of all of it, which the tests check.</p>
      </div>
      <div class="card">
        <h3>Revenue is capacity, not a growth rate</h3>
        <p class="caption">New customers a month = ramped account executives &times; customers per ramped AE &times; seasonality. An AE hired in January sells nothing that month, a quarter of quota in February, and full quota from May. Churn and expansion come from gross and net retention; the January price increase is its own line; Insights revenue is customers &times; attach rate &times; usage.</p>
        <p class="caption">Cloud cost = compute units &times; unit price, with committed units at a discount and overage at list. Customer success hires are added automatically when coverage drops below {F['customers_per_csm']:.0f} customers per manager.</p>
      </div>
    </div>
    <details>
      <summary>The full driver table, all three scenarios &rarr;</summary>
      {table(["Driver", "Base", "Upside", "Downside", "Unit", "Source"], assumption_rows)}
    </details>
    <details>
      <summary>The recommended hiring plan, seat by seat &rarr;</summary>
      {table(["Role", "Location", "Start", "Count", "Why"], hire_rows)}
    </details>
  </div>
</section>

<section id="bridge">
  <div class="wrap">
    <span class="kicker">4 &middot; 2026 so far</span>
    <h2>Actual against budget, driver by driver</h2>
    <p class="lead" style="margin-top:10px;">The FY2026 budget was locked in December 2025. {fx.month_name(F['ytd_first'])} to {fx.month_name(F['ytd_last'])},
    EBITDA is {fx.signed_kusd(F['ytd_ebitda_variance'])} against it. Every P&amp;L line is split into volume and price, headcount and rate,
    usage and unit cost; the {F['n_bridge_components']} components add up to that figure to the cent, and {F['n_material']} of them pass the materiality test
    (over USD {F['materiality_abs'] / 1e3:.0f}k and {P(F['materiality_pct'])} of the line, or over USD {F['materiality_override'] / 1e3:.0f}k).</p>
    <div class="card" style="margin-top:22px;">{bridge_chart}</div>
    <p class="caption">Budget and actual EBITDA are the two black levels; each bar is one driver component, floating from the previous level.</p>
    {table(["Line", "Component", "Effect on EBITDA"], bridge_rows)}
    <p class="caption">Blue is favorable, red unfavorable. The late engineering hires flatter the year; the Insights usage step-up is the number that changed the plan, and it is why the cloud commitment and the gross margin floor are in the recommendation.</p>
  </div>
</section>

<section id="versions">
  <div class="wrap">
    <span class="kicker">5 &middot; Assumptions have a history</span>
    <h2>What changed since the budget, when, and why</h2>
    <p class="lead" style="margin-top:10px;">Assumption set v{F['version']}. The budget snapshot plus this log reproduces today's file exactly, and a test proves it on every run.</p>
    {table(["Version", "Date", "Driver", "Scenario", "From", "To", "Reason"], log_rows)}
  </div>
</section>

<section id="verify">
  <div class="wrap">
    <span class="kicker">6 &middot; Verify it</span>
    <h2>Run it, read the tests, open the workbook</h2>
    <div class="two">
      <div>
        <p>Python 3.12, pandas, numpy, openpyxl, matplotlib. No language model anywhere, no dashboard tool, no build step.</p>
        <pre>git clone https://github.com/alanvourch/fpa-planning-model.git
cd fpa-planning-model
python -m venv .venv
.venv/Scripts/pip install -r requirements.txt
.venv/Scripts/python.exe run_model.py
.venv/Scripts/python.exe -m pytest -q</pre>
        <p class="caption">The run regenerates the dataset, the budget, the bridge, the {F['n_runs']} scenario runs, the Excel workbook, the memo, the board pack and this page. Two runs give identical files.</p>
      </div>
      <div>
        <h3>What the tests hold</h3>
        <ul class="plain">
          <li><b>Reconciliation.</b> ARR roll-forward, P&amp;L subtotals, product P&amp;L, payroll to the workforce table, cloud rule, and cash roll-forward, for every one of the {F['n_runs']} runs plus actuals and budget.</li>
          <li><b>Workforce.</b> A hire costs exactly its loaded salary from its start month, merit applies each January, an end date stops cost, an AE adds customers only after ramp, and one extra engineer moves EBITDA and cash by exactly the expected amount.</li>
          <li><b>Bridge.</b> Components tie to each line and to EBITDA every month, and recover the six planted deviations.</li>
          <li><b>Excel.</b> Values match the Python output, and Excel itself recalculates every formula to the same figures.</li>
          <li><b>Documents.</b> Every number in the memo and on this page traces to a model output.</li>
          <li><b>Adversarial.</b> See the repository's decisions file for what the adversarial test caught.</li>
        </ul>
      </div>
    </div>
    <div class="card" style="margin-top:22px;">
      <h3>The Excel export</h3>
      <p class="caption"><a href="assets/northlight_planning_model.xlsx">northlight_planning_model.xlsx</a>: assumptions with sources, the change log, actuals, budget, the bridge, the recommended plan's three scenarios with the ARR roll-forward, cloud and cash, the workforce by function and location, and a Checks sheet where every subtotal is an Excel formula recomputed against the model value. Yellow cells are model values, blue cells are formulas.</p>
    </div>
    <h3 style="margin-top:30px;">What the model deliberately does not do</h3>
    <ul class="plain">
      <li>It does not model interest, income tax, depreciation, capitalized development or foreign exchange. EBITDA is the operating line and cash follows it.</li>
      <li>The actuals are synthetic and generated by the same engine, so the bridge reconciles exactly by construction. Real ledgers need a reconciliation tolerance and an unallocated line.</li>
      <li>Plan headcount carries attrition as an expected vacancy allowance, not as simulated leavers.</li>
      <li>Marketing spend scales with the new-customer target; it does not drive it.</li>
      <li>{F['n_judgment']} of the {F['n_assumptions']} drivers are judgment calls, labelled as such in the driver table above. The benchmark-anchored ones cite the survey they come from.</li>
    </ul>
  </div>
</section>

<section id="about">
  <div class="wrap">
    <span class="kicker">7 &middot; About</span>
    <div class="about">
      <b>Alan Vourc'h</b>
      <span class="title">FP&amp;A &middot; finance and data, together</span>
      <p style="margin-top:10px;max-width:46em;">Northlight is fictional, but the question is not. I have run budgets, forecasts and
      headcount plans for a EUR100M business and consolidated costs across twelve business units at a global bank. This model is the
      forward-looking half of that work: the machinery a finance team needs before the debate about the numbers can even start.
      A companion project, <a href="https://alanvourch.com/fpa-project/">the automated monthly close</a>, covers the backward-looking half.</p>
      <div class="contact">
        <a class="btn primary" href="https://www.linkedin.com/in/alan-vourch/">LinkedIn</a>
        <a class="btn" href="mailto:alan.vourch@gmail.com">alan.vourch@gmail.com</a>
      </div>
    </div>
  </div>
</section>

<footer>
  <div class="wrap">
    <p>All data on this page is synthetic and generated from a fixed seed. Nothing real except the method.
    Code, tests and the decisions log are in the <a href="https://github.com/alanvourch/fpa-planning-model">GitHub repository</a>.</p>
  </div>
</footer>

</body>
</html>
"""
    path = SITE / "index.html"
    path.write_text(page, encoding="utf-8")
    return path


def _ondemand_gm():
    import pandas as pd
    F = fx.build()
    p = pd.read_csv(OUT / "scenarios" / f"{F['ondemand_twin']}__base_pnl.csv", index_col="month")
    return [float(x) for x in p["gross_margin"]]


if __name__ == "__main__":
    print(f"wrote {build()}")
