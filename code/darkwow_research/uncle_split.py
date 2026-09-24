"""Uncle Merkle pin mechanism -- the subtractive coinbase split.

Source of truth: ``compute_reward()`` in ``src/linear/src/supply_chain.rs``
and ``BlockReward::split_for_uncle()`` in ``src/sdk/src/blockchain.rs``
(https://github.com/PatrickMockridge/DarkWow, ``linear-master``), as
specified in *The DarkWow Book*, "Uncle Merkle Consensus".

Rules (from the spec):

* The canonical chain is *obligated* to offer a pin to every valid uncle.
* Pin value is ``base_reward / 2^depth`` -- 50 % at depth 1, 25 % at depth 2,
  ... down to 1.5625 % at ``MAX_UNCLE_DEPTH = 6``.
* The uncle miner accepts or rejects once ("use it or lose it"). Accepting
  is strictly dominant: it pays > 0, rejecting pays 0.
* The split is **subtractive**: pins come out of the canonical miner's base
  reward. Nothing extra is minted.

Invariant enforced by ``verify_uncle_split()`` before a block hits disk:

    canonical_reward + sum(uncle_rewards) == base_reward   (exactly 100 %)
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

MAX_UNCLE_DEPTH = 6


def split_for_uncle(base_reward: int, depth: int) -> int:
    """``BlockReward::split_for_uncle`` -- ``base_reward / 2^depth``.

    The Rust version deliberately makes any depth >= 64 yield 0 rather than
    wrapping; consensus separately rejects depth > ``MAX_UNCLE_DEPTH``.
    """
    if depth < 0:
        raise ValueError("depth must be non-negative")
    if depth >= 64:
        return 0
    return base_reward // (1 << depth)


@dataclass(frozen=True)
class UncleBlock:
    """The two fields of ``UncleBlock`` that the reward split reads."""

    depth: int
    pin_accepted: bool
    pin_confirmed: int  # base units, normally == split_for_uncle(base, depth)

    @classmethod
    def offered(cls, base_reward: int, depth: int, accept: bool = True) -> "UncleBlock":
        if not 1 <= depth <= MAX_UNCLE_DEPTH:
            raise ValueError(f"uncle depth must be in 1..={MAX_UNCLE_DEPTH}, got {depth}")
        return cls(depth=depth, pin_accepted=accept, pin_confirmed=split_for_uncle(base_reward, depth))


def compute_reward(base_reward: int, uncles: Sequence[UncleBlock]) -> tuple[int, list[int]]:
    """Port of ``compute_reward()``: returns ``(canonical_reward, uncle_rewards)``.

    An uncle is paid ``pin_confirmed`` only if ``pin_accepted``; a rejected
    pin pays 0 and the canonical miner keeps that share.
    """
    if not uncles:
        return base_reward, []
    uncle_rewards = [u.pin_confirmed if u.pin_accepted else 0 for u in uncles]
    total_pin_confirmed = sum(uncle_rewards)
    # Rust: base.checked_sub(total).unwrap_or(0); verify_uncle_split rejects overflow at commit.
    canonical_reward = max(base_reward - total_pin_confirmed, 0)
    return canonical_reward, uncle_rewards


def verify_uncle_split(base_reward: int, canonical_reward: int, uncle_rewards: Sequence[int]) -> bool:
    """Value-level mass balance: ``canonical + sum(uncles) == base``."""
    return canonical_reward + sum(uncle_rewards) == base_reward


def pin_table(base_reward: int = 1) -> list[tuple[int, float, float]]:
    """``(depth, uncle_share_pct, canonical_share_pct)`` for depth 1..MAX_UNCLE_DEPTH."""
    rows = []
    for d in range(1, MAX_UNCLE_DEPTH + 1):
        share = 100.0 / (1 << d)
        rows.append((d, share, 100.0 - share))
    return rows


if __name__ == "__main__":  # pragma: no cover - convenience CLI
    from .emission import BASE_UNITS_PER_DRKW, INITIAL_REWARD

    base = INITIAL_REWARD
    uncles = [UncleBlock.offered(base, 1), UncleBlock.offered(base, 3), UncleBlock.offered(base, 2, accept=False)]
    canonical, paid = compute_reward(base, uncles)
    print(f"base      {base / BASE_UNITS_PER_DRKW:.8f} DRKW")
    for u, p in zip(uncles, paid):
        print(f"  uncle d={u.depth} accepted={u.pin_accepted!s:5} paid {p / BASE_UNITS_PER_DRKW:.8f} DRKW")
    print(f"canonical {canonical / BASE_UNITS_PER_DRKW:.8f} DRKW  invariant={verify_uncle_split(base, canonical, paid)}")
