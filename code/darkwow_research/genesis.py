"""The nine DarkWow genesis contracts.

Source of truth: ``src/sdk/src/crypto/contract_id.rs`` (the ``lazy_static!``
block) and ``doc/src/arch/genesis.md`` in
https://github.com/PatrickMockridge/DarkWow (``linear-master``).

Every genesis ``ContractId`` is::

    ContractId = poseidon_hash([CONTRACT_ID_PREFIX, 0, counter])
               = poseidon_hash([42, pallas::Base::zero(), counter])

The middle element is the *x-coordinate* slot of the derivation used for
user-deployed contracts (``poseidon_hash([42, pk.x, pk.y])``). Zero is not
the x-coordinate of any Pallas point, so no key pair can ever sign as the
"deployer" of a genesis contract. Counters 0 and 1 are unused; genesis starts
at 2.

Poseidon over the Pallas base field is *not* re-implemented here -- the
point of this module is the registry (who is at which counter, and why),
not recomputing 32-byte IDs. Use the Rust crate for that.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

CONTRACT_ID_PREFIX = 42
GENESIS_X_COORDINATE = 0  # pallas::Base::zero() -- never a valid point x
FIRST_GENESIS_COUNTER = 2
GENESIS_HEIGHT = 1


class Role(str, Enum):
    CONSENSUS_CRITICAL = "consensus-critical"
    ECOSYSTEM = "ecosystem infrastructure (O-Cap primitive)"


@dataclass(frozen=True)
class GenesisContract:
    counter: int
    name: str
    crate: str
    role: Role
    purpose: str
    genesis_position: int  # tx index inside block 1 (0 is the coinbase)

    @property
    def derivation(self) -> str:
        return f"poseidon_hash([{CONTRACT_ID_PREFIX}, {GENESIS_X_COORDINATE}, {self.counter}])"

    @property
    def is_consensus_critical(self) -> bool:
        return self.role is Role.CONSENSUS_CRITICAL


# Ordered exactly as build_genesis_deployment_txs() / genesis_contracts() emit them
# (positions 1..=9 of block 1). Note the order is NOT sorted by counter: NativeToken
# (4) is deployed before PromissoryNote (3).
GENESIS_CONTRACTS: tuple[GenesisContract, ...] = (
    GenesisContract(2, "Deployooor", "dwow_deployooor_contract", Role.CONSENSUS_CRITICAL,
                    "Deploys and immutably locks every later WASM contract", 1),
    GenesisContract(4, "NativeToken", "dwow_native_token_contract", Role.CONSENSUS_CRITICAL,
                    "Coinbase (PoWRewardV1), fee payment, Pedersen mass-balance supply audit", 2),
    GenesisContract(3, "PromissoryNote", "dwow_promissory_note_contract", Role.ECOSYSTEM,
                    "Privacy-first DeFi token layer: mint, burn, transfer, atomic OTC swap", 3),
    GenesisContract(5, "Identity", "dwow_identity_contract", Role.ECOSYSTEM,
                    "ZK-verifiable credentials and selective-disclosure capability proofs", 4),
    GenesisContract(6, "Oracle", "dwow_oracle_contract", Role.ECOSYSTEM,
                    "Push-model external data feeds (price, weather, randomness)", 5),
    GenesisContract(7, "Attestation", "dwow_attestation_contract", Role.ECOSYSTEM,
                    "Claims, predicates, delegation and slashing -- the trust layer", 6),
    GenesisContract(8, "Purse", "dwow_purse_contract", Role.ECOSYSTEM,
                    "Fungible capability container with hidden balances and token types", 7),
    GenesisContract(9, "Box", "dwow_box_contract", Role.ECOSYSTEM,
                    "Capability delegation / restriction container, consumed on open", 8),
    GenesisContract(10, "MultiSig", "dwow_multisig_contract", Role.ECOSYSTEM,
                    "N-of-M threshold approvals, private ZK voting", 9),
)


def by_counter(counter: int) -> GenesisContract:
    for c in GENESIS_CONTRACTS:
        if c.counter == counter:
            return c
    raise KeyError(f"no genesis contract at counter {counter}")


def consensus_critical() -> tuple[GenesisContract, ...]:
    return tuple(c for c in GENESIS_CONTRACTS if c.is_consensus_critical)


def ecosystem() -> tuple[GenesisContract, ...]:
    return tuple(c for c in GENESIS_CONTRACTS if not c.is_consensus_critical)


#: Header of block 1, per genesis.md "Genesis Block".
GENESIS_HEADER = {
    "height": GENESIS_HEIGHT,
    "previous": "0x" + "00" * 32,
    "timestamp": 0,
    "target": "u32::MAX",
    "transactions": 1 + len(GENESIS_CONTRACTS),  # coinbase + 9 deployments
    "merkle_root": "blake3 over all 10 transactions",
    "randomx_key": "blake3(height.to_le_bytes())",
}


if __name__ == "__main__":  # pragma: no cover - convenience CLI
    print(f"{'pos':>3} {'ctr':>3}  {'name':<15} {'role':<45} derivation")
    for c in GENESIS_CONTRACTS:
        print(f"{c.genesis_position:>3} {c.counter:>3}  {c.name:<15} {c.role.value:<45} {c.derivation}")
