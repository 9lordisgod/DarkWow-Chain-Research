"""DarkWow block-reward (emission) schedule, ported 1:1 from Rust.

Source of truth: ``src/sdk/src/blockchain.rs`` (``mod reward``,
``expected_reward()``, ``fixed_pow_decay()``) on the ``linear-master`` branch
of https://github.com/PatrickMockridge/DarkWow.

The schedule is "Satoshi with the steps sanded off": a continuous exponential
decay with a 4-year half-life that lands on a perpetual 1 %/year tail
emission instead of a hard cap.

    R(0) = 0                              (pre-genesis)
    R(1) = R0                             (genesis block)
    R(h) = max(R0 * 2^(-(h-1)/H), R_tail) for h >= 2

Consensus computes ``2^(-(h-1)/H)`` with 32-bit fixed-point binary
exponentiation so that every node, on every CPU, gets the same integer.
Floating point MUST NOT be used for supply computation -- and it is not used
anywhere in this module either.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterator

# --- constants: src/sdk/src/blockchain.rs::reward -------------------------------------------

#: 1 DRKW = 10^8 base units.
BASE_UNITS_PER_DRKW = 100_000_000

#: R0 = floor(2.1e15 * ln 2 / 1_051_920) = ~13.84 DRKW. Paid in full at height 1.
INITIAL_REWARD = 1_383_764_049

#: Half-life in blocks (~4 years at 120 s blocks).
HALF_LIFE_BLOCKS = 1_051_920

#: Perpetual tail: floor(21_000_000 * 0.01 * 10^8 / 262_980) = ~0.80 DRKW / block.
TAIL_REWARD = 79_853_981

#: 21 M DRKW is a *reference* supply (where the curve meets the tail), not a cap.
TAIL_EMISSION_REFERENCE_SUPPLY = 21_000_000 * BASE_UNITS_PER_DRKW

#: 365.25 * 24 * 3600 / 120
BLOCKS_PER_YEAR = 262_980

#: Target block interval in seconds.
BLOCK_TIME_SECONDS = 120

#: floor(2^(-1/H) * 2^32) -- the per-block decay factor in Q32 fixed point.
DECAY_FP = 4_294_964_465
FP_SHIFT = 32

_U64_MAX = (1 << 64) - 1


# --- consensus functions -------------------------------------------------------------------


def fixed_pow_decay(exp: int) -> int:
    """Return ``DECAY_FP^exp`` in Q32 fixed point using binary exponentiation.

    Mirrors ``fixed_pow_decay()`` exactly, including the truncating right
    shift after every multiply (that truncation is why the schedule drifts a
    hair *below* the ideal real-valued curve -- see the Week 1 notes).
    """
    if exp < 0:
        raise ValueError("exp must be non-negative")
    result = 1 << FP_SHIFT  # 1.0
    base = DECAY_FP
    while exp > 0:
        if exp & 1:
            result = ((result * base) >> FP_SHIFT) & _U64_MAX
        base = ((base * base) >> FP_SHIFT) & _U64_MAX
        exp >>= 1
    return result


def _mul_fixed_point(reward: int, decay_fp: int) -> int:
    """``BlockReward::mul_fixed_point`` -- (reward * decay) >> 32, saturating to u64."""
    shifted = (reward * decay_fp) >> FP_SHIFT
    return _U64_MAX if shifted > _U64_MAX else shifted


def expected_reward(height: int) -> int:
    """Block reward in base units for ``height`` (``expected_reward()`` in Rust)."""
    if height < 0:
        raise ValueError("height must be non-negative")
    if height == 0:
        return 0
    if height == 1:
        return INITIAL_REWARD
    decay = fixed_pow_decay(height - 1)
    reward = _mul_fixed_point(INITIAL_REWARD, decay)
    return TAIL_REWARD if reward <= TAIL_REWARD else reward


def ideal_reward(height: int) -> float:
    """The real-valued curve the fixed-point code approximates (for comparison only)."""
    if height == 0:
        return 0.0
    if height == 1:
        return float(INITIAL_REWARD)
    r = INITIAL_REWARD * 2.0 ** (-(height - 1) / HALF_LIFE_BLOCKS)
    return max(r, float(TAIL_REWARD))


# --- derived quantities ------------------------------------------------------------------


def tail_onset_height() -> int:
    """First height at which the consensus reward equals ``TAIL_REWARD``.

    ``expected_reward`` is monotone non-increasing, so bisection is exact.
    """
    lo, hi = 1, HALF_LIFE_BLOCKS * 20  # Rust test asserts tail is reached by 20 half-lives
    while lo < hi:
        mid = (lo + hi) // 2
        if expected_reward(mid) <= TAIL_REWARD:
            hi = mid
        else:
            lo = mid + 1
    return lo


def cumulative_supply(height: int) -> int:
    """Exact total minted after ``height`` blocks (sum of ``expected_reward`` 1..height).

    Sums block by block through the exponential phase and switches to a
    closed form once the tail floor is reached, so 100-year horizons stay cheap.
    """
    if height <= 0:
        return 0
    onset = tail_onset_height()
    upto = min(height, onset - 1)
    total = sum(expected_reward(h) for h in range(1, upto + 1))
    if height >= onset:
        total += (height - onset + 1) * TAIL_REWARD
    return total


@dataclass(frozen=True)
class Milestone:
    year: float
    height: int
    reward: int
    supply: int

    @property
    def reward_drkw(self) -> float:
        return self.reward / BASE_UNITS_PER_DRKW

    @property
    def supply_drkw(self) -> float:
        return self.supply / BASE_UNITS_PER_DRKW

    @property
    def annual_inflation_pct(self) -> float:
        """Forward-looking inflation: one year of emission at this height's reward."""
        if self.supply == 0:
            return float("inf")
        return 100.0 * self.reward * BLOCKS_PER_YEAR / self.supply


def iter_supply(max_height: int, step: int) -> Iterator[Milestone]:
    """Yield exact ``Milestone`` rows every ``step`` blocks in one O(max_height) pass."""
    total = 0
    onset = tail_onset_height()
    for h in range(1, max_height + 1):
        r = TAIL_REWARD if h >= onset else expected_reward(h)
        total += r
        if h % step == 0 or h == 1 or h == max_height:
            yield Milestone(year=h / BLOCKS_PER_YEAR, height=h, reward=r, supply=total)


def height_at_years(years: float) -> int:
    return int(round(years * BLOCKS_PER_YEAR))


if __name__ == "__main__":  # pragma: no cover - convenience CLI
    import sys

    heights = [int(a) for a in sys.argv[1:]] or [0, 1, 2, HALF_LIFE_BLOCKS + 1, tail_onset_height()]
    for h in heights:
        r = expected_reward(h)
        print(f"height {h:>10,}  reward {r:>14,} base units  = {r / BASE_UNITS_PER_DRKW:.8f} DRKW")
