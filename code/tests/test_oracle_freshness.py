"""Claims in weeks/week-02/README.md §5 (BUG-03): what the oracle records and what a
max-age window would buy."""

import pytest

from darkwow_research import oracle_freshness as of


def test_record_has_updated_at_but_no_sequence():
    rec = of.OracleRecord(value=42, updated_at=100)
    assert rec.age(130) == 30
    assert not hasattr(rec, "sequence")


def test_same_value_twice_collides_on_the_nullifier():
    spent = set()
    rec = of.push(None, 7, 10, spent)
    with pytest.raises(ValueError, match="DuplicateNullifier"):
        of.push(rec, 7, 20, spent)
    rec2 = of.push(rec, 8, 20, spent)   # a different value always goes through
    assert rec2.updated_at == 20 and rec2.value == 8


def test_default_policy_accepts_any_age():
    rec = of.OracleRecord(1, 0)
    assert of.ReadPolicy().accept(rec, 10_000)
    assert not of.ReadPolicy(max_age=5).accept(rec, 6)
    assert of.ReadPolicy(max_age=5).accept(rec, 5)
    assert not of.ReadPolicy().accept(of.OracleRecord(1, 0, is_active=False), 1)


def test_simulation_is_deterministic():
    a, b = of.simulate(5), of.simulate(5)
    assert a == b
    assert a.reads == 6666  # 20_000 blocks, read every 3rd


def test_no_window_means_stale_reads_are_accepted_at_the_withholding_rate():
    r = of.simulate(None)
    assert r.false_rejected == 0 and r.accepted == r.reads
    assert 0.10 < r.stale_rate < 0.25


def test_windows_trade_stale_acceptance_for_false_rejection_monotonically():
    rows = of.tradeoff()
    stale = [r.stale_rate for r in rows[1:]]
    false = [r.false_reject_rate for r in rows[1:]]
    assert stale == sorted(stale)
    assert false == sorted(false, reverse=True)


def test_five_block_window_blocks_almost_every_stale_read_but_rejects_nearly_half():
    r = of.simulate(5)
    assert r.stale_rate < 0.01
    assert 0.40 < r.false_reject_rate < 0.50


def test_age_histogram_mass_sits_below_push_cadence_when_honest():
    hist = of.age_histogram()
    total = sum(hist.values())
    young = sum(n for a, n in hist.items() if a <= 10)
    assert total == 6666
    assert 0.5 < young / total < 0.8


def test_freshness_sources_table():
    assert "oracle.sequence" in of.FRESHNESS_SOURCES
    assert of.FRESHNESS_SOURCES["oracle.sequence"][1] == "does not exist"
    assert of.FRESHNESS_SOURCES["oracle.updated_at"][2] == "no on-chain reader"
