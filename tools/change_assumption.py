"""Change one assumption and log it. The only sanctioned way to edit values.

Usage:
  .venv/Scripts/python.exe tools/change_assumption.py --id nrr_annual --scenario base \
      --value 1.04 --version 1.4 --by "Alan Vourc'h (FP&A)" --reason "Q3 churn review"
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from model import assumptions as asm  # noqa: E402


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--id", required=True)
    p.add_argument("--scenario", default="all", choices=["all", "base", "upside", "downside"])
    p.add_argument("--value", required=True, type=float)
    p.add_argument("--version", required=True)
    p.add_argument("--by", required=True)
    p.add_argument("--reason", required=True)
    args = p.parse_args()
    asm.record_change(args.id, args.scenario, args.value, args.reason, args.by, args.version)
    print(f"{args.id} [{args.scenario}] -> {args.value} logged as v{args.version}")


if __name__ == "__main__":
    main()
