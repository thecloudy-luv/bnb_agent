"""Canonical contract and wallet addresses on BSC Testnet (Chain ID 97)."""

from web3 import Web3

# Campaign agent wallet
CAMPAIGN_WALLET = Web3.to_checksum_address("0xa59C56C5D269c85Af6eb997deA9A1791E4E4e9C5")

# Identity & ERC-8183 Commerce stack
IDENTITY_REGISTRY = Web3.to_checksum_address("0x8004A818BFB912233c491871b3d84c89A494BD9e")
COMMERCE = Web3.to_checksum_address("0xa206c0517b6371c6638cd9e4a42cc9f02a33b0de")
ROUTER_PROXY = Web3.to_checksum_address("0xd7d36d66d2f1b608a0f943f722d27e3744f66f25")
POLICY = Web3.to_checksum_address("0xd6a4217588f6b1f5657a92a3e94e6422ad771cea")

# Tokens
PAYMENT_TOKEN_U = Web3.to_checksum_address("0xc70B8741B8B07A6d61E54fd4B20f22Fa648E5565")
WBNB = Web3.to_checksum_address("0xae13d989daC2f0dEbFf460aC112a837C89BAa7cd")
BUSD = Web3.to_checksum_address("0x78867BbEeF44f2326bF8DDd1941a4439382EF2A7")

# DEX Contracts (PancakeSwap V2 on BSC Testnet)
PANCAKESWAP_V2_ROUTER = Web3.to_checksum_address("0xD99D1c33F9fC3444f8101754aBC46c52416550D1")
PANCAKESWAP_V2_FACTORY = Web3.to_checksum_address("0x6725F303b657a9451d8BA641348b6761A6CC7a17")
PAIR_WBNB_BUSD = Web3.to_checksum_address("0x85EcDcdd01EbE0BfD0Aba74B81Ca6d7F4A53582b")
