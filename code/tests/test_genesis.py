from darkwow_research import genesis as g


def test_exactly_nine_genesis_contracts():
    assert len(g.GENESIS_CONTRACTS) == 9


def test_counters_are_2_through_10_with_none_skipped():
    assert sorted(c.counter for c in g.GENESIS_CONTRACTS) == list(range(2, 11))


def test_only_deployooor_and_native_token_are_consensus_critical():
    assert [c.name for c in g.consensus_critical()] == ["Deployooor", "NativeToken"]
    assert len(g.ecosystem()) == 7


def test_deployment_order_matches_genesis_contracts_table():
    # build_genesis_deployment_txs(): Deployooor, NativeToken, PromissoryNote, Identity,
    # Oracle, Attestation, Purse, Box, MultiSig -- positions 1..=9 of block 1.
    assert [c.name for c in g.GENESIS_CONTRACTS] == [
        "Deployooor", "NativeToken", "PromissoryNote", "Identity", "Oracle",
        "Attestation", "Purse", "Box", "MultiSig",
    ]
    assert [c.genesis_position for c in g.GENESIS_CONTRACTS] == list(range(1, 10))


def test_derivation_string_uses_prefix_42_and_zero_x():
    assert g.by_counter(4).derivation == "poseidon_hash([42, 0, 4])"
    assert g.by_counter(10).name == "MultiSig"


def test_genesis_block_carries_ten_transactions():
    assert g.GENESIS_HEADER["transactions"] == 10
    assert g.GENESIS_HEADER["height"] == 1
    assert g.GENESIS_HEADER["timestamp"] == 0
