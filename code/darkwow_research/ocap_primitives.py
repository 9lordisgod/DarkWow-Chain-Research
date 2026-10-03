"""The six O-Cap governance primitives and the two contracts that compose them.

A *registry*, transcribed from the DarkWow source at ``linear-master`` commit
``d775e37c`` (2026-10-03) and from *The DarkWow Book* (2026-09-03 export):

* function selectors of Box, Purse, Identity, MultiSig, Oracle, Attestation,
  Promissory Note, ``dao_escrow`` and ``escrow`` (``src/contract/*/src/lib.rs``,
  ``manifest.toml``);
* the 41 Halo2 circuits those nine contracts ship, with the counts a reader can
  re-check by grepping the ``.zk`` source (witness slots, ``constrain_instance``,
  ``constrain_equal_*``, Poseidon / EC / range-check calls, ``k``);
* the Book-era ``dao_escrow`` entrypoint table (17 selectors, pp. 1145-1146) next
  to the shipped one (10 selectors), so the retirement can be charted;
* the cross-contract composition matrix: which contract references which
  primitive's ``*_CONTRACT_ID`` from its entrypoint (a real child-call check) or
  only from ``lib.rs`` (a constant nothing reads).

Nothing here hashes or proves anything -- as in ``l1_circuits.py`` the module is
a description checked by counting, not a zkas parser.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Iterable

COMMIT = "d775e37c"
BOOK_DATE = "2026-09-03"

# --------------------------------------------------------------------------------------
# function selectors
# --------------------------------------------------------------------------------------


@dataclass(frozen=True)
class Selector:
    code: int
    name: str
    circuit: str | None = None  # zkas namespace proven by the call, if any

    @property
    def requires_proof(self) -> bool:
        return self.circuit is not None


@dataclass(frozen=True)
class Contract:
    name: str
    genesis_counter: int | None  # None = user-deployed (not one of the nine)
    selectors: tuple[Selector, ...]
    circuits: tuple["CircuitStats", ...] = field(default=())

    def selector(self, code: int) -> Selector:
        for s in self.selectors:
            if s.code == code:
                return s
        raise KeyError(f"{self.name} has no selector 0x{code:02x}")

    @property
    def proof_selectors(self) -> tuple[Selector, ...]:
        return tuple(s for s in self.selectors if s.requires_proof)


# --------------------------------------------------------------------------------------
# circuit statistics (grep counts over the .zk source with comments stripped)
# --------------------------------------------------------------------------------------


@dataclass(frozen=True)
class CircuitStats:
    contract: str
    circuit: str  # file stem under proof/
    k: int
    witnesses: int
    constrain_instance: int
    constrain_equal: int
    poseidon: int
    ec_mul: int
    merkle_root: int
    range_checks: int
    statements: int
    public_inputs: tuple[str, ...] = ()  # in constrain_instance order, where read

    @property
    def only_tx_pair_is_public(self) -> bool:
        """True when the proof publishes nothing but ``tx_binding`` and ``tx_nonce``."""
        return self.constrain_instance == 2

    @property
    def binds_a_secret(self) -> bool:
        """Does the circuit derive a key/commitment from a secret and constrain it?"""
        return self.constrain_equal > 0 or self.ec_mul > 0 or self.merkle_root > 0


def _c(contract, circuit, k, w, ci, ce, ph, ecm, mr, rc, st, pub=()):
    return CircuitStats(contract, circuit, k, w, ci, ce, ph, ecm, mr, rc, st, tuple(pub))


_TX = ("tx_binding", "tx_nonce")

# Leaf formulas at d775e37c.  Week 1 (commit ec914970, ``l1_circuits.py``) recorded these
# without ``owner_pub``; the field was folded in upstream, which closes Week 1 Finding 8.
LEAF_FORMULAS: dict[tuple[str, str], tuple[str, ...]] = {
    ("box", "put"): ("DOMAIN_MERKLE_LEAF", "box_id", "old_contents_commit", "old_state_nonce", "owner_pub"),  # put.zk:46
    ("box", "take"): ("DOMAIN_MERKLE_LEAF", "box_id", "contents_commit", "state_nonce", "owner_pub"),        # take.zk:42
    ("purse", "deposit"): ("DOMAIN_MERKLE_LEAF", "purse_id", "old_balance", "state_nonce", "owner_pub"),     # deposit.zk:66
    ("purse", "withdraw"): ("DOMAIN_MERKLE_LEAF", "purse_id", "old_balance", "state_nonce", "owner_pub"),    # withdraw.zk:71
}

CIRCUITS: tuple[CircuitStats, ...] = (
    # box -- leaf now folds owner_pub (closes Week 1 Finding 8)
    _c("box", "put", 11, 15, 5, 6, 5, 0, 1, 0, 23, ("nullifier", "expected_root", "new_leaf", *_TX)),
    _c("box", "take", 11, 12, 4, 4, 4, 0, 1, 0, 17, ("nullifier", "expected_root", *_TX)),
    # purse
    _c("purse", "balance", 11, 18, 7, 7, 5, 2, 1, 1, 29),
    _c("purse", "deposit", 11, 24, 10, 12, 6, 6, 1, 4, 52),
    _c("purse", "withdraw", 11, 24, 10, 13, 6, 6, 1, 5, 54),
    # promissory_note
    _c("promissory_note", "issue", 11, 14, 9, 2, 3, 2, 1, 1, 32),
    _c("promissory_note", "redeem", 11, 11, 8, 1, 3, 2, 0, 0, 27),
    _c("promissory_note", "register_type", 11, 13, 8, 0, 3, 2, 0, 1, 26),
    _c("promissory_note", "revoke", 11, 15, 10, 1, 8, 2, 1, 2, 41),
    _c("promissory_note", "transfer", 11, 11, 7, 0, 3, 2, 0, 1, 25),
    # identity
    _c("identity", "issue_credential", 11, 18, 3, 3, 5, 1, 0, 0, 33),
    _c("identity", "verify_capability", 11, 19, 10, 2, 6, 0, 0, 4, 42),
    # attestation -- eight of ten publish only the tx pair
    _c("attestation", "attest_slash", 11, 6, 2, 0, 1, 0, 0, 0, 3, _TX),
    _c("attestation", "check_not_revoked", 11, 4, 2, 0, 2, 0, 0, 0, 4, _TX),
    _c("attestation", "commit_fee_schedule", 11, 6, 2, 0, 1, 0, 0, 0, 3, _TX),
    _c("attestation", "consume_claim", 11, 8, 6, 3, 2, 1, 0, 0, 16,
       ("claim_id", "claimant_pub_x", "claimant_pub_y", "nullifier", *_TX)),
    _c("attestation", "create_attestation", 11, 6, 2, 0, 1, 0, 0, 0, 3, _TX),
    _c("attestation", "create_claim", 11, 7, 2, 0, 1, 0, 0, 0, 3, _TX),
    _c("attestation", "delegate_attestation", 11, 6, 3, 0, 2, 0, 0, 0, 5),
    _c("attestation", "update_delegation", 11, 6, 2, 0, 1, 0, 0, 0, 3, _TX),
    _c("attestation", "verify_chain", 11, 7, 2, 0, 1, 0, 0, 0, 3, _TX),
    _c("attestation", "verify_claim", 11, 6, 2, 0, 4, 0, 0, 0, 6, _TX),
    # oracle -- k = 13/14, the only non-k11 circuits in the set
    _c("oracle", "aggregate", 13, 17, 8, 2, 3, 0, 0, 17, 50),
    _c("oracle", "attest_value", 13, 9, 8, 0, 3, 0, 0, 0, 14),
    _c("oracle", "push_value", 13, 6, 6, 0, 3, 0, 0, 0, 12,
       ("oracle_id", "oracle_commitment", "value", "nullifier", *_TX)),
    _c("oracle", "push_value_commitment", 14, 8, 6, 1, 4, 0, 0, 0, 15),
    _c("oracle", "register_oracle", 13, 5, 4, 0, 2, 0, 0, 0, 8),
    _c("oracle", "set_oracle_active", 13, 6, 5, 0, 2, 0, 0, 0, 9),
    # multisig
    _c("multisig", "create_group", 11, 5, 5, 0, 1, 0, 0, 1, 8),
    _c("multisig", "finalize", 11, 5, 5, 1, 2, 0, 0, 0, 10),
    _c("multisig", "sign", 11, 5, 6, 0, 3, 0, 0, 0, 12),
    # dao_escrow (V2 circuits)
    _c("dao_escrow", "init", 11, 7, 4, 0, 2, 1, 0, 0, 18),
    _c("dao_escrow", "pay_premium", 11, 15, 2, 3, 3, 1, 0, 3, 29),
    _c("dao_escrow", "propose_claim", 11, 12, 3, 2, 4, 1, 0, 0, 23),
    _c("dao_escrow", "set_governance_config", 11, 8, 5, 3, 2, 1, 0, 0, 11),
    _c("dao_escrow", "vote_claim", 11, 12, 3, 2, 3, 1, 0, 0, 18),
    # escrow (the contract that actually composes Box + Purse)
    _c("escrow", "cancel", 11, 7, 6, 2, 2, 1, 0, 0, 15),
    _c("escrow", "claim", 11, 8, 5, 3, 3, 1, 0, 0, 17,
       ("escrow_id", "escrow_seller_commitment", "tx_binding", "tx_nonce", "spent_nullifier")),
    _c("escrow", "create_escrow", 11, 11, 4, 2, 3, 1, 0, 0, 21),
    _c("escrow", "fund", 11, 8, 6, 0, 1, 2, 1, 0, 11),
    _c("escrow", "refund", 11, 11, 8, 4, 2, 1, 0, 0, 19),
)


def circuits_for(contract: str) -> tuple[CircuitStats, ...]:
    return tuple(c for c in CIRCUITS if c.contract == contract)


def circuit(contract: str, name: str) -> CircuitStats:
    for c in CIRCUITS:
        if c.contract == contract and c.circuit == name:
            return c
    raise KeyError(f"{contract}/{name}.zk")


# --------------------------------------------------------------------------------------
# the contracts
# --------------------------------------------------------------------------------------


def _sel(*rows):
    return tuple(Selector(*r) for r in rows)


BOX = Contract("box", 9, _sel((0x00, "Initialize"), (0x01, "Put", "Put"), (0x02, "Take", "Take")),
               circuits_for("box"))

PURSE = Contract("purse", 8, _sel(
    (0x00, "Initialize"), (0x01, "Deposit", "Deposit"), (0x02, "Withdraw", "Withdraw"),
    (0x03, "Balance", "Balance")), circuits_for("purse"))

PROMISSORY_NOTE = Contract("promissory_note", 3, _sel(
    (0x00, "RegisterTypeV1", "RegisterType_V2"), (0x01, "RedeemV1", "Redeem_V2"),
    (0x02, "IssueV1", "Issue_V2"), (0x03, "RevokeV1", "Revoke_V2"),
    (0x04, "TransferV1", "Transfer_V2"), (0x05, "OtcSwapV1")), circuits_for("promissory_note"))

IDENTITY = Contract("identity", 5, _sel(
    (0x00, "InitializeV1"), (0x01, "IssueCredentialV1", "IssueCredentialV2"),
    (0x02, "RevokeCredentialV1"), (0x04, "RegisterCapabilityV1"), (0x05, "IssueCapabilityV1"),
    (0x06, "VerifyCapabilityV1", "VerifyCapabilityV2"), (0x07, "RevokeCapabilityV1"),
    (0x08, "RegisterIssuerV1")), circuits_for("identity"))

ATTESTATION = Contract("attestation", 7, _sel(
    (0x00, "CreateAttestationV1", "CreateAttestationV2"), (0x01, "RevokeAttestationV1"),
    (0x02, "ExpireAttestationV1"), (0x03, "CreateClaimV1", "CreateClaimV2"),
    (0x04, "VerifyClaimV1", "VerifyClaimV2"), (0x05, "ConsumeClaimV1", "ConsumeClaimV2"),
    (0x06, "ValidateClaimV1"), (0x07, "CheckNotRevokedV1", "CheckNotRevokedV2"),
    (0x08, "DelegateAttestationV1", "DelegateAttestationV2"), (0x09, "VerifyChainV1", "VerifyChainV2"),
    (0x0A, "UpdateDelegationV1", "UpdateDelegationV2"), (0x0B, "AttestSlashV1", "AttestSlashV2"),
    (0x0C, "CommitFeeScheduleV1", "CommitFeeScheduleV2"), (0x0D, "CheckAttestationV1")),
    circuits_for("attestation"))

ORACLE = Contract("oracle", 6, _sel(
    (0x00, "RegisterOracleV1", "RegisterOracleV2"), (0x01, "PushValueV1", "PushValueV2"),
    (0x02, "AttestValueV1", "AttestValueV2"), (0x03, "PushValueCommitmentV1", "PushValueCommitmentV2"),
    (0x04, "AggregateV1", "AggregateV2"), (0x05, "SetOracleActiveV1", "SetOracleActiveV2")),
    circuits_for("oracle"))

MULTISIG = Contract("multisig", 10, _sel(
    (0x00, "InitializeV1"), (0x01, "CreateGroupV1", "CreateGroupV2"), (0x02, "SignV1", "SignV2"),
    (0x03, "FinalizeV1", "FinalizeV2")), circuits_for("multisig"))

# dao_escrow as shipped at d775e37c (manifest.toml + lib.rs)
DAO_ESCROW = Contract("dao_escrow", None, _sel(
    (0x00, "InitializeV1", "InitV2"), (0x01, "UpdateV1", "SetGovernanceConfigV2"),
    (0x02, "PayPremiumV1", "PayPremiumV2"), (0x03, "WithdrawV1", "SetGovernanceConfigV2"),
    (0x04, "EndowmentWithdrawV1"), (0x05, "TreasurySpendV1"),
    (0x07, "ProposeClaimV1", "ProposeClaimV2"), (0x08, "VoteClaimV1", "VoteClaimV2"),
    (0x09, "ExecuteClaimV1"), (0x0D, "CancelClaimV1")), circuits_for("dao_escrow"))

ESCROW = Contract("escrow", None, _sel(
    (0x00, "InitializeV1"), (0x01, "CreateEscrowV1", "CreateEscrowV2"), (0x02, "FundV1", "FundEscrowV2"),
    (0x03, "ClaimV1", "ClaimEscrowV2"), (0x04, "RefundV1", "RefundEscrowV2"),
    (0x05, "CancelV1", "CancelEscrowV2")), circuits_for("escrow"))

PRIMITIVES: tuple[Contract, ...] = (PURSE, BOX, IDENTITY, MULTISIG, ORACLE, ATTESTATION)
CONTRACTS: dict[str, Contract] = {
    c.name: c for c in (*PRIMITIVES, PROMISSORY_NOTE, DAO_ESCROW, ESCROW)
}

# --------------------------------------------------------------------------------------
# dao_escrow: Book-era design vs shipped code
# --------------------------------------------------------------------------------------


class Fate(str, Enum):
    KEPT = "kept"          # same selector, same meaning
    RETIRED = "retired"    # selector removed -> InvalidFunction
    REWIRED = "rewired"    # kept, but what authorises it changed


@dataclass(frozen=True)
class BookSelector:
    code: int
    name: str
    book_capability: str   # the capability column of the Book's table (pp. 1145-1146)
    fate: Fate
    note: str = ""


BOOK_DAO_ESCROW: tuple[BookSelector, ...] = (
    BookSelector(0x00, "InitializeV1", "none (creator)", Fate.KEPT),
    BookSelector(0x01, "UpdateV1", "none (creator)", Fate.KEPT),
    BookSelector(0x02, "PayPremiumV1", "none", Fate.KEPT, "child PN::TransferV1 at slot 0"),
    BookSelector(0x03, "WithdrawV1", "capability-gated", Fate.REWIRED, "owner's SetGovernanceConfigV2 proof"),
    BookSelector(0x04, "EndowmentWithdrawV1", "board_endowment via Box", Fate.REWIRED,
                 "MultiSig::FinalizeV1 child, fail-closed"),
    BookSelector(0x05, "TreasurySpendV1", "board_treasury via Box", Fate.REWIRED,
                 "MultiSig::FinalizeV1 child, fail-closed"),
    BookSelector(0x06, "EnableDrainProtectionV1", "none", Fate.RETIRED, "flag nothing read (OBL-C151)"),
    BookSelector(0x07, "ProposeClaimV1", "member_vote", Fate.REWIRED, "membership proof, no Identity"),
    BookSelector(0x08, "VoteClaimV1", "member_vote", Fate.REWIRED, "group member proof"),
    BookSelector(0x09, "ExecuteClaimV1", "none (quorum)", Fate.KEPT),
    BookSelector(0x0A, "RegisterCapabilityRequirementV1", "board_treasury", Fate.RETIRED),
    BookSelector(0x0B, "VerifyMemberCapabilityV1", "none (is the check)", Fate.RETIRED,
                 "Identity::VerifyCapabilityV1 child never wired"),
    BookSelector(0x0C, "ResolveDisputeV1", "dispute_arbitrator", Fate.RETIRED,
                 "Oracle->Attestation->3-of-5 flow never implemented"),
    BookSelector(0x0D, "CancelClaimV1", "proposer identity match", Fate.KEPT),
    BookSelector(0x0E, "SetGovernanceConfigV1", "board_treasury", Fate.RETIRED, "folded into UpdateV1"),
    BookSelector(0x0F, "SetGovernanceActiveV1", "board_treasury", Fate.RETIRED,
                 "governance_active=false fail-open flag removed"),
    BookSelector(0x10, "DeactivateCapabilityRequirementV1", "board_treasury", Fate.RETIRED),
)

BOOK_DAO_ESCROW_ROLES = ("member_vote", "board_treasury", "board_endowment", "dispute_arbitrator")
BOOK_DAO_ESCROW_PRIMITIVES = ("Purse", "Box", "Identity", "Oracle", "Attestation", "PromissoryNote")
CODE_DAO_ESCROW_CHILDREN = ("promissory_note::TransferV1 (0x04, slot 0)", "multisig::FinalizeV1 (0x03, slot 1)")


def selector_retirement() -> dict[Fate, list[BookSelector]]:
    out: dict[Fate, list[BookSelector]] = {f: [] for f in Fate}
    for s in BOOK_DAO_ESCROW:
        out[s.fate].append(s)
    return out


def shipped_codes() -> set[int]:
    return {s.code for s in DAO_ESCROW.selectors}


# --------------------------------------------------------------------------------------
# composition matrix: who references whose *_CONTRACT_ID
# --------------------------------------------------------------------------------------


class RefKind(int, Enum):
    NONE = 0
    LIB_ONLY = 1    # constant declared in lib.rs, never read by a handler
    ENTRYPOINT = 2  # referenced from entrypoint.rs (child-call validation or comment)


_ENTRY: dict[str, tuple[str, ...]] = {
    "box": ("drain_protection", "escrow", "identity"),
    "purse": ("drain_protection", "escrow", "pool_stake", "stablecoin"),
    "identity": ("insurance_market", "labor_market", "tender"),
    "attestation": ("labor_market",),
    "oracle": (),
    "multisig": ("dao_escrow", "drain_protection"),
    "promissory_note": (
        "auction", "baccarat", "betting_stake", "bridge", "dao_escrow", "darkbet_exchange",
        "darktoshi_dice", "dex", "drain_protection", "escrow", "insurance_market", "labor_market",
        "lottery", "otc_swap", "pool_stake", "relayer_endowment", "roulette", "slot", "stablecoin",
        "subscription"),
}
_LIB: dict[str, tuple[str, ...]] = {
    "box": ("drain_protection", "escrow", "identity", "subscription"),
    "purse": ("betting_stake", "drain_protection", "escrow", "labor_market", "pool_stake",
              "relayer_endowment", "stablecoin", "subscription"),
    "identity": ("insurance_market", "labor_market", "tender"),
    "attestation": ("labor_market",),
    "oracle": ("darkbet_exchange",),
    "multisig": ("dao_escrow", "drain_protection"),
    "promissory_note": _ENTRY["promissory_note"] + ("game_room",),
}

# identity's entrypoint mentions BOX_CONTRACT_ID only in the comment explaining why the
# Box child check was *removed*; it is kept in the matrix as ENTRYPOINT with this caveat.
COMMENT_ONLY_REFS = {("box", "identity")}

PRIMITIVE_ROWS = ("purse", "box", "identity", "multisig", "oracle", "attestation", "promissory_note")

ALL_CONTRACTS = (
    "attestation", "auction", "baccarat", "bearer_bond", "betting_stake", "box", "bridge",
    "dao_escrow", "darkbet_exchange", "darktoshi_dice", "deployooor", "dex", "drain_protection",
    "escrow", "game_room", "identity", "insurance_market", "labor_market", "lottery", "multisig",
    "native_token", "oracle", "otc_swap", "pool_stake", "promissory_note", "purse",
    "relayer_endowment", "roulette", "slot", "stablecoin", "subscription", "tender",
)


def reference(primitive: str, consumer: str) -> RefKind:
    if consumer in _ENTRY[primitive]:
        return RefKind.ENTRYPOINT
    if consumer in _LIB[primitive]:
        return RefKind.LIB_ONLY
    return RefKind.NONE


def consumers(primitive: str, kind: RefKind = RefKind.ENTRYPOINT) -> tuple[str, ...]:
    return tuple(c for c in ALL_CONTRACTS if reference(primitive, c) == kind)


def composition_matrix(rows: Iterable[str] = PRIMITIVE_ROWS,
                       cols: Iterable[str] = ALL_CONTRACTS) -> list[list[int]]:
    return [[int(reference(r, c)) for c in cols] for r in rows]


def composers() -> tuple[str, ...]:
    """Contracts that reference at least one of the six governance primitives from an entrypoint."""
    six = [p for p in PRIMITIVE_ROWS if p != "promissory_note"]
    return tuple(c for c in ALL_CONTRACTS
                 if any(reference(p, c) == RefKind.ENTRYPOINT for p in six))


# --------------------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------------------


def _main() -> None:  # pragma: no cover
    print(f"Registry @ {COMMIT}; Book {BOOK_DATE}\n")
    for c in CONTRACTS.values():
        print(f"{c.name:16s} selectors={len(c.selectors):2d} proofs={len(c.proof_selectors):2d} "
              f"circuits={len(c.circuits):2d}")
    print("\ndao_escrow Book -> code:")
    for fate, rows in selector_retirement().items():
        print(f"  {fate.value:8s} {len(rows):2d}  " + ", ".join(f"0x{r.code:02x}" for r in rows))
    print("\ncomposition (entrypoint-level):")
    for p in PRIMITIVE_ROWS:
        print(f"  {p:16s} <- {', '.join(consumers(p)) or '-'}")
    print(f"\ncontracts composing a governance primitive: {', '.join(composers())}")


if __name__ == "__main__":  # pragma: no cover
    _main()
