"""Tests for on-chain executor with mocks and dry-run verification."""

from unittest.mock import MagicMock, patch
from eth_account import Account
import pytest
from web3 import Web3
from agent.addresses import CAMPAIGN_WALLET, PANCAKESWAP_V2_ROUTER
from agent.executor import execute, wrap_bnb
from agent.strategy import Decision, decision_hash


@pytest.fixture
def dummy_decision() -> Decision:
    return Decision(
        action="sell_wbnb",
        amount_in=1000000000000000000,  # 1 WBNB
        reason="test rebalance",
        inputs={"test": 1},
    )


def test_reject_unauthorized_wallet(dummy_decision: Decision) -> None:
    # A random wallet that does not match CAMPAIGN_WALLET
    random_account = Account.create()
    res = execute(dummy_decision, random_account.key.hex(), "http://localhost:8545", dry_run=True)
    assert res.ok is False
    assert "does not match campaign wallet" in str(res.error)


def test_gas_reserve_blocks_execution(dummy_decision: Decision) -> None:
    mock_w3 = MagicMock()
    mock_w3.is_connected.return_value = True
    mock_w3.eth.chain_id = 97

    with patch("agent.executor.get_web3", return_value=mock_w3), \
         patch("agent.executor.get_wallet_balances", return_value={"native_bnb": 0.01, "wbnb": 1.0, "busd": 100.0}), \
         patch("eth_account.Account.from_key") as mock_from_key:
        mock_acc = MagicMock()
        mock_acc.address = CAMPAIGN_WALLET
        mock_from_key.return_value = mock_acc

        res = execute(dummy_decision, "0x" + "11" * 32, "http://localhost:8545", dry_run=True)
        assert res.ok is False
        assert "Insufficient native tBNB gas reserve" in str(res.error)


def test_dry_run_does_not_send_transaction(dummy_decision: Decision) -> None:
    mock_w3 = MagicMock()
    mock_w3.is_connected.return_value = True
    mock_w3.eth.chain_id = 97

    # Mock contract allowance
    mock_token = MagicMock()
    mock_token.functions.allowance.return_value.call.return_value = 0

    mock_router = MagicMock()
    mock_router.encode_abi.return_value = "0x38ed1739" + "00" * 128

    def contract_side_effect(address, abi):
        if Web3.to_checksum_address(address) == PANCAKESWAP_V2_ROUTER:
            return mock_router
        return mock_token

    mock_w3.eth.contract.side_effect = contract_side_effect

    with patch("agent.executor.get_web3", return_value=mock_w3), \
         patch("agent.executor.get_wallet_balances", return_value={"native_bnb": 0.5, "wbnb": 1.0, "busd": 100.0}), \
         patch("agent.executor.get_amounts_out", return_value=[10**18, 400 * 10**18]), \
         patch("eth_account.Account.from_key") as mock_from_key:
        mock_acc = MagicMock()
        mock_acc.address = CAMPAIGN_WALLET
        mock_from_key.return_value = mock_acc

        res = execute(dummy_decision, "0x" + "11" * 32, "http://localhost:8545", dry_run=True)
        assert res.ok is True
        assert res.simulated is True
        # Verify send_raw_transaction was NEVER called
        mock_w3.eth.send_raw_transaction.assert_not_called()

        # Check calldata ends with decision hash
        details = res.details
        d_hash = decision_hash(dummy_decision).hex()
        assert details["data"].endswith(d_hash)
        assert details["decision_hash"] == "0x" + d_hash

        # Check slippage 1% (400 * 0.99 = 396)
        expected_min = int(400 * 10**18 * 0.99)
        assert details["amount_out_min"] == expected_min


def test_live_execution_uses_tx_lock_and_exact_approval(dummy_decision: Decision) -> None:
    mock_w3 = MagicMock()
    mock_w3.is_connected.return_value = True
    mock_w3.eth.chain_id = 97
    mock_w3.eth.get_transaction_count.return_value = 5
    mock_w3.eth.gas_price = 3000000000

    # Mock receipt
    mock_receipt = MagicMock()
    mock_receipt.status = 1
    mock_receipt.transactionHash.hex.return_value = "0xabc123"
    mock_receipt.gasUsed = 150000
    mock_w3.eth.wait_for_transaction_receipt.return_value = mock_receipt

    # Mock contract for token_in
    mock_token = MagicMock()
    mock_token.functions.allowance.return_value.call.return_value = 0
    mock_token.functions.approve.return_value.build_transaction.return_value = {"to": "0xToken", "data": "0x"}

    # Mock router
    mock_router = MagicMock()
    mock_router.encode_abi.return_value = "0x38ed1739" + "00" * 128

    def contract_side_effect(address, abi):
        if Web3.to_checksum_address(address) == PANCAKESWAP_V2_ROUTER:
            return mock_router
        return mock_token

    mock_w3.eth.contract.side_effect = contract_side_effect

    with patch("agent.executor.get_web3", return_value=mock_w3), \
         patch("agent.executor.get_wallet_balances", return_value={"native_bnb": 0.5, "wbnb": 1.0, "busd": 100.0}), \
         patch("agent.executor.get_amounts_out", return_value=[10**18, 400 * 10**18]), \
         patch("eth_account.Account.from_key") as mock_from_key:
        mock_acc = MagicMock()
        mock_acc.address = CAMPAIGN_WALLET
        mock_from_key.return_value = mock_acc

        res = execute(dummy_decision, "0x" + "11" * 32, "http://localhost:8545", dry_run=False)
        assert res.ok is True
        assert res.simulated is False
        assert res.tx_hash == "0xabc123"

        # Verify exact approval was requested for decision.amount_in (1 WBNB)
        mock_token.functions.approve.assert_called_with(PANCAKESWAP_V2_ROUTER, dummy_decision.amount_in)


def test_wrap_bnb_unauthorized_wallet() -> None:
    random_account = Account.create()
    res = wrap_bnb(10**18, random_account.key.hex(), "http://localhost:8545", dry_run=True)
    assert res.ok is False
    assert "does not match campaign wallet" in str(res.error)
