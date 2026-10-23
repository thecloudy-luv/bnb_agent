"""On-chain swap and execution engine with dry-run support."""

from dataclasses import dataclass, field
import logging
import time
from typing import Any
from eth_account import Account
from web3 import Web3
from agent.addresses import (
    BUSD,
    CAMPAIGN_WALLET,
    PANCAKESWAP_V2_ROUTER,
    WBNB,
)
from agent.chain import (
    ERC20_ABI,
    ROUTER_ABI,
    get_amounts_out,
    get_wallet_balances,
    get_web3,
)
from agent.strategy import Decision, decision_hash
from agent.txlock import tx_lock

logger = logging.getLogger(__name__)

GAS_RESERVE_BNB = 0.05
DEFAULT_SLIPPAGE = 0.01
SWAP_DEADLINE_SEC = 300


@dataclass(frozen=True)
class ExecResult:
    """Execution result container."""

    ok: bool
    tx_hash: str | None = None
    status: int | None = None
    gas_used: int | None = None
    error: str | None = None
    simulated: bool = False
    details: dict[str, Any] = field(default_factory=dict)


def execute(
    decision: Decision,
    private_key: str | None,
    rpc_url: str,
    dry_run: bool = True,
    slippage: float = DEFAULT_SLIPPAGE,
) -> ExecResult:
    """Execute or simulate a rebalance swap based on the Decision.

    Enforces:
    - Campaign wallet verification
    - Gas reserve check (>= 0.05 tBNB)
    - Exact ERC-20 approval
    - 32-byte decision hash appended to swap calldata
    - Serialized writes via TX_LOCK
    - Dry-run mode by default
    """
    if decision.action == "none":
        return ExecResult(
            ok=True,
            simulated=dry_run,
            details={"action": "none", "reason": decision.reason},
        )

    try:
        # 1. Resolve and verify campaign wallet
        if private_key:
            account = Account.from_key(private_key)
            account_address = Web3.to_checksum_address(account.address)
            if account_address != CAMPAIGN_WALLET:
                return ExecResult(
                    ok=False,
                    error=f"Signer {account.address} does not match campaign wallet {CAMPAIGN_WALLET}",
                    simulated=dry_run,
                )
        else:
            if not dry_run:
                return ExecResult(
                    ok=False,
                    error="PRIVATE_KEY is required for live execution",
                    simulated=dry_run,
                )
            account_address = CAMPAIGN_WALLET

        w3 = get_web3(rpc_url)

        # 2. Check native gas reserve
        balances = get_wallet_balances(w3, account_address)
        native_bnb = balances["native_bnb"]
        if native_bnb < GAS_RESERVE_BNB:
            return ExecResult(
                ok=False,
                error=(
                    f"Insufficient native tBNB gas reserve: {native_bnb:.4f} < {GAS_RESERVE_BNB}"
                ),
                simulated=dry_run,
            )

        # 3. Determine swap path
        if decision.action == "sell_wbnb":
            token_in = WBNB
            token_out = BUSD
        elif decision.action == "buy_wbnb":
            token_in = BUSD
            token_out = WBNB
        else:
            return ExecResult(
                ok=False,
                error=f"Unrecognized action: {decision.action}",
                simulated=dry_run,
            )

        path = [token_in, token_out]

        # 4. Calculate minimum amount out with slippage
        amounts_out = get_amounts_out(w3, decision.amount_in, path)
        expected_out = amounts_out[-1]
        amount_out_min = int(expected_out * (1.0 - slippage))
        deadline = int(time.time()) + SWAP_DEADLINE_SEC

        # 5. Check allowance
        token_contract = w3.eth.contract(address=token_in, abi=ERC20_ABI)
        raw_allowance = token_contract.functions.allowance(
            account_address, PANCAKESWAP_V2_ROUTER
        ).call()
        current_allowance = int(raw_allowance) if isinstance(raw_allowance, (int, str)) else 0

        needs_approval = current_allowance < decision.amount_in

        # 6. Build swap transaction with decision hash appended to calldata
        router = w3.eth.contract(address=PANCAKESWAP_V2_ROUTER, abi=ROUTER_ABI)
        base_tx_data = router.encode_abi(
            "swapExactTokensForTokens",
            args=[decision.amount_in, amount_out_min, path, account_address, deadline],
        )

        d_hash = decision_hash(decision)
        augmented_calldata = base_tx_data + d_hash.hex()

        planned_swap = {
            "to": PANCAKESWAP_V2_ROUTER,
            "from": account_address,
            "data": augmented_calldata,
            "value": 0,
            "token_in": token_in,
            "token_out": token_out,
            "amount_in": decision.amount_in,
            "amount_out_min": amount_out_min,
            "needs_approval": needs_approval,
            "decision_hash": "0x" + d_hash.hex(),
        }

        # Dry-run handling: do not sign or broadcast
        if dry_run:
            logger.info("[Dry Run] Swap planned: %s", planned_swap)
            return ExecResult(
                ok=True,
                status=1,
                simulated=True,
                details=planned_swap,
            )

        # Live execution protected by TX_LOCK
        assert private_key is not None
        with tx_lock():
            # Send exact approval if needed
            if needs_approval:
                approve_tx = token_contract.functions.approve(
                    PANCAKESWAP_V2_ROUTER, decision.amount_in
                ).build_transaction({
                    "from": account_address,
                    "nonce": w3.eth.get_transaction_count(account_address),
                    "gas": 100_000,
                    "gasPrice": w3.eth.gas_price,
                    "chainId": 97,
                })
                signed_approve = w3.eth.account.sign_transaction(approve_tx, private_key)
                app_hash = w3.eth.send_raw_transaction(signed_approve.raw_transaction)
                w3.eth.wait_for_transaction_receipt(app_hash, timeout=120)

            # Send swap transaction
            swap_tx = {
                "to": PANCAKESWAP_V2_ROUTER,
                "from": account_address,
                "data": augmented_calldata,
                "value": 0,
                "nonce": w3.eth.get_transaction_count(account_address),
                "gas": 300_000,
                "gasPrice": w3.eth.gas_price,
                "chainId": 97,
            }

            signed_swap = w3.eth.account.sign_transaction(swap_tx, private_key)
            tx_hash_bytes = w3.eth.send_raw_transaction(signed_swap.raw_transaction)
            receipt = w3.eth.wait_for_transaction_receipt(tx_hash_bytes, timeout=120)

            ok = receipt.status == 1
            return ExecResult(
                ok=ok,
                tx_hash=receipt.transactionHash.hex(),
                status=receipt.status,
                gas_used=receipt.gasUsed,
                error=None if ok else "Swap transaction reverted",
                simulated=False,
                details=planned_swap,
            )

    except Exception as exc:
        logger.error("Execution failed: %s", exc)
        return ExecResult(
            ok=False,
            error=str(exc),
            simulated=dry_run,
        )


