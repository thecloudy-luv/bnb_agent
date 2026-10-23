"""Global transaction lock to ensure serialized on-chain writes and avoid nonce collisions."""

from contextlib import contextmanager
import logging
import threading
from typing import Generator

logger = logging.getLogger(__name__)

# Global re-entrant lock for all on-chain state-changing transactions
TX_LOCK = threading.Lock()


@contextmanager
def tx_lock(timeout: float = 120.0) -> Generator[None, None, None]:
    """Context manager acquiring the global transaction lock with timeout."""
    acquired = TX_LOCK.acquire(timeout=timeout)
    if not acquired:
        logger.error("Timed out waiting to acquire global TX_LOCK (timeout=%ss)", timeout)
        raise TimeoutError("Could not acquire TX_LOCK within timeout window")
    try:
        yield
    finally:
        TX_LOCK.release()
