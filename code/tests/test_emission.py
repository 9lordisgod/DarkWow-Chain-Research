"""Mirrors the Rust unit tests in ``src/sdk/src/blockchain.rs::reward_tests``
plus a few checks on the numbers quoted in the Week 1 notes."""

import math

import pytest

from darkwow_research import emission as em


def test_reward_formula_key_points():
    assert em.expected_reward(0) == 0
    assert em.expected_reward(1) == em.INITIAL_REWARD
    at_half = em.expected_reward(em.HALF_LIFE_BLOCKS + 1)
    expected_half = em.INITIAL_REWARD // 2
    assert abs(at_half - expected_half) <= expected_half // 100  # same 1 % tolerance as Rust
    assert em.expected_reward(em.HALF_LIFE_BLOCKS * 20) == em.TAIL_REWARD


def test_reward_monotonic_decrease():
    prev = em.expected_reward(1)
    for h in range(2, 1000):
        cur = em.expected_reward(h)
        assert cur <= prev, (h, cur, prev)
        prev = cur


def test_binary_exp_additive_property():
    a, b = 1000, 2000
    product = (em.fixed_pow_decay(a) * em.fixed_pow_decay(b)) >> 32
    assert abs(em.fixed_pow_decay(a + b) - product) <= 5


def test_decay_fp_matches_documented_derivation():
    assert em.DECAY_FP == math.floor(2 ** (-1 / em.HALF_LIFE_BLOCKS) * 2**32)


def test_constants_match_documented_derivations():
    assert em.INITIAL_REWARD == math.floor(em.TAIL_EMISSION_REFERENCE_SUPPLY * math.log(2) / em.HALF_LIFE_BLOCKS)
    assert em.TAIL_REWARD == math.floor(21_000_000 * 0.01 * 10**8 / em.BLOCKS_PER_YEAR)
    assert em.BLOCKS_PER_YEAR == int(365.25 * 24 * 3600 / em.BLOCK_TIME_SECONDS)


def test_tail_onset_is_about_16_and_a_half_years():
    onset = em.tail_onset_height()
    assert em.expected_reward(onset - 1) > em.TAIL_REWARD
    assert em.expected_reward(onset) == em.TAIL_REWARD
    assert 16.0 < onset / em.BLOCKS_PER_YEAR < 17.0


def test_fixed_point_never_exceeds_ideal_curve():
    # Truncating shifts can only round *down*, so consensus <= ideal everywhere
    # (until both clamp to the tail).
    for h in (2, 10, 1_000, 100_000, em.HALF_LIFE_BLOCKS, 3 * em.HALF_LIFE_BLOCKS):
        assert em.expected_reward(h) <= em.ideal_reward(h) + 1


def test_cumulative_supply_closed_form_matches_brute_force():
    n = 5_000
    assert em.cumulative_supply(n) == sum(em.expected_reward(h) for h in range(1, n + 1))


def test_negative_inputs_rejected():
    with pytest.raises(ValueError):
        em.expected_reward(-1)
    with pytest.raises(ValueError):
        em.fixed_pow_decay(-1)
