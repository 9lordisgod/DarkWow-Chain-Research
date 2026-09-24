"""Reference models used by the DarkWow Chain Research notes.

Every module here is a *pure-Python re-derivation* of a consensus rule taken
from the DarkWow source tree (https://github.com/PatrickMockridge/DarkWow,
branch ``linear-master``) or from "The DarkWow Book". The goal is to make the
numbers quoted in the weekly write-ups reproducible, not to ship a node.

Modules
-------
emission     -- ``expected_reward()`` / ``fixed_pow_decay()`` from
                ``src/sdk/src/blockchain.rs`` (integer-only, no floats).
uncle_split  -- ``compute_reward()`` pin split from
                ``src/linear/src/supply_chain.rs`` and the subtractive
                mass-balance invariant.
genesis      -- the nine genesis contracts, their counters, crates and roles
                from ``src/sdk/src/crypto/contract_id.rs`` / ``genesis.md``.
"""

from . import emission, genesis, uncle_split

__all__ = ["emission", "genesis", "uncle_split"]
