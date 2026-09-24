import pytest

from darkwow_research import uncle_split as us
from darkwow_research.emission import INITIAL_REWARD


def test_pin_percentages_halve_per_depth():
    assert [round(share, 4) for _, share, _ in us.pin_table()] == [50.0, 25.0, 12.5, 6.25, 3.125, 1.5625]


def test_no_uncles_pays_full_base_reward():
    assert us.compute_reward(INITIAL_REWARD, []) == (INITIAL_REWARD, [])


def test_single_depth_one_uncle_splits_fifty_fifty():
    canonical, paid = us.compute_reward(INITIAL_REWARD, [us.UncleBlock.offered(INITIAL_REWARD, 1)])
    assert paid == [INITIAL_REWARD // 2]
    assert us.verify_uncle_split(INITIAL_REWARD, canonical, paid)


def test_rejected_pin_pays_zero_and_canonical_keeps_it():
    uncles = [us.UncleBlock.offered(INITIAL_REWARD, 2, accept=False)]
    canonical, paid = us.compute_reward(INITIAL_REWARD, uncles)
    assert paid == [0]
    assert canonical == INITIAL_REWARD


@pytest.mark.parametrize("depths", [(1,), (1, 2), (1, 2, 3, 4, 5, 6), (6, 6, 6)])
def test_mass_balance_invariant_holds_for_any_accepted_set(depths):
    uncles = [us.UncleBlock.offered(INITIAL_REWARD, d) for d in depths]
    canonical, paid = us.compute_reward(INITIAL_REWARD, uncles)
    assert us.verify_uncle_split(INITIAL_REWARD, canonical, paid)
    assert canonical >= 0


def test_all_six_depths_leave_canonical_just_over_a_third():
    # 1/2 + 1/4 + ... + 1/64 = 63/64 paid out; canonical keeps 1/64 + rounding
    uncles = [us.UncleBlock.offered(INITIAL_REWARD, d) for d in range(1, 7)]
    canonical, _ = us.compute_reward(INITIAL_REWARD, uncles)
    assert abs(canonical - INITIAL_REWARD / 64) < 8


def test_split_for_uncle_saturates_like_rust():
    assert us.split_for_uncle(INITIAL_REWARD, 64) == 0
    assert us.split_for_uncle(INITIAL_REWARD, 0) == INITIAL_REWARD


def test_depth_outside_consensus_window_is_rejected():
    with pytest.raises(ValueError):
        us.UncleBlock.offered(INITIAL_REWARD, 0)
    with pytest.raises(ValueError):
        us.UncleBlock.offered(INITIAL_REWARD, us.MAX_UNCLE_DEPTH + 1)