def wrap_bnb(
    amount_wei: int,
    private_key: str | None,
    rpc_url: str,
    dry_run: bool = True,
) -> ExecResult:
    """Deposit native tBNB into WBNB contract."""
    try:
        if private_key:
            account = Account.from_key(private_key)
            account_address = Web3.to_checksum_address(account.address)
            if account_address != CAMPAIGN_WALLET:
                return ExecResult(
                    ok=False,
                    error=f"Signer {account.address} does not match campaign wallet {CAMPAIGN_WALLET}",
                    simulated=dry_run,
                )
        else:
            if not dry_run:
                return ExecResult(ok=False, error="PRIVATE_KEY required for live execution", simulated=dry_run)
            account_address = CAMPAIGN_WALLET

        w3 = get_web3(rpc_url)
        wbnb_contract = w3.eth.contract(address=WBNB, abi=ERC20_ABI)
        tx_dict = wbnb_contract.functions.deposit().build_transaction({
            "from": account_address,
            "value": amount_wei,
            "nonce": 0 if dry_run else w3.eth.get_transaction_count(account_address),
            "gas": 60_000,
            "gasPrice": 3_000_000_000,
            "chainId": 97,
        })

        if dry_run:
            return ExecResult(
                ok=True,
                simulated=True,
                details={"action": "deposit_wbnb", "amount_wei": amount_wei, "tx": tx_dict},
            )

        assert private_key is not None
        with tx_lock():
            tx_dict["nonce"] = w3.eth.get_transaction_count(account_address)
            tx_dict["gasPrice"] = w3.eth.gas_price
            signed = w3.eth.account.sign_transaction(tx_dict, private_key)
            tx_hash = w3.eth.send_raw_transaction(signed.raw_transaction)
            receipt = w3.eth.wait_for_transaction_receipt(tx_hash, timeout=120)
            ok = receipt.status == 1
            return ExecResult(
                ok=ok,
                tx_hash=receipt.transactionHash.hex(),
                status=receipt.status,
                gas_used=receipt.gasUsed,
                error=None if ok else "WBNB deposit reverted",
                simulated=False,
            )
    except Exception as exc:
        return ExecResult(ok=False, error=str(exc), simulated=dry_run)
