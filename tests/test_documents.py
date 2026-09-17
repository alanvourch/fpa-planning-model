"""Every number displayed in the memo and on the web page traces to a model
output. The allowed set is built from model/facts.py (the only source the
renderers may read), formatted every way the renderers format numbers, plus
the assumption, hiring-plan and change-log tables the page prints verbatim.
A number on the page that is not in that set fails the test with its context.

Also: the memo PDF is one page, the board pack five, and the page is a single
self-contained HTML file (no external scripts, stylesheets or images).
"""

import re
from html.parser import HTMLParser
from pathlib import Path

import pandas as pd
import pytest

from model import assumptions as asm, facts as fx

ROOT = Path(__file__).resolve().parents[1]
SITE = ROOT / "site" / "index.html"
MEMO = ROOT / "output" / "cfo_memo.md"

# numbers that are structure, not model output: section numbers, the years in
# month names, the Python version in the run instructions, the 90-second promise
STRUCTURAL = {"1", "2", "3", "4", "5", "6", "7", "12", "18", "90", "100", "2024", "2025", "2026", "2027", "2028", "3.12", "0"}


def _formats(v: float) -> set:
    out = set()
    for f in (f"{v:.0f}", f"{v:.1f}", f"{v:.2f}", f"{v:g}", f"{v:,.0f}", f"{v / 1e6:.0f}", f"{v / 1e6:.1f}",
              f"{v / 1e6:.2f}", f"{v / 1e3:.0f}", f"{v * 100:.0f}", f"{v * 100:.1f}", f"{v * 100:.2f}"):
        out.add(f.replace(",", ""))
        out.add(f.replace(",", "").lstrip("-"))
    return out


def _walk(x, acc: set):
    if isinstance(x, bool):
        return
    if isinstance(x, (int, float)):
        if x == float("inf"):
            return
        acc |= _formats(float(x))
    elif isinstance(x, str):
        for tok in re.findall(r"\d[\d,]*\.?\d*", x):
            acc.add(tok.replace(",", ""))
    elif isinstance(x, dict):
        for v in x.values():
            _walk(v, acc)
    elif isinstance(x, (list, tuple)):
        for v in x:
            _walk(v, acc)


@pytest.fixture(scope="module")
def allowed():
    F = fx.build()
    acc = set()
    _walk(F, acc)
    a = asm.load()
    for df in (a.table.reset_index(), a.hiring_plans, asm.read_changelog(), a.locations.reset_index(), a.salaries.reset_index()):
        for col in df.columns:
            for v in df[col]:
                _walk(v.item() if hasattr(v, "item") else v, acc)
    # derived display values used on the page
    for loc in a.locations.index:
        _walk(a.value("bonus_pct_non_sales"), acc)
        _walk(a.value("recruiting_cost_pct_salary"), acc)
        _walk(a.value("capex_per_new_hire_usd"), acc)
    for sc in asm.SCENARIOS:
        _walk(F[f"chosen_{sc}_arr_end"] / F["arr_now"] - 1.0, acc)
    _walk(F["materiality_abs"] / 1e3, acc)
    _walk(F["materiality_override"] / 1e3, acc)
    return acc | STRUCTURAL


class _Text(HTMLParser):
    def __init__(self):
        super().__init__()
        self.skip = 0
        self.chunks = []

    def handle_starttag(self, tag, attrs):
        if tag in ("style", "script"):
            self.skip += 1
        # axis tick labels are scaffolding derived from the data range, not model figures
        if tag == "text" and any(k == "class" and "axis" in (v or "") for k, v in attrs):
            self.skip += 1
            self._axis_depth = getattr(self, "_axis_depth", 0) + 1

    def handle_endtag(self, tag):
        if tag in ("style", "script"):
            self.skip -= 1
        if tag == "text" and getattr(self, "_axis_depth", 0) > 0:
            self.skip -= 1
            self._axis_depth -= 1

    def handle_data(self, data):
        if not self.skip and data.strip():
            self.chunks.append(data.strip())


def _numbers_with_context(text_chunks):
    out = []
    for chunk in text_chunks:
        for m in re.finditer(r"\d[\d,]*\.?\d*", chunk):
            tok = m.group(0).replace(",", "").rstrip(".")
            out.append((tok, chunk[max(0, m.start() - 40):m.end() + 40]))
    return out


def _month_tokens(tok: str) -> bool:
    return bool(re.fullmatch(r"20\d\d-\d\d", tok)) or bool(re.fullmatch(r"20\d\d-\d\d-\d\d", tok))


def test_every_number_on_the_page_traces_to_the_model(allowed):
    assert SITE.exists(), "run run_model.py first"
    p = _Text()
    p.feed(SITE.read_text(encoding="utf-8"))
    unknown = []
    for tok, ctx in _numbers_with_context(p.chunks):
        if tok in allowed or _month_tokens(tok):
            continue
        unknown.append((tok, ctx))
    assert not unknown, "numbers not traceable to a model output:\n" + "\n".join(f"  {t!r} in {c!r}" for t, c in unknown[:40])


def test_every_number_in_the_memo_traces_to_the_model(allowed):
    assert MEMO.exists()
    text = MEMO.read_text(encoding="utf-8")
    unknown = []
    for tok, ctx in _numbers_with_context([line for line in text.splitlines() if line.strip()]):
        if tok in allowed or _month_tokens(tok):
            continue
        unknown.append((tok, ctx))
    assert not unknown, "numbers not traceable to a model output:\n" + "\n".join(f"  {t!r} in {c!r}" for t, c in unknown[:40])


def test_page_is_self_contained_and_light():
    html = SITE.read_text(encoding="utf-8")
    assert "<script" not in html
    assert 'rel="stylesheet"' not in html
    assert "<img" not in html
    assert "<svg" in html
    for word in ("leverage", "streamline", "seamless", "robust", "unlock", "empower", "game-changer"):
        assert word not in html.lower(), word
    assert "—" not in html  # no em dashes anywhere Alan publishes


def test_memo_has_no_em_dash_or_hype():
    text = MEMO.read_text(encoding="utf-8").lower()
    assert "—" not in text
    for word in ("leverage", "streamline", "seamless", "robust", "unlock", "empower", "game-changer"):
        assert word not in text, word
    for heading in ("## Decision", "## Why this option", "## Scenarios", "## Risks", "## Asks"):
        assert heading in MEMO.read_text(encoding="utf-8")


def test_pdf_page_counts():
    def count(path):
        data = path.read_bytes()
        return len(re.findall(rb"/Type\s*/Page[^s]", data))
    assert count(ROOT / "output" / "cfo_memo.pdf") == 1
    assert count(ROOT / "output" / "board_pack.pdf") == 5


def test_site_assets_copied():
    for name in ("northlight_planning_model.xlsx", "cfo_memo.pdf", "board_pack.pdf"):
        assert (ROOT / "site" / "assets" / name).exists()
