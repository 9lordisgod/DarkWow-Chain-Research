"""Oracle freshness: what the contract records, what a consumer could check, and
the liveness / staleness trade-off of the "epoch window" BUG-03 proposes.

Facts transcribed from ``src/contract/oracle`` at ``d775e37c``:

* ``Oracle { value, updated_at, oracle_commitment, is_active, ... }`` -- there is
  **no sequence number**; ``PushValueV1`` overwrites ``value`` and sets
  ``updated_at = get_verifying_block_height()`` (entrypoint.rs 389-401).
* ``push_value.zk`` publishes ``(oracle_id, oracle_commitment, value, nullifier,
  tx_binding, tx_nonce)``; the nullifier is ``H(1, oracle_secret, oracle_id,
  value)`` so the *same value* cannot be pushed twice, but a different value
  always can, and nothing orders pushes.
* ``db_lookup`` refuses a foreign ``ContractId`` (``src/runtime/import/db.rs``:
  "cross-contract access denied"), so **no contract can read the Oracle's state
  tree**.  A consumer learns an oracle value only from an ``Oracle`` call in the
  same transaction (a child whose ``value`` instance is proof-bound) -- which is
  by construction current -- or from a wire field it trusts.  ``darkbet_exchange``
  and ``insurance_market`` take the second route (``oracle_signature`` never
  verified, ``doc/src/contract/oracle.md``).

So the "host function fetching Oracle state" the brief worries about does not
exist; the staleness question is real for the *design* (``updated_at`` is the
only freshness datum and nobody reads it).  ``simulate`` quantifies what a
``max_age`` guard would buy and cost: a consumer that rejects values older than
``max_age`` blocks fails closed under operator withholding, at the price of
false rejections whenever the honest push cadence is slower than the window.
Deterministic (seeded ``random.Random``), standard library only.
"""

from __future__ import annotations

import random
from dataclasses import dataclass

BLOCK_SECONDS = 120


@dataclass(frozen=True)
class OracleRecord:
    value: int
    updated_at: int          # block height of the last PushValueV1
    is_active: bool = True

    def age(self, height: int) -> int:
        return height - self.updated_at


@dataclass(frozen=True)
class ReadPolicy:
    """What a consumer *could* enforce if it could see the record."""

    max_age: int | None = None    # None = accept any age (today's behaviour)
    require_active: bool = True

    def accept(self, rec: OracleRecord, height: int) -> bool:
        if self.require_active and not rec.is_active:
            return False
        if self.max_age is not None and rec.age(height) > self.max_age:
            return False
        return True


def push(rec: OracleRecord | None, value: int, height: int, spent: set[tuple[int]]) -> OracleRecord:
    """``push_value_v1``: last-write-wins; the nullifier only forbids repeating a *value*."""
    key = (value,)
    if key in spent:
        raise ValueError("DuplicateNullifier")
    spent.add(key)
    return OracleRecord(value, height, True if rec is None else rec.is_active)


# --------------------------------------------------------------------------------------
# simulation
# --------------------------------------------------------------------------------------


@dataclass(frozen=True)
class SimResult:
    max_age: int | None
    reads: int
    stale_accepted: int      # consumer used a value the operator was withholding behind
    false_rejected: int      # honest, current value rejected because the cadence was slow
    accepted: int

    @property
    def stale_rate(self) -> float:
        return self.stale_accepted / self.reads

    @property
    def false_reject_rate(self) -> float:
        return self.false_rejected / self.reads


def simulate(max_age: int | None, *, blocks: int = 20_000, push_every: int = 10,
             withhold_prob: float = 0.05, withhold_len: int = 40, read_every: int = 3,
             seed: int = 2) -> SimResult:
    """Walk ``blocks`` heights.  The operator pushes a fresh value every ``push_every``
    blocks (geometric jitter) except during *withholding episodes*: with probability
    ``withhold_prob`` at each scheduled push the operator goes silent for ``withhold_len``
    blocks while the true value has moved.  A consumer reads every ``read_every`` blocks
    and applies ``ReadPolicy(max_age)``.

    A read is *stale-accepted* when the operator is withholding and the policy accepts;
    *false-rejected* when the operator is honest-and-current and the policy rejects.
    """
    rng = random.Random(seed)
    policy = ReadPolicy(max_age)
    spent: set[tuple[int]] = set()
    rec = push(None, rng.randrange(1 << 30), 1, spent)
    withholding_until = 0
    next_push = 1 + max(1, int(rng.expovariate(1 / push_every)))
    reads = stale = false_rej = acc = 0
    for h in range(2, blocks + 1):
        if h >= next_push and h > withholding_until:
            if rng.random() < withhold_prob:
                withholding_until = h + withhold_len
            else:
                rec = push(rec, rng.randrange(1 << 30), h, spent)
            next_push = h + max(1, int(rng.expovariate(1 / push_every)))
        if h % read_every == 0:
            reads += 1
            ok = policy.accept(rec, h)
            withholding = h <= withholding_until
            if ok:
                acc += 1
                if withholding:
                    stale += 1
            elif not withholding:
                false_rej += 1
    return SimResult(max_age, reads, stale, false_rej, acc)


def tradeoff(windows=(None, 1, 2, 3, 5, 8, 10, 15, 20, 30, 40, 60), **kw) -> list[SimResult]:
    return [simulate(w, **kw) for w in windows]


def age_histogram(*, blocks: int = 20_000, push_every: int = 10, read_every: int = 3,
                  seed: int = 2, withhold_prob: float = 0.05, withhold_len: int = 40) -> dict[int, int]:
    """Age (blocks since ``updated_at``) seen by each read, honest and withheld periods together."""
    rng = random.Random(seed)
    spent: set[tuple[int]] = set()
    rec = push(None, rng.randrange(1 << 30), 1, spent)
    withholding_until = 0
    next_push = 1 + max(1, int(rng.expovariate(1 / push_every)))
    hist: dict[int, int] = {}
    for h in range(2, blocks + 1):
        if h >= next_push and h > withholding_until:
            if rng.random() < withhold_prob:
                withholding_until = h + withhold_len
            else:
                rec = push(rec, rng.randrange(1 << 30), h, spent)
            next_push = h + max(1, int(rng.expovariate(1 / push_every)))
        if h % read_every == 0:
            a = rec.age(h)
            hist[a] = hist.get(a, 0) + 1
    return hist


# --------------------------------------------------------------------------------------
# what the code offers a consumer today
# --------------------------------------------------------------------------------------

FRESHNESS_SOURCES = {
    "oracle.updated_at": ("block height of last push", "written by PushValueV1", "no on-chain reader"),
    "oracle.sequence": ("monotone counter", "does not exist", "-"),
    "child Oracle::PushValueV1 in same tx": ("value is a constrain_instance of PushValueV2",
                                            "proof-bound", "current by construction"),
    "params.oracle_signature (darkbet_exchange, insurance_market)": (
        "a field the consumer trusts", "never verified", "oracle.md: 'trusting its caller'"),
}


def _main() -> None:  # pragma: no cover
    print(f"{'max_age':>8} {'stale%':>7} {'false-reject%':>14} {'accept%':>8}")
    for r in tradeoff():
        print(f"{str(r.max_age):>8} {100 * r.stale_rate:7.2f} {100 * r.false_reject_rate:14.2f} "
              f"{100 * r.accepted / r.reads:8.2f}")


if __name__ == "__main__":  # pragma: no cover
    _main()
