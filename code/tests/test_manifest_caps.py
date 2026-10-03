"""Claims in weeks/week-02/README.md §6 (BUG-04): the manifest, the trust layers and
capability aliasing."""

import pytest

from darkwow_research import manifest_caps as mc


# --------------------------------------------------------------------------------------
# §6.1 -- the 32 manifests
# --------------------------------------------------------------------------------------


def test_thirty_two_manifests_and_their_totals():
    t = mc.totals()
    assert t["manifests"] == 32
    assert t["functions"] == 242 and t["requires_proof"] == 168
    assert t["capabilities"] == 54 and t["actions"] == 32
    assert t["with_actions"] == 9 and t["with_parameters"] == 3


def test_eight_of_thirty_two_manifests_declare_typed_capability_fields():
    assert mc.typed_coverage() == (8, 32)
    typed = sorted(m.contract for m in mc.MANIFESTS if m.typed)
    assert typed == ["attestation", "box", "deployooor", "multisig", "native_token", "oracle",
                     "promissory_note", "purse"]


def test_the_typed_eight_are_genesis_contracts_except_native_token_is_not_a_governance_primitive():
    typed = {m.contract for m in mc.MANIFESTS if m.typed}
    assert typed - set(mc.GENESIS_CONTRACTS) == set()
    assert set(mc.GENESIS_CONTRACTS) - typed == {"identity"}


def test_capability_name_collisions():
    assert sum(len(v) for v in mc.SHARED_CAPABILITY_NAMES.values()) == 17
    assert mc.SHARED_CAPABILITY_NAMES["creator"] == ("dao_escrow", "darkbet_exchange", "escrow")
    assert len(mc.SHARED_CAPABILITY_NAMES["player"]) == 5
    assert mc.TOTAL_CAPABILITY_DECLARATIONS == 54 and mc.DISTINCT_CAPABILITY_NAMES == 43


def test_shared_names_agree_with_the_per_manifest_lists():
    for name, owners in mc.SHARED_CAPABILITY_NAMES.items():
        assert tuple(m.contract for m in mc.MANIFESTS if name in m.cap_names) == owners


def test_dao_escrow_manifest_row():
    m = mc.manifest("dao_escrow")
    assert (m.functions, m.requires_proof, m.capabilities) == (10, 6, 3)
    assert m.cap_names == ("creator", "governance_group", "member")
    assert not m.typed


# --------------------------------------------------------------------------------------
# §6.2 -- trust layers
# --------------------------------------------------------------------------------------


def test_only_two_trust_tiers_are_reachable_from_contract_show():
    assert mc.resolve_show_trust("purse") is mc.TrustTier.GENESIS
    assert mc.resolve_show_trust("dao_escrow") is mc.TrustTier.UNVERIFIED
    assert mc.resolve_show_trust("escrow") is mc.TrustTier.UNVERIFIED
    reachable = {mc.resolve_show_trust(c) for c in [m.contract for m in mc.MANIFESTS]}
    assert reachable == {mc.TrustTier.GENESIS, mc.TrustTier.UNVERIFIED}


def test_nine_genesis_contracts():
    assert len(mc.GENESIS_CONTRACTS) == 9


def test_trust_layers_one_partial_two_absent():
    assert [l.implemented for l in mc.TRUST_LAYERS] == ["partial", "no", "no"]
    assert "not implemented" in mc.TRUST_LAYERS[1].where


def test_tier_display_strings_match_the_sdk():
    assert [t.value for t in mc.TrustTier] == ["GENESIS", "OWN", "ATTESTED", "UNVERIFIED"]


# --------------------------------------------------------------------------------------
# §6.3 -- aliasing
# --------------------------------------------------------------------------------------


def test_manifest_prefix_and_parse():
    assert mc.MANIFEST_PREFIX == 0x4D == ord("M")
    assert mc.parse_deploy_ix(b"M[contract]\nname='x'") == "[contract]\nname='x'"
    assert mc.parse_deploy_ix(b"") is None
    assert mc.parse_deploy_ix(b"\x00abc") is None


def test_relabelled_selector_is_not_caught_by_the_described_wasm_check():
    spoof = mc.Manifest("looks_like_identity", (
        mc.ManifestFunction("identity_verification", 0x02, True),
        mc.ManifestFunction("nonexistent", 0x09, True),
    ))
    truth = {0x00: "Initialize", 0x01: "Deposit", 0x02: "Withdraw", 0x03: "Balance"}
    findings = mc.alias(spoof, truth)
    by_name = {f.name: f for f in findings}
    assert by_name["identity_verification"].true_name == "Withdraw"
    assert by_name["identity_verification"].caught_by_layer2 is False
    assert by_name["nonexistent"].caught_by_layer2 is True


def test_honest_manifest_has_no_alias_findings():
    m = mc.Manifest("purse", tuple(mc.ManifestFunction(n, c) for c, n in
                                  [(0, "Initialize"), (1, "Deposit"), (2, "Withdraw"), (3, "Balance")]))
    assert mc.alias(m, {0: "Initialize", 1: "Deposit", 2: "Withdraw", 3: "Balance"}) == []


def test_manifest_strings_are_not_among_the_things_the_chain_dispatches_on():
    chain = " ".join(mc.what_the_chain_dispatches_on()).lower()
    assert "manifest" not in chain and "name" not in chain
    assert any("display names" in s for s in mc.what_the_manifest_controls())


@pytest.mark.parametrize("contract", ["box", "purse", "multisig", "oracle", "attestation"])
def test_governance_primitive_manifests_are_typed(contract):
    assert mc.manifest(contract).typed


def test_identity_manifest_declares_no_capabilities_at_all():
    assert mc.manifest("identity").capabilities == 0 and not mc.manifest("identity").typed
