"""The three L1 genesis contracts -- Box, Purse, Promissory Note -- as data.

Source of truth (https://github.com/PatrickMockridge/DarkWow, ``linear-master``,
read at commit ``ec914970``):

* ``src/contract/box/proof/{put,take}.zk``
* ``src/contract/purse/proof/{deposit,withdraw,balance}.zk``
* ``src/contract/promissory_note/proof/{register_type,issue,revoke,transfer,redeem}.zk``
* ``src/contract/{box,purse}/src/model/mod.rs`` -- ``*Params::encode()`` wire layouts
* ``src/contract/{box,purse,promissory_note}/src/lib.rs`` -- function selectors
* ``doc/src/arch/privacy.md`` §6 and ``doc/src/dev/contracts/safety.md`` Lesson 23 --
  the Halo2 L1 complexity ceiling (``P_CEILING``, ``W_CEILING``, ``O_CEILING``)

Nothing here re-implements Poseidon, Pedersen or halo2. The module records, for
every L1 circuit, the *shape* that the weekly note quotes numbers from:

* the ordered ``witness`` section and the ordered ``constrain_instance`` list,
  so public-input / witness-only counts can be compared with the Book's
  ceiling table;
* the preimage of the leaf (or coin) the circuit consumes/creates and of the
  nullifier it emits, so the *owner-binding* property can be checked
  structurally ("is the spender's secret part of what the leaf commits to?");
* the byte layout of the params structs that travel on-chain, so the
  "what does the wire carry in plaintext" claim is a sum, not an estimate.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum, IntEnum

# --------------------------------------------------------------------------------------
# constants
# --------------------------------------------------------------------------------------

#: Poseidon domain separators (``contract-wasm-type-system.md`` §A.9). Every
#: L1 circuit hard-codes these with ``witness_base(n)``.
DOMAIN = {
    1: "nullifier",
    2: "token commitment",
    3: "transaction binding",
    4: "commitment / coin",
    5: "merkle leaf",
    6: "user-data encryption",
    7: "signature secret (public key derivation)",
}

#: Halo2 L1 complexity ceiling -- ``privacy.md`` §6 / ``safety.md`` Lesson 23.
#: "Purse *is* the ceiling": the constants are the Purse Deposit/Withdraw counts.
P_CEILING = 9  # constrain_instance cells per operation
W_CEILING = 13  # witness-only values per operation
O_CEILING = 3  # state-transition operations per contract

#: ``MerklePath = [MerkleNode; 32]`` -- Orchard depth, fixed at compile time.
MERKLE_DEPTH = 32

#: zkas ``k`` declared by every L1 circuit (2^k rows).
K = 11

BASE = 32  # pallas::Base / MerkleNode / Nullifier ``to_repr()``
U32 = 4
U64 = 8
MERKLE_PATH_BYTES = MERKLE_DEPTH * BASE  # 1024


class Tier(str, Enum):
    SAFE = "safe"
    SCRUTINY = "scrutiny"
    EXCEEDS = "exceeds"


def triage_public_inputs(p: int) -> Tier:
    """Row 'Public inputs' of the Book's triage table (≤9 / 10–15 / >15)."""
    if p <= P_CEILING:
        return Tier.SAFE
    return Tier.SCRUTINY if p <= 15 else Tier.EXCEEDS


def triage_witnesses(w: int) -> Tier:
    """Row 'Witness values' of the Book's triage table (≤13 / 14–20 / >20)."""
    if w <= W_CEILING:
        return Tier.SAFE
    return Tier.SCRUTINY if w <= 20 else Tier.EXCEEDS


def triage_operations(o: int) -> Tier:
    """Row 'Operations' of the Book's triage table (≤3 / 4–6 / >6)."""
    if o <= O_CEILING:
        return Tier.SAFE
    return Tier.SCRUTINY if o <= 6 else Tier.EXCEEDS


# --------------------------------------------------------------------------------------
# function selectors (``src/contract/*/src/lib.rs``)
# --------------------------------------------------------------------------------------


class BoxFunction(IntEnum):
    Initialize = 0x00
    Put = 0x01
    Take = 0x02


