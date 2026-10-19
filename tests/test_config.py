"""Tests for agent configuration."""

from agent.config import (
    DEFAULT_CHAIN_ID,
    DEFAULT_PUBLIC_BASE_URL,
    DEFAULT_RPC_URL,
    load_settings,
)


def test_default_config() -> None:
    """Verify default configuration values when no env vars are supplied."""
    cfg = load_settings({})
    assert cfg.private_key is None
    assert cfg.rpc_url == DEFAULT_RPC_URL
    assert cfg.chain_id == DEFAULT_CHAIN_ID
    assert cfg.public_base_url == DEFAULT_PUBLIC_BASE_URL
    assert cfg.run_loops is False


def test_run_loops_strictly_enabled_with_one() -> None:
    """Verify RUN_LOOPS is only True when set to exactly '1'."""
    assert load_settings({"RUN_LOOPS": "1"}).run_loops is True
    assert load_settings({"RUN_LOOPS": "0"}).run_loops is False
    assert load_settings({"RUN_LOOPS": "true"}).run_loops is False
    assert load_settings({"RUN_LOOPS": "TRUE"}).run_loops is False
    assert load_settings({"RUN_LOOPS": ""}).run_loops is False
    assert load_settings({}).run_loops is False


def test_public_base_url_priority() -> None:
    """Verify RENDER_EXTERNAL_URL takes precedence over PUBLIC_BASE_URL."""
    # When RENDER_EXTERNAL_URL is set, it should be used
    cfg = load_settings({
        "RENDER_EXTERNAL_URL": "https://my-render-agent.onrender.com/",
        "PUBLIC_BASE_URL": "https://fallback.example.com",
    })
    assert cfg.public_base_url == "https://my-render-agent.onrender.com"

    # When only PUBLIC_BASE_URL is set
    cfg2 = load_settings({
        "PUBLIC_BASE_URL": "https://custom.example.com/",
    })
    assert cfg2.public_base_url == "https://custom.example.com"

    # When neither is set, use default
    cfg3 = load_settings({})
    assert cfg3.public_base_url == DEFAULT_PUBLIC_BASE_URL


def test_custom_rpc_and_chain_id() -> None:
    """Verify custom RPC_URL and CHAIN_ID parsing."""
    cfg = load_settings({
        "RPC_URL": "https://custom-rpc.example.com",
        "CHAIN_ID": "56",
    })
    assert cfg.rpc_url == "https://custom-rpc.example.com"
    assert cfg.chain_id == 56


def test_private_key_not_in_repr() -> None:
    """Ensure private key is never leaked in repr or string representation."""
    secret = "0x0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef"
    cfg = load_settings({"PRIVATE_KEY": secret})
    repr_str = repr(cfg)
    assert secret not in repr_str
    assert "<set>" in repr_str
