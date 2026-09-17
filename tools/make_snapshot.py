"""Rebuild assumptions/snapshots/assumptions_v1.0.csv by reversing the change
log from the current file. Run once when the log is edited by hand; the test
suite then checks that snapshot + log == current file."""

import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from model import assumptions as asm  # noqa: E402


def main() -> None:
    raw = pd.read_csv(asm.ADIR / "assumptions.csv", dtype=str).set_index("id")
    log = asm.read_changelog()
    for row in log.iloc[::-1].itertuples():
        cols = list(asm.SCENARIOS) if row.scenario == "all" else [row.scenario]
        for c in cols:
            if abs(float(raw.at[row.assumption_id, c]) - float(row.new_value)) > 1e-12:
                raise SystemExit(f"{row.assumption_id}/{c}: current {raw.at[row.assumption_id, c]} != log new {row.new_value}")
            raw.at[row.assumption_id, c] = row.old_value
    out = asm.ADIR / "snapshots" / "assumptions_v1.0.csv"
    out.parent.mkdir(exist_ok=True)
    raw.reset_index().to_csv(out, index=False)
    print(f"wrote {out}")


if __name__ == "__main__":
    main()