class PurseFunction(IntEnum):
    Initialize = 0x00
    Deposit = 0x01
    Withdraw = 0x02
    Balance = 0x03


class PromissoryNoteFunction(IntEnum):
    """``src/contract/promissory_note/src/lib.rs`` -- note the order: Redeem is 0x01."""

    RegisterTypeV1 = 0x00
    RedeemV1 = 0x01
    IssueV1 = 0x02
    RevokeV1 = 0x03
    TransferV1 = 0x04
    OtcSwapV1 = 0x05


#: The older selector names that still appear in several Book chapters
#: (``arch/overview.md``, ``contract_invoke_api.md``, ``stablecoin.md``, ...).
#: They do not match the code; kept so the discrepancy can be asserted.
LEGACY_PN_FUNCTION_NAMES = {
    "TokenMintV1": 0x00,
    "MintV1": 0x01,
    "BurnV1": 0x02,
    "TransferV1": 0x03,
    "OtcSwapV1": 0x04,
}


# --------------------------------------------------------------------------------------
# circuits
# --------------------------------------------------------------------------------------


@dataclass(frozen=True)
class Circuit:
    contract: str
    name: str  # zkas namespace
    source: str  # path in the DarkWow tree
    witnesses: tuple[str, ...]  # the ``witness`` section, in slot order
    public_inputs: tuple[str, ...]  # ``constrain_instance`` calls, in order
    consumes: bool  # emits a nullifier
    creates: bool  # publishes a new leaf / coin
    #: preimage of the leaf (Box/Purse) or coin (PN) *after* the domain constant
    leaf: tuple[str, ...] | None
    #: preimage of the nullifier *after* the domain constant (None = read-only)
    nullifier: tuple[str, ...] | None
    #: the witness playing the "owner secret" role, and the leaf field (if any)
    #: that is derived from it
    owner_secret: str | None
    owner_field_in_leaf: str | None
    poseidon_calls: int
    ec_ops: int  # ec_mul_short + ec_mul + ec_add
    range_checks: int
    merkle_roots: int
    k: int = K

    @property
    def witness_only(self) -> int:
        return len(self.witnesses) - len(self.public_inputs)

    @property
    def leaf_binds_owner(self) -> bool:
        """Does the consumed/created leaf commit to the spender's secret?

        If not, ``nullifier = H(1, owner_secret, ...)`` is satisfiable with *any*
        ``owner_secret`` for the same leaf, and the leaf admits one distinct
        nullifier per distinct secret.
        """
        return self.owner_field_in_leaf is not None and self.leaf is not None and (
            self.owner_field_in_leaf in self.leaf
        )

    @property
    def max_nullifiers_per_leaf(self) -> int | None:
        """1 when the leaf pins its owner; ``None`` (unbounded) otherwise."""
        if not self.consumes:
            return 0
        return 1 if self.leaf_binds_owner else None

    @property
    def public_input_tier(self) -> Tier:
        return triage_public_inputs(len(self.public_inputs))

    @property
    def witness_tier(self) -> Tier:
        return triage_witnesses(self.witness_only)


_TX = ("tx_commitment", "tx_nonce", "tx_binding")

BOX_PUT = Circuit(
    contract="box",
    name="Put",
    source="src/contract/box/proof/put.zk",
    witnesses=(
        "box_id", "old_state_nonce", "new_state_nonce", "old_contents_commit",
        "new_contents_commit", "nullifier", "expected_root", "new_leaf",
        "owner_secret", "leaf_pos", "path", *_TX,
    ),
    public_inputs=("nullifier", "expected_root", "new_leaf", "tx_binding", "tx_nonce"),
    consumes=True,
    creates=True,
    leaf=("box_id", "old_contents_commit", "old_state_nonce"),
    nullifier=("owner_secret", "box_id", "old_state_nonce"),
    owner_secret="owner_secret",
    owner_field_in_leaf=None,
    poseidon_calls=4,
    ec_ops=0,
    range_checks=0,
    merkle_roots=1,
)

