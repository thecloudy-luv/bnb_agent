"""Web3 chain reader and contract interface on BSC Testnet."""

import logging
from typing import Any
from web3 import Web3
from web3.middleware import ExtraDataToPOAMiddleware
from agent.addresses import (
    BUSD,
    PAIR_WBNB_BUSD,
    PANCAKESWAP_V2_ROUTER,
    WBNB,
)

logger = logging.getLogger(__name__)

ERC20_ABI = [
    {
        "constant": True,
        "inputs": [{"name": "_owner", "type": "address"}],
        "name": "balanceOf",
        "outputs": [{"name": "balance", "type": "uint256"}],
        "type": "function",
    },
    {
        "constant": True,
        "inputs": [
            {"name": "_owner", "type": "address"},
            {"name": "_spender", "type": "address"},
        ],
        "name": "allowance",
        "outputs": [{"name": "", "type": "uint256"}],
        "type": "function",
    },
    {
        "constant": False,
        "inputs": [
            {"name": "_spender", "type": "address"},
            {"name": "_value", "type": "uint256"},
        ],
        "name": "approve",
        "outputs": [{"name": "", "type": "bool"}],
        "type": "function",
    },
    {
        "constant": True,
        "inputs": [],
        "name": "decimals",
        "outputs": [{"name": "", "type": "uint8"}],
        "type": "function",
    },
    {
        "constant": False,
        "inputs": [],
        "name": "deposit",
        "outputs": [],
        "payable": True,
        "stateMutability": "payable",
        "type": "function",
    },
    {
        "constant": False,
        "inputs": [{"name": "wad", "type": "uint256"}],
        "name": "withdraw",
        "outputs": [],
        "type": "function",
    },
]

PAIR_ABI = [
    {
        "constant": True,
        "inputs": [],
        "name": "getReserves",
        "outputs": [
            {"name": "_reserve0", "type": "uint112"},
            {"name": "_reserve1", "type": "uint112"},
            {"name": "_blockTimestampLast", "type": "uint32"},
        ],
        "type": "function",
    },
    {
        "constant": True,
        "inputs": [],
        "name": "token0",
        "outputs": [{"name": "", "type": "address"}],
        "type": "function",
    },
    {
        "constant": True,
        "inputs": [],
        "name": "token1",
        "outputs": [{"name": "", "type": "address"}],
        "type": "function",
    },
]

ROUTER_ABI = [
    {
        "constant": True,
        "inputs": [
            {"name": "amountIn", "type": "uint256"},
            {"name": "path", "type": "address[]"},
        ],
        "name": "getAmountsOut",
        "outputs": [{"name": "amounts", "type": "uint256[]"}],
        "type": "function",
    },
    {
        "constant": False,
        "inputs": [
            {"name": "amountIn", "type": "uint256"},
            {"name": "amountOutMin", "type": "uint256"},
            {"name": "path", "type": "address[]"},
            {"name": "to", "type": "address"},
            {"name": "deadline", "type": "uint256"},
        ],
        "name": "swapExactTokensForTokens",
        "outputs": [{"name": "amounts", "type": "uint256[]"}],
        "type": "function",
    },
]


def get_web3(rpc_url: str) -> Web3:
    """Create Web3 connection and verify BSC Testnet (chain ID 97)."""
    w3 = Web3(Web3.HTTPProvider(rpc_url))
    w3.middleware_onion.inject(ExtraDataToPOAMiddleware, layer=0)
    if not w3.is_connected():
        raise ConnectionError(f"Cannot connect to RPC: {rpc_url}")
    chain_id = w3.eth.chain_id
    if chain_id != 97:
        raise ValueError(f"Expected BSC Testnet (chain 97), got chain {chain_id}")
    return w3


def get_wallet_balances(w3: Web3, address: str) -> dict[str, float]:
    """Retrieve native tBNB, WBNB, and BUSD balances in human units."""
    chk_addr = Web3.to_checksum_address(address)

    # Native tBNB
    native_wei = w3.eth.get_balance(chk_addr)
    native_bnb = float(Web3.from_wei(native_wei, "ether"))

    # WBNB
    wbnb_contract = w3.eth.contract(address=WBNB, abi=ERC20_ABI)
    wbnb_raw = wbnb_contract.functions.balanceOf(chk_addr).call()
    wbnb = float(Web3.from_wei(wbnb_raw, "ether"))

    # BUSD
    busd_contract = w3.eth.contract(address=BUSD, abi=ERC20_ABI)
    busd_raw = busd_contract.functions.balanceOf(chk_addr).call()
    busd = float(Web3.from_wei(busd_raw, "ether"))

    return {
        "native_bnb": native_bnb,
        "wbnb": wbnb,
        "busd": busd,
        "native_wei": native_wei,
        "wbnb_wei": wbnb_raw,
        "busd_wei": busd_raw,
    }


def get_pair_reserves(w3: Web3) -> dict[str, float]:
    """Fetch WBNB/BUSD pool reserves from the PancakeSwap V2 pair contract."""
    pair_contract = w3.eth.contract(address=PAIR_WBNB_BUSD, abi=PAIR_ABI)
    reserves = pair_contract.functions.getReserves().call()
    token0 = pair_contract.functions.token0().call()

    r0 = reserves[0]
    r1 = reserves[1]

    if Web3.to_checksum_address(token0) == WBNB:
        reserve_wbnb_raw, reserve_busd_raw = r0, r1
    else:
        reserve_wbnb_raw, reserve_busd_raw = r1, r0

    reserve_wbnb = float(Web3.from_wei(reserve_wbnb_raw, "ether"))
    reserve_busd = float(Web3.from_wei(reserve_busd_raw, "ether"))

    return {
        "reserve_wbnb": reserve_wbnb,
        "reserve_busd": reserve_busd,
        "reserve_wbnb_raw": reserve_wbnb_raw,
        "reserve_busd_raw": reserve_busd_raw,
    }


def get_amounts_out(w3: Web3, amount_in: int, path: list[str]) -> list[int]:
    """Query getAmountsOut from PancakeSwap V2 router."""
    router = w3.eth.contract(address=PANCAKESWAP_V2_ROUTER, abi=ROUTER_ABI)
    checksummed_path = [Web3.to_checksum_address(addr) for addr in path]
    amounts = router.functions.getAmountsOut(amount_in, checksummed_path).call()
    return list(amounts)
