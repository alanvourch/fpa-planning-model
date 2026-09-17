"""Assumption registry integrity: sources labelled, versions replayable,
guardrails and options consistent."""

import pandas as pd
import pytest

from model import assumptions as asm


def test_every_assumption_has_a_source_label(assumptions):
    t = assumptions.table
    assert set(t["source_type"].unique()) <= {"benchmark", "derived", "judgment"}
    assert (t["source"].str.len() > 10).all()
    assert (t[["base", "upside", "downside"]].notna()).all().all()


def test_benchmark_rows_name_a_source_that_was_read(assumptions):
    t = assumptions.table
    bench = t[t["source_type"] == "benchmark"]
    assert len(bench) >= 4
    for src in bench["source"]:
        assert any(k in src for k in ("SaaS Capital", "Benchmarkit")), src


def test_locations_are_derived_from_named_sources(assumptions):
    loc = assumptions.locations
    assert set(loc.index) == {"Montreal", "Paris", "Austin"}
    assert "Raymond Chabot" in loc.at["Montreal", "source"]
    assert "PwC" in loc.at["Paris", "source"]
    assert "IRS" in loc.at["Austin", "source"]
    assert (loc["employer_tax_rate"] > 0).all() and (loc["employer_tax_rate"] < 0.6).all()


def test_snapshot_plus_changelog_equals_current(assumptions):
    snap = asm.load_snapshot("1.0").table
    log = asm.read_changelog()
    replayed = asm.apply_changelog(snap, log)
    cur = assumptions.table
    for c in asm.SCENARIOS:
        pd.testing.assert_series_equal(replayed[c], cur[c], check_names=False)
    assert log["version"].iloc[-1] == assumptions.version
    assert set(log.columns) == set(asm.CHANGELOG_COLUMNS)
    assert (log["reason"].str.len() > 20).all()


def test_changelog_replays_in_order_and_refuses_bad_old_values(assumptions):
    snap = asm.load_snapshot("1.0").table
    log = asm.read_changelog()
    bad = log.copy()
    bad.loc[0, "old_value"] = "9.99"
    with pytest.raises(ValueError):
        asm.apply_changelog(snap, bad)


def test_override_is_in_memory_only(assumptions):
    other = assumptions.with_override("nrr_annual", 1.5, "base")
    assert other.value("nrr_annual", "base") == 1.5
    assert assumptions.value("nrr_annual", "base") != 1.5


def test_options_reference_existing_hiring_plans(assumptions):
    plans = set(assumptions.hiring_plans["plan_id"]) | {"hold"}
    for opt, row in assumptions.options.iterrows():
        assert row["hiring_plan"] in plans, opt
    for r in assumptions.hiring_plans.itertuples():
        assert r.role in assumptions.salaries.index and r.location in assumptions.locations.index


def test_scenario_ordering_is_coherent(assumptions):
    a = assumptions
    for k in ("logos_per_ramped_ae_month", "nrr_annual", "grr_annual", "attach_gain_pts_month"):
        assert a.value(k, "upside") >= a.value(k, "base") >= a.value(k, "downside"), k
    for k in ("cloud_unit_price_usd", "marketing_program_cost_per_new_logo"):
        assert a.value(k, "upside") <= a.value(k, "base") <= a.value(k, "downside"), k