BOX_TAKE = Circuit(
    contract="box",
    name="Take",
    source="src/contract/box/proof/take.zk",
    witnesses=(
        "box_id", "contents_commit", "state_nonce", "nullifier", "expected_root",
        "owner_secret", "leaf_pos", "path", *_TX,
    ),
    public_inputs=("nullifier", "expected_root", "tx_binding", "tx_nonce"),
    consumes=True,
    creates=False,
    leaf=("box_id", "contents_commit", "state_nonce"),
    nullifier=("owner_secret", "box_id", "state_nonce"),
    owner_secret="owner_secret",
    owner_field_in_leaf=None,
    poseidon_calls=3,
    ec_ops=0,
    range_checks=0,
    merkle_roots=1,
)

_PURSE_RW_WITNESSES = (
    "purse_id", "old_balance", "old_balance_blind", "{amount}", "{amount}_blind",
    "new_balance", "new_balance_blind", "state_nonce", "nullifier", "expected_root",
    "new_leaf", "old_commit_x", "old_commit_y", "new_commit_x", "new_commit_y",
    "owner_secret", "owner_pub", "leaf_pos", "path", *_TX,
)
_PURSE_RW_PUBLIC = (
    "nullifier", "expected_root", "old_commit_x", "old_commit_y", "new_commit_x",
    "new_commit_y", "new_leaf", "tx_binding", "tx_nonce",
)

PURSE_DEPOSIT = Circuit(
    contract="purse",
    name="Deposit",
    source="src/contract/purse/proof/deposit.zk",
    witnesses=tuple(w.format(amount="deposit_amount") for w in _PURSE_RW_WITNESSES),
    public_inputs=_PURSE_RW_PUBLIC,
    consumes=True,
    creates=True,
    leaf=("purse_id", "old_balance", "state_nonce"),
    nullifier=("owner_secret", "purse_id", "state_nonce"),
    owner_secret="owner_secret",
    owner_field_in_leaf="owner_pub",  # exists as a witness -- but is not in the leaf
    poseidon_calls=5,
    ec_ops=10,
    range_checks=3,
    merkle_roots=1,
)

PURSE_WITHDRAW = Circuit(
    contract="purse",
    name="Withdraw",
    source="src/contract/purse/proof/withdraw.zk",
    witnesses=tuple(w.format(amount="withdraw_amount") for w in _PURSE_RW_WITNESSES),
    public_inputs=_PURSE_RW_PUBLIC,
    consumes=True,
    creates=True,
    leaf=("purse_id", "old_balance", "state_nonce"),
    nullifier=("owner_secret", "purse_id", "state_nonce"),
    owner_secret="owner_secret",
    owner_field_in_leaf="owner_pub",
    poseidon_calls=5,
    ec_ops=10,
    range_checks=3,
    merkle_roots=1,
)

PURSE_BALANCE = Circuit(
    contract="purse",
    name="Balance",
    source="src/contract/purse/proof/balance.zk",
    witnesses=(
        "purse_id", "asset_id", "balance", "balance_blind", "state_nonce",
        "derived_purse_id", "expected_root", "token_commit", "token_blind",
        "balance_commit_x", "balance_commit_y", "owner_secret", "owner_pub",
        "leaf_pos", "path", *_TX,
    ),
    public_inputs=(
        "derived_purse_id", "expected_root", "balance_commit_x", "balance_commit_y",
        "token_commit", "tx_binding", "tx_nonce",
    ),
    consumes=False,
    creates=False,
    leaf=("purse_id", "balance", "state_nonce"),
    nullifier=None,
    owner_secret="owner_secret",
    owner_field_in_leaf="owner_pub",
    poseidon_calls=5,
    ec_ops=3,
    range_checks=1,
    merkle_roots=1,
)

#: ``coin = H(4, pub, value, asset_id, coin_spend_hook, user_data, commitment_blind)``
_PN_COIN = ("pub", "value", "asset_id", "coin_spend_hook", "user_data", "commitment_blind")

