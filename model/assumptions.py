"""Assumption registry: one CSV per concern, one value per scenario, versioned.

Files (all under assumptions/):
  assumptions.csv   every numeric driver, with base/upside/downside columns and a
                    source label (benchmark, derived or judgment)
  locations.csv     employer tax, benefits and rent per location
  salary_table.csv  annual salary in USD by role and location, function mapping
  seasonality.csv   monthly new-logo index
  hiring_plans.csv  candidate hiring plans (one row per role/location/start)
  options.csv       the allocation options the decision engine evaluates
  changelog.csv     every change to assumptions.csv since the FY2026 budget was
                    locked: version, date, id, scenario, old, new, who, why
  VERSION           current version string
  snapshots/        frozen copies of assumptions.csv at a given version

Nothing in this module computes finance. It only loads, versions and
overrides values so every downstream number can be traced to a row here.
"""

from __future__ import annotations

import copy
import datetime as dt
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
ADIR = ROOT / "assumptions"
SCENARIOS = ("base", "upside", "downside")
CHANGELOG_COLUMNS = [
    "version", "date", "assumption_id", "scenario", "old_value", "new_value",
    "changed_by", "reason",
]


@dataclass
class Assumptions:
    version: str
    table: pd.DataFrame        # index: id; columns include base/upside/downside
    locations: pd.DataFrame    # index: location
    salaries: pd.DataFrame     # index: role; columns: function, cost_bucket, sales_role, <locations>
    seasonality: dict          # month number -> factor
    hiring_plans: pd.DataFrame
    options: pd.DataFrame      # index: option_id

    def value(self, assumption_id: str, scenario: str = "base") -> float:
        if scenario not in SCENARIOS:
            raise KeyError(f"unknown scenario {scenario!r}")
        if assumption_id not in self.table.index:
            raise KeyError(f"unknown assumption {assumption_id!r}")
        return float(self.table.at[assumption_id, scenario])

    def scenario_params(self, scenario: str) -> dict:
        return {aid: self.value(aid, scenario) for aid in self.table.index}

    def with_override(self, assumption_id: str, new_value: float,
                      scenario: str = "all") -> "Assumptions":
        """Return a copy with one value changed (in memory only)."""
        other = copy.deepcopy(self)
        cols = list(SCENARIOS) if scenario == "all" else [scenario]
        for c in cols:
            other.table.at[assumption_id, c] = float(new_value)
        return other

    def salary(self, role: str, location: str) -> float:
        return float(self.salaries.at[role, location])

    def location_param(self, location: str, name: str) -> float:
        return float(self.locations.at[location, name])


def _read_table(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path)
    df = df.set_index("id")
    for c in SCENARIOS:
        df[c] = df[c].astype(float)
    return df


def load(table_path: Path | None = None, version: str | None = None) -> Assumptions:
    table_path = table_path or ADIR / "assumptions.csv"
    version = version or (ADIR / "VERSION").read_text().strip()
    salaries = pd.read_csv(ADIR / "salary_table.csv").set_index("role")
    salaries["sales_role"] = salaries["sales_role"].astype(int).astype(bool)
    seasonality = pd.read_csv(ADIR / "seasonality.csv")
    return Assumptions(
        version=version,
        table=_read_table(table_path),
        locations=pd.read_csv(ADIR / "locations.csv").set_index("location"),
        salaries=salaries,
        seasonality={int(r.month): float(r.new_logo_factor) for r in seasonality.itertuples()},
        hiring_plans=pd.read_csv(ADIR / "hiring_plans.csv"),
        options=pd.read_csv(ADIR / "options.csv").set_index("option_id"),
    )


def load_snapshot(version: str) -> Assumptions:
    return load(ADIR / "snapshots" / f"assumptions_v{version}.csv", version=version)


def read_changelog() -> pd.DataFrame:
    path = ADIR / "changelog.csv"
    if not path.exists():
        return pd.DataFrame(columns=CHANGELOG_COLUMNS)
    return pd.read_csv(path, dtype=str)


def apply_changelog(table: pd.DataFrame, changelog: pd.DataFrame,
                    up_to_version: str | None = None) -> pd.DataFrame:
    """Replay changelog rows onto a snapshot table. Used by the tests to prove
    that snapshot + log == current file, so the log is complete."""
    out = table.copy()
    for row in changelog.itertuples():
        if up_to_version is not None and _vkey(row.version) > _vkey(up_to_version):
            continue
        cols = list(SCENARIOS) if row.scenario == "all" else [row.scenario]
        for c in cols:
            current = float(out.at[row.assumption_id, c])
            if abs(current - float(row.old_value)) > 1e-12:
                raise ValueError(
                    f"changelog {row.version} {row.assumption_id}/{c}: expected old value "
                    f"{row.old_value}, found {current}")
            out.at[row.assumption_id, c] = float(row.new_value)
    return out


def record_change(assumption_id: str, scenario: str, new_value: float, reason: str,
                  changed_by: str, version: str, date: str | None = None) -> None:
    """Change one assumption on disk and append the change to the log.

    This is the only sanctioned way to edit assumptions.csv values."""
    if scenario not in SCENARIOS and scenario != "all":
        raise KeyError(f"unknown scenario {scenario!r}")
    table = _read_table(ADIR / "assumptions.csv")
    raw = pd.read_csv(ADIR / "assumptions.csv", dtype=str).set_index("id")
    cols = list(SCENARIOS) if scenario == "all" else [scenario]
    old_values = {c: float(table.at[assumption_id, c]) for c in cols}
    if scenario == "all" and len(set(old_values.values())) != 1:
        raise ValueError("scenario='all' requires identical current values; change each scenario")
    for c in cols:
        raw.at[assumption_id, c] = _fmt(new_value)
    raw.reset_index().to_csv(ADIR / "assumptions.csv", index=False)
    log = read_changelog()
    entry = pd.DataFrame([{
        "version": version,
        "date": date or dt.date.today().isoformat(),
        "assumption_id": assumption_id,
        "scenario": scenario,
        "old_value": _fmt(old_values[cols[0]]),
        "new_value": _fmt(new_value),
        "changed_by": changed_by,
        "reason": reason,
    }])
    pd.concat([log, entry], ignore_index=True).to_csv(ADIR / "changelog.csv", index=False)
    (ADIR / "VERSION").write_text(version + "\n")


def _fmt(v: float) -> str:
    s = f"{float(v):.6f}".rstrip("0").rstrip(".")
    return s if s else "0"


def _vkey(v: str) -> tuple:
    return tuple(int(p) for p in str(v).split("."))
