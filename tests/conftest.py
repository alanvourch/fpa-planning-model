"""Shared fixtures: one model run per test session (the run takes a few
seconds) plus the loaded assumptions. Tests never read the planted-deviation
document except in test_bridge, where it is the answer key."""

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from model import assumptions as asm, dataset, decision as decision_mod, plan  # noqa: E402


@pytest.fixture(scope="session")
def assumptions():
    return asm.load()


@pytest.fixture(scope="session")
def world():
    """actuals + budget, generated in memory (no files written)."""
    a, roster, wf, drivers, actual, budget = dataset.generate(write=False)
    return {"assumptions": a, "roster": roster, "wf": wf, "drivers": drivers, "actual": actual, "budget": budget}


@pytest.fixture(scope="session")
def opening(world):
    return dataset.state_after(world["actual"], world["actual"].months[-1])


@pytest.fixture(scope="session")
def months():
    return plan.horizon()


@pytest.fixture(scope="session")
def decision(world, opening, months):
    return decision_mod.evaluate(world["assumptions"], world["roster"], opening, months)


@pytest.fixture(scope="session")
def output_dir():
    return ROOT / "output"