PN_REGISTER_TYPE = Circuit(
    contract="promissory_note",
    name="RegisterType_V2",
    source="src/contract/promissory_note/proof/register_type.zk",
    witnesses=(
        "token_auth_parent", "token_user_data", "token_blind", "coin_public", "value",
        "coin_asset_id",  # declared but never read: the coin uses the derived asset_id
        "coin_spend_hook", "user_data", "commitment_blind", "value_blind", *_TX,
    ),
    public_inputs=(
        "asset_id", "token_auth_parent", "coin", "value_commit.x", "value_commit.y",
        "coin_spend_hook", "tx_binding", "tx_nonce",
    ),
    consumes=False,
    creates=True,
    leaf=_PN_COIN,
    nullifier=None,
    owner_secret=None,  # a mint: the recipient is `coin_public`, no spender
    owner_field_in_leaf="pub",
    poseidon_calls=3,
    ec_ops=3,
    range_checks=1,
    merkle_roots=0,
)

PN_ISSUE = Circuit(
    contract="promissory_note",
    name="Issue_V2",
    source="src/contract/promissory_note/proof/issue.zk",
    witnesses=(
        "backing_secret", "mint_public", "token_leaf_pos", "token_path", "coin_public",
        "value", "asset_id", "coin_spend_hook", "user_data", "commitment_blind",
        "value_blind", *_TX,
    ),
    public_inputs=(
        "token_root", "mint_public", "coin", "value_commit.x", "value_commit.y",
        "asset_id", "coin_spend_hook", "tx_binding", "tx_nonce",
    ),
    consumes=False,
    creates=True,
    leaf=_PN_COIN,
    nullifier=None,
    owner_secret="backing_secret",  # RC1-B: coin_public == mint_public == H(7, backing_secret)
    owner_field_in_leaf="pub",
    poseidon_calls=3,
    ec_ops=3,
    range_checks=1,
    merkle_roots=1,
)

PN_REVOKE = Circuit(
    contract="promissory_note",
    name="Revoke_V2",
    source="src/contract/promissory_note/proof/revoke.zk",
    witnesses=(
        "spend_secret", "value", "asset_id", "coin_spend_hook", "user_data",
        "commitment_blind", "value_blind", "asset_id_blind", "user_data_blind",
        "leaf_pos", "path", "signature_secret", *_TX,
    ),
    public_inputs=(
        "nullifier", "value_commit.x", "value_commit.y", "token_commit", "root",
        "user_data_enc", "coin_spend_hook", "signature_public", "tx_binding", "tx_nonce",
    ),
    consumes=True,
    creates=False,
    leaf=_PN_COIN,
    nullifier=("spend_secret", "coin"),
    owner_secret="spend_secret",
    owner_field_in_leaf="pub",  # pub = H(7, spend_secret) -- *is* in the coin
    poseidon_calls=8,
    ec_ops=3,
    range_checks=1,
    merkle_roots=1,
)

PN_TRANSFER = Circuit(
    contract="promissory_note",
    name="Transfer_V2",
    source="src/contract/promissory_note/proof/transfer.zk",
    witnesses=(
        "coin_public", "value", "asset_id", "coin_spend_hook", "user_data",
        "commitment_blind", "value_blind", "asset_id_blind", *_TX,
    ),
    public_inputs=(
        "coin", "value_commit.x", "value_commit.y", "token_commit", "coin_spend_hook",
        "tx_binding", "tx_nonce",
    ),
    consumes=False,
    creates=True,
    leaf=_PN_COIN,
    nullifier=None,
    owner_secret=None,
    owner_field_in_leaf="pub",
    poseidon_calls=3,
    ec_ops=3,
    range_checks=1,
    merkle_roots=0,
)

PN_REDEEM = Circuit(
    contract="promissory_note",
    name="Redeem_V2",
    source="src/contract/promissory_note/proof/redeem.zk",
    witnesses=(
        "coin_public", "value", "asset_id", "coin_spend_hook", "user_data",
        "commitment_blind", "value_blind", "asset_id_blind", *_TX,
    ),
    public_inputs=(
        "coin", "value_commit.x", "value_commit.y", "token_commit", "value",
        "tx_binding", "tx_nonce", "coin_spend_hook",
    ),
    consumes=False,
    creates=True,  # the zero-value receipt
    leaf=_PN_COIN,
    nullifier=None,
    owner_secret=None,
    owner_field_in_leaf="pub",
    poseidon_calls=3,
    ec_ops=3,
    range_checks=0,  # value is pinned to 0 instead: constrain_equal_base(value, ZERO)
    merkle_roots=0,
)

