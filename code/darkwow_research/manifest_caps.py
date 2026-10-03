"""The contract manifest (``manifest.toml``) as the wallet sees it, and what a
spoofed one can and cannot do (BUG-04).

Transcribed from ``src/sdk/src/manifest.rs``, ``doc/src/arch/manifest.md``,
``bin/dww/src/{dispatch,manifest_resolver}.rs`` and the 32 ``manifest.toml``
files at ``d775e37c``.

What the chain knows about a manifest: nothing.  It is TOML carried in the
``ix`` bytes of ``DeployParamsV1`` behind a ``0x4D`` ('M') prefix, stored
unencrypted, never hashed on-chain ("On-chain manifest hash: Pending").  The
node dispatches on ``data[0]`` -- a ``u8`` selector -- and on a 32-byte
``ContractId``; the manifest's ``name`` strings are for wallets and humans.

What the wallet does with it: parse, store in SQLite, answer ``contract show``
and ``contract invoke`` by *name* (``ManifestResolver::get_function(name)``,
``get_capability(name)``), and print a trust tier.  Of the three-layer trust
model the Book describes, layer 1 (tier) distinguishes only GENESIS from
UNVERIFIED today, layer 2 (WASM-vs-manifest) prints "not implemented", and
layer 3 (attestations) is "deferred".
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

MANIFEST_PREFIX = 0x4D  # ASCII 'M'


@dataclass(frozen=True)
class ManifestFunction:
    name: str
    code: int
    requires_proof: bool = False
    proof_circuit: str | None = None


@dataclass(frozen=True)
class ManifestCapability:
    discriminant: int
    name: str
    primitives: tuple[str, ...] = ()     # typed field; closed vocabulary (type-system.md §8.1)
    note_schema: tuple[str, ...] = ()    # typed field; the wallet's tier selector

    @property
    def typed(self) -> bool:
        return bool(self.primitives) or bool(self.note_schema)


@dataclass(frozen=True)
class Manifest:
    name: str
    functions: tuple[ManifestFunction, ...]
    capabilities: tuple[ManifestCapability, ...] = ()
    dependencies: tuple[str, ...] = ()

    def function_by_name(self, name: str) -> ManifestFunction | None:
        return next((f for f in self.functions if f.name == name), None)

    def function_by_code(self, code: int) -> ManifestFunction | None:
        return next((f for f in self.functions if f.code == code), None)


def parse_deploy_ix(ix: bytes) -> str | None:
    """``ContractManifest::from_deploy_ix``: 'M' + UTF-8 TOML, else treated as absent."""
    if not ix or ix[0] != MANIFEST_PREFIX:
        return None
    try:
        return ix[1:].decode("utf-8")
    except UnicodeDecodeError:
        return None


# --------------------------------------------------------------------------------------
# trust model
# --------------------------------------------------------------------------------------


class TrustTier(str, Enum):
    GENESIS = "GENESIS"
    SELF_DEPLOYED = "OWN"
    ATTESTED = "ATTESTED"
    UNVERIFIED = "UNVERIFIED"


GENESIS_CONTRACTS = ("native_token", "deployooor", "promissory_note", "identity", "oracle",
                     "attestation", "purse", "box", "multisig")


def resolve_show_trust(contract: str) -> TrustTier:
    """``bin/dww/src/dispatch.rs::resolve_show_trust`` -- only two outcomes are reachable."""
    return TrustTier.GENESIS if contract in GENESIS_CONTRACTS else TrustTier.UNVERIFIED


@dataclass(frozen=True)
class TrustLayer:
    n: int
    name: str
    described_as: str
    implemented: str      # "yes" / "partial" / "no"
    where: str


TRUST_LAYERS: tuple[TrustLayer, ...] = (
    TrustLayer(1, "Trust tier", "GENESIS / OWN / ATTESTED / UNVERIFIED by deployer", "partial",
               "dispatch.rs resolve_show_trust: GENESIS else UNVERIFIED; OWN and ATTESTED deferred"),
    TrustLayer(2, "WASM verification", "exports and circuit names compared against the manifest", "no",
               "dispatch.rs prints 'WASM verification: not implemented (WASM binary is not stored locally)'"),
    TrustLayer(3, "Attestation", "issuers vouch on-chain via the Attestation contract", "no",
               "attestations_json column exists; 'requires on-chain Attestation contract query'"),
)


# --------------------------------------------------------------------------------------
# aliasing: what a spoofed manifest changes, and what it cannot
# --------------------------------------------------------------------------------------


@dataclass(frozen=True)
class AliasFinding:
    name: str
    code: int
    true_name: str
    caught_by_layer2: bool   # would the described WASM check notice?


def alias(manifest: Manifest, truth: dict[int, str]) -> list[AliasFinding]:
    """Compare manifest function names against the contract's real selector table.

    Layer 2, as *described*, compares exported function names and circuit namespaces
    against the manifest -- it would catch a name that is not exported at all, but a
    manifest that relabels an existing selector with a benign name is a mismatch in
    *meaning*, which no mechanical check sees ("sophisticated deception where the WASM
    exports the claimed function but it doesn't do what the name implies", manifest.md).
    """
    out = []
    for f in manifest.functions:
        true = truth.get(f.code)
        if true is None:
            out.append(AliasFinding(f.name, f.code, "<no such selector>", True))
        elif true != f.name:
            out.append(AliasFinding(f.name, f.code, true, False))
    return out


def what_the_chain_dispatches_on() -> tuple[str, ...]:
    return ("ContractId (32 bytes, Poseidon-derived)", "data[0] selector (u8)",
            "children_indexes / parent_index (DarkTree)", "ZK proof public inputs from metadata()")


def what_the_manifest_controls() -> tuple[str, ...]:
    return ("display names of functions and capabilities", "CLI parameter validation",
            "which witness slots the generic prover fills from the note (witness / off_wire tags)",
            "cost-profile baselines", "trust-tier label text")


# --------------------------------------------------------------------------------------
# the 32 shipped manifests (counts from tomllib over src/contract/*/manifest.toml)
# --------------------------------------------------------------------------------------


@dataclass(frozen=True)
class ManifestStats:
    contract: str
    functions: int
    requires_proof: int
    capabilities: int
    actions: int
    parameters: int
    circuits: int
    trees: int
    typed: bool            # declares [[capabilities]].primitives / note_schema
    cap_names: tuple[str, ...] = field(default=())


_M = ManifestStats
MANIFESTS: tuple[ManifestStats, ...] = (
    _M("attestation", 14, 10, 3, 5, 0, 10, 6, True, ('attestation', 'claim', 'delegation')),
    _M("auction", 6, 6, 3, 0, 0, 6, 4, False, ('seller', 'bidder_active', 'bidder_outbid')),
    _M("baccarat", 5, 4, 2, 0, 0, 4, 4, False, ('player', 'banker')),
    _M("bearer_bond", 9, 6, 1, 0, 0, 4, 7, False, ('bond_holder',)),
    _M("betting_stake", 5, 5, 1, 0, 0, 5, 4, False, ('staker',)),
    _M("box", 3, 2, 1, 2, 2, 2, 3, True, ('box_capability',)),
    _M("bridge", 3, 2, 0, 0, 0, 2, 4, False, ()),
    _M("dao_escrow", 10, 6, 3, 0, 0, 5, 6, False, ('creator', 'governance_group', 'member')),
    _M("darkbet_exchange", 11, 10, 5, 0, 0, 10, 8, False, ('creator', 'backer', 'layer', 'lp_provider', 'oracle')),
    _M("darktoshi_dice", 5, 4, 2, 0, 0, 4, 4, False, ('player', 'house')),
    _M("deployooor", 2, 0, 1, 2, 0, 0, 2, True, ('deployment_right',)),
    _M("dex", 9, 8, 2, 3, 0, 8, 4, False, ('proposer', 'acceptor')),
    _M("drain_protection", 9, 9, 1, 0, 0, 9, 7, False, ('fund_owner',)),
    _M("escrow", 6, 5, 2, 0, 0, 5, 4, False, ('creator', 'counterparty')),
    _M("game_room", 12, 12, 2, 0, 0, 12, 7, False, ('host', 'player')),
    _M("identity", 8, 2, 0, 0, 0, 2, 6, False, ()),
    _M("insurance_market", 16, 4, 0, 0, 0, 4, 7, False, ()),
    _M("labor_market", 15, 10, 0, 0, 0, 11, 4, False, ()),
    _M("lottery", 6, 2, 2, 0, 0, 5, 7, False, ('operator', 'ticket_holder')),
    _M("multisig", 4, 3, 3, 3, 0, 3, 3, True, ('group_membership', 'partial_signature', 'approval')),
    _M("native_token", 8, 4, 1, 3, 0, 3, 7, True, ('commitment',)),
    _M("oracle", 6, 6, 5, 5, 0, 6, 3, True, ('oracle_registration', 'oracle_value', 'attestation', 'aggregate', 'value_commitment')),
    _M("otc_swap", 5, 4, 2, 0, 0, 4, 3, False, ('proposer', 'acceptor')),
    _M("pool_stake", 9, 4, 1, 0, 0, 4, 5, False, ('pool_staker',)),
    _M("promissory_note", 6, 6, 3, 6, 6, 5, 7, True, ('note', 'mint_authority', 'receipt')),
    _M("purse", 4, 3, 1, 3, 3, 3, 3, True, ('purse_capability',)),
    _M("relayer_endowment", 8, 3, 2, 0, 0, 3, 4, False, ('relayer', 'backer_endowment')),
    _M("roulette", 5, 4, 2, 0, 0, 4, 5, False, ('player', 'house')),
    _M("slot", 5, 3, 2, 0, 0, 3, 5, False, ('player', 'house')),
    _M("stablecoin", 12, 11, 0, 0, 0, 11, 7, False, ()),
    _M("subscription", 7, 5, 1, 0, 0, 5, 4, False, ('subscriber',)),
    _M("tender", 9, 5, 0, 0, 0, 5, 4, False, ()),
)

# capability names that appear in more than one manifest (exact strings, tomllib)
SHARED_CAPABILITY_NAMES: dict[str, tuple[str, ...]] = {
    "player": ("baccarat", "darktoshi_dice", "game_room", "roulette", "slot"),
    "creator": ("dao_escrow", "darkbet_exchange", "escrow"),
    "house": ("darktoshi_dice", "roulette", "slot"),
    "attestation": ("attestation", "oracle"),
    "proposer": ("dex", "otc_swap"),
    "acceptor": ("dex", "otc_swap"),
}
TOTAL_CAPABILITY_DECLARATIONS = 54
DISTINCT_CAPABILITY_NAMES = 43


def manifest(contract: str) -> ManifestStats:
    for m in MANIFESTS:
        if m.contract == contract:
            return m
    raise KeyError(contract)


def typed_coverage() -> tuple[int, int]:
    """(manifests declaring typed capability fields, total manifests)."""
    return sum(m.typed for m in MANIFESTS), len(MANIFESTS)


def totals() -> dict[str, int]:
    return {
        "manifests": len(MANIFESTS),
        "functions": sum(m.functions for m in MANIFESTS),
        "requires_proof": sum(m.requires_proof for m in MANIFESTS),
        "capabilities": sum(m.capabilities for m in MANIFESTS),
        "actions": sum(m.actions for m in MANIFESTS),
        "with_actions": sum(m.actions > 0 for m in MANIFESTS),
        "with_parameters": sum(m.parameters > 0 for m in MANIFESTS),
        "circuits": sum(m.circuits for m in MANIFESTS),
        "trees": sum(m.trees for m in MANIFESTS),
    }


def _main() -> None:  # pragma: no cover
    print("totals:", totals())
    print("typed capability fields:", "%d/%d" % typed_coverage())
    print("shared names:", {k: len(v) for k, v in SHARED_CAPABILITY_NAMES.items()})
    spoof = Manifest("not_a_purse", (ManifestFunction("identity_verification", 0x02, True, "Withdraw"),
                                     ManifestFunction("audit_log", 0x01, True, "Deposit")))
    truth = {0x00: "Initialize", 0x01: "Deposit", 0x02: "Withdraw", 0x03: "Balance"}
    for a in alias(spoof, truth):
        print(f"  '{a.name}' -> 0x{a.code:02x} is really {a.true_name}; layer-2 catches: {a.caught_by_layer2}")
    for layer in TRUST_LAYERS:
        print(f"  L{layer.n} {layer.name:18s} implemented={layer.implemented}")


if __name__ == "__main__":  # pragma: no cover
    _main()
