"""Configuration module for the agent."""

import os
from dataclasses import dataclass
from dotenv import load_dotenv

# Automatically load .env if present
load_dotenv()

DEFAULT_RPC_URL = "https://data-seed-prebsc-1-s1.bnbchain.org:8545"
DEFAULT_CHAIN_ID = 97
DEFAULT_PUBLIC_BASE_URL = "http://localhost:8000"


@dataclass(frozen=True)
class Settings:
    """Agent runtime settings."""

    private_key: str | None
    rpc_url: str
    chain_id: int
    public_base_url: str
    run_loops: bool

    def __repr__(self) -> str:
        # Never expose or print private_key value
        pk_display = "<set>" if self.private_key else "<not set>"
        return (
            f"Settings(private_key={pk_display}, rpc_url='{self.rpc_url}', "
            f"chain_id={self.chain_id}, public_base_url='{self.public_base_url}', "
            f"run_loops={self.run_loops})"
        )


def load_settings(environ: dict[str, str] | None = None) -> Settings:
    """Load settings from environment variables with defaults."""
    env = os.environ if environ is None else environ

    raw_private_key = env.get("PRIVATE_KEY")
    private_key = raw_private_key.strip() if raw_private_key else None

    rpc_url = env.get("RPC_URL", DEFAULT_RPC_URL)

    raw_chain_id = env.get("CHAIN_ID")
    try:
        chain_id = int(raw_chain_id) if raw_chain_id is not None and raw_chain_id.strip() != "" else DEFAULT_CHAIN_ID
    except ValueError:
        chain_id = DEFAULT_CHAIN_ID

    # Priority: RENDER_EXTERNAL_URL > PUBLIC_BASE_URL > default
    render_url = env.get("RENDER_EXTERNAL_URL")
    if render_url and render_url.strip():
        public_base_url = render_url.strip().rstrip("/")
    else:
        public_base_url = env.get("PUBLIC_BASE_URL", DEFAULT_PUBLIC_BASE_URL).strip().rstrip("/")

    # RUN_LOOPS: default disabled; enabled strictly when value is "1"
    run_loops = env.get("RUN_LOOPS") == "1"

    return Settings(
        private_key=private_key,
        rpc_url=rpc_url,
        chain_id=chain_id,
        public_base_url=public_base_url,
        run_loops=run_loops,
    )


settings = load_settings()