CIRCUITS: tuple[Circuit, ...] = (
    BOX_PUT, BOX_TAKE,
    PURSE_DEPOSIT, PURSE_WITHDRAW, PURSE_BALANCE,
    PN_REGISTER_TYPE, PN_ISSUE, PN_REVOKE, PN_TRANSFER, PN_REDEEM,
)

#: The Book's own table (PDF pp. 1491-1492; ``safety.md`` Lesson 23):
#: contract op -> (public inputs, witness-only values)
BOOK_CEILING_TABLE = {
    ("box", "Put"): (5, 9),
    ("box", "Take"): (4, 7),
    ("purse", "Deposit"): (9, 13),
    ("purse", "Withdraw"): (9, 13),
    ("purse", "Balance"): (7, 11),
}


def circuits_for(contract: str) -> tuple[Circuit, ...]:
    return tuple(c for c in CIRCUITS if c.contract == contract)


def operations(contract: str) -> int:
    """Number of proving operations a contract exposes (the ``O`` of the theorem)."""
    return len(circuits_for(contract))


def contract_tier(contract: str) -> Tier:
    """Worst tier over public inputs, witnesses and operation count."""
    order = [Tier.SAFE, Tier.SCRUTINY, Tier.EXCEEDS]
    tiers = [triage_operations(operations(contract))]
    for c in circuits_for(contract):
        tiers += [c.public_input_tier, c.witness_tier]
    return max(tiers, key=order.index)


# --------------------------------------------------------------------------------------
# wire formats (``src/contract/{box,purse}/src/model/mod.rs``)
# --------------------------------------------------------------------------------------


@dataclass(frozen=True)
class WireField:
    name: str
    size: int  # bytes; for the proof this is the 1-byte length prefix only
    #: True when the field is a private witness in the circuit (or unused by
    #: it) -- i.e. it is *only* on the wire because the params carry it.
    witness_only: bool = False
    note: str = ""


@dataclass(frozen=True)
class WireFormat:
    contract: str
    struct: str
    fields: tuple[WireField, ...]
    header_bytes: int  # the ``hdr`` constant in ``encode()``

    def encoded_size(self, proof_len: int = 0) -> int:
        """Total ``encode()`` length for a given ``proof`` payload length (≤ 255)."""
        if not 0 <= proof_len <= 255:
            raise ValueError("proof length is a single u8 on the wire")
        return sum(f.size for f in self.fields) + proof_len

    @property
    def plaintext_witness_fields(self) -> tuple[WireField, ...]:
        return tuple(f for f in self.fields if f.witness_only)


def _base(name: str, **kw) -> WireField:
    return WireField(name, BASE, **kw)


PUT_PARAMS = WireFormat(
    contract="box",
    struct="PutParams",
    header_bytes=260,
    fields=(
        _base("box_id", witness_only=True, note="the resource ID the Book says is 'never a public input'"),
        _base("old_state_nonce", witness_only=True),
        _base("new_state_nonce", witness_only=True),
        _base("old_contents_commit", witness_only=True),
        _base("new_contents_commit", witness_only=True),
        _base("nullifier"),
        _base("expected_root"),
        _base("new_leaf"),
        WireField("leaf_pos", U32, witness_only=True),
        WireField("merkle_path", MERKLE_PATH_BYTES, witness_only=True),
        WireField("proof", 1, note="u8 length prefix; the real proof travels in Transaction.proofs"),
        _base("tx_binding"),
        _base("tx_nonce"),
    ),
)

TAKE_PARAMS = WireFormat(
    contract="box",
    struct="TakeParams",
    header_bytes=164,
    fields=(
        _base("box_id", witness_only=True),
        _base("contents_commit", witness_only=True),
        _base("state_nonce", witness_only=True),
        _base("nullifier"),
        _base("expected_root"),
        WireField("leaf_pos", U32, witness_only=True),
        WireField("merkle_path", MERKLE_PATH_BYTES, witness_only=True),
        WireField("proof", 1),
        _base("tx_binding"),
        _base("tx_nonce"),
    ),
)

