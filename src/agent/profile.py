"""Agent profile and identity metadata for TiltBalance."""

AGENT_NAME = "TiltBalance"
AGENT_DESCRIPTION = (
    "Rebalances a WBNB/BUSD portfolio on BSC testnet toward a target weight "
    "that tilts with real BNB momentum (Binance data), and anchors the hash "
    "of every decision in the swap calldata."
)
CATEGORY = "rebalancing"
PRICE_U = "0.1"
ICON_PATH = "/logo.png"
EXAMPLES = [
    "Analyse my 60/40 BNB/stable split and tell me how to rebalance",
    "Give me today's BNB tilt target and the swap you would make",
    "Explain your last rebalance",
]
VERSION = "0.1.0"