DEPOSIT_PARAMS = WireFormat(
    contract="purse",
    struct="DepositParams",
    header_bytes=316,
    fields=(
        _base("purse_id", witness_only=True),
        WireField("old_balance", U64, witness_only=True, note="u64 LE, plaintext"),
        WireField("deposit_amount", U64, witness_only=True, note="u64 LE, plaintext (withdraw_amount for WithdrawParams)"),
        WireField("new_balance", U64, witness_only=True, note="u64 LE, plaintext"),
        _base("state_nonce", witness_only=True),
        _base("nullifier"),
        _base("expected_root"),
        _base("new_leaf"),
        _base("old_commit_x"),
        _base("old_commit_y"),
        _base("new_commit_x"),
        _base("new_commit_y"),
        WireField("leaf_pos", U32, witness_only=True),
        WireField("merkle_path", MERKLE_PATH_BYTES, witness_only=True),
        WireField("proof", 1),
        _base("tx_binding"),
        _base("tx_nonce"),
        _base("asset_id", witness_only=True, note="not a witness of Deposit/Withdraw at all; unused by circuit, metadata and exec"),
    ),
)

#: ``WithdrawParams`` shares ``DepositParams``' layout byte for byte.
WITHDRAW_PARAMS = WireFormat("purse", "WithdrawParams", DEPOSIT_PARAMS.fields, 316)

BALANCE_PARAMS = WireFormat(
    contract="purse",
    struct="BalanceParams",
    header_bytes=268,
    fields=(
        _base("purse_id", witness_only=True),
        _base("asset_id", witness_only=True),
        WireField("balance", U64, witness_only=True, note="u64 LE, plaintext"),
        _base("state_nonce", witness_only=True),
        _base("derived_purse_id"),
        _base("expected_root"),
        _base("token_commit"),
        _base("balance_commit_x"),
        _base("balance_commit_y"),
        WireField("leaf_pos", U32, witness_only=True),
        WireField("merkle_path", MERKLE_PATH_BYTES, witness_only=True),
        WireField("proof", 1),
        _base("tx_binding"),
        _base("tx_nonce"),
    ),
)

WIRE_FORMATS: tuple[WireFormat, ...] = (
    PUT_PARAMS, TAKE_PARAMS, DEPOSIT_PARAMS, WITHDRAW_PARAMS, BALANCE_PARAMS,
)


def header_bytes(fmt: WireFormat) -> int:
    """Bytes before the merkle path -- what ``encode()`` calls ``hdr``."""
    total = 0
    for f in fmt.fields:
        if f.name == "merkle_path":
            return total
        total += f.size
    raise AssertionError("no merkle_path field")


def leaf_preimage_on_wire(fmt: WireFormat, circuit: Circuit) -> bool:
    """Is every field of the consumed leaf's preimage carried in plaintext?"""
    names = {f.name for f in fmt.fields}
    aliases = {"old_contents_commit": "contents_commit", "old_state_nonce": "state_nonce"}
    return all(x in names or aliases.get(x, x) in names for x in (circuit.leaf or ()))


# --------------------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------------------


def _table() -> str:
    rows = ["contract          circuit           k  slots  public  witness  P-tier    W-tier    owner-bound  nf/leaf"]
    for c in CIRCUITS:
        nf = {None: "unbounded", 0: "-", 1: "1"}[c.max_nullifiers_per_leaf]
        rows.append(
            f"{c.contract:17s} {c.name:16s} {c.k:2d} {len(c.witnesses):6d} {len(c.public_inputs):7d} "
            f"{c.witness_only:8d}  {c.public_input_tier.value:9s}{c.witness_tier.value:9s} "
            f"{str(c.leaf_binds_owner):12s} {nf}"
        )
    rows.append("")
    for name in ("box", "purse", "promissory_note"):
        rows.append(f"{name:17s} operations={operations(name)}  contract tier={contract_tier(name).value}")
    rows.append("")
    for w in WIRE_FORMATS:
        pt = ", ".join(f.name for f in w.plaintext_witness_fields if f.name not in ("leaf_pos", "merkle_path"))
        rows.append(f"{w.struct:16s} hdr={header_bytes(w):4d}  encoded={w.encoded_size():5d}+proof  plaintext witness: {pt}")
    return "\n".join(rows)


if __name__ == "__main__":
    print(_table())
