"""ERC-8183 Job Desk module: scanning, processing, deliverable generation, submission, and settlement."""

import dataclasses
import json
import logging
import os
import threading
import time
from typing import Any
from web3 import Web3

from bnbagent.config import resolve_network, NetworkConfig
from bnbagent.erc8183 import ERC8183Client, Job, JobStatus, DeliverableManifest
from bnbagent.erc8183.commerce import CommerceClient
from bnbagent.storage import IPFSStorageProvider, upload_sync
from bnbagent.wallets import EVMWalletProvider

from agent.addresses import CAMPAIGN_WALLET, COMMERCE, PAYMENT_TOKEN_U
from agent.chain import get_pair_reserves, get_wallet_balances, get_web3
from agent.config import Settings, load_settings
from agent.market import fetch_bnb_closes
from agent.strategy import current_weight, momentum_24h, pool_price, target_weight
from agent.txlock import tx_lock

logger = logging.getLogger(__name__)

DISPUTE_WINDOW_SEC = 900
MIN_BUDGET_WEI = 100000000000000000  # 0.1 U (18 decimals)

# In-memory job state
_TRACKED_JOBS: dict[int, dict[str, Any]] = {}
_JOBS_LOCK = threading.Lock()
_LAST_SCANNED_BLOCK: int | None = None

_jobs_thread: threading.Thread | None = None
_stop_jobs_event = threading.Event()


def get_tracked_jobs() -> list[dict[str, Any]]:
    """Return in-memory snapshot of all tracked ERC-8183 jobs."""
    with _JOBS_LOCK:
        jobs = []
        now = int(time.time())
        for j in _TRACKED_JOBS.values():
            entry = dict(j)
            expired_at = entry.get("expired_at", 0)
            entry["time_remaining_sec"] = max(0, expired_at - now) if expired_at else 0
            jobs.append(entry)
        return sorted(jobs, key=lambda x: x["id"], reverse=True)


def record_tracked_job(job_data: dict[str, Any]) -> None:
    """Thread-safe update of job entry in memory."""
    with _JOBS_LOCK:
        job_id = job_data["id"]
        if job_id in _TRACKED_JOBS:
            _TRACKED_JOBS[job_id].update(job_data)
        else:
            _TRACKED_JOBS[job_id] = dict(job_data)


def parse_task(description: str) -> dict[str, Any]:
    """Parse job description supporting standard SDK schema, Pokter format, and plain text."""
    if not isinstance(description, str) or not description.strip():
        return {
            "task": "",
            "terms": {"deliverables": "", "quality_standards": "Read-only analysis only. Execute no transaction and move no funds."},
            "raw": description,
        }

    try:
        data = json.loads(description)
    except Exception:
        return {
            "task": description.strip(),
            "terms": {"deliverables": "", "quality_standards": "Read-only analysis only. Execute no transaction and move no funds."},
            "raw": description,
        }

    if not isinstance(data, dict):
        return {
            "task": str(data),
            "terms": {"deliverables": "", "quality_standards": "Read-only analysis only. Execute no transaction and move no funds."},
            "raw": data,
        }

    # Format (b): Pokter format {"protocol": "pokter-job", ..., "task": ...}
    if data.get("protocol") == "pokter-job":
        raw_task = data.get("task", "")
        task_str = ""
        if isinstance(raw_task, str):
            try:
                nested = json.loads(raw_task)
                if isinstance(nested, dict):
                    task_str = nested.get("task") or nested.get("description") or raw_task
                else:
                    task_str = raw_task
            except Exception:
                task_str = raw_task
        elif isinstance(raw_task, dict):
            task_str = raw_task.get("task") or raw_task.get("description") or str(raw_task)
        else:
            task_str = str(raw_task)

        terms = data.get("terms") if isinstance(data.get("terms"), dict) else {}
        return {
            "task": task_str,
            "terms": terms,
            "protocol": "pokter-job",
            "raw": data,
        }

    # Format (a): Standard SDK format {"task": "...", "terms": {...}}
    task_val = data.get("task", "")
    terms_val = data.get("terms") if isinstance(data.get("terms"), dict) else {}
    return {
        "task": str(task_val),
        "terms": terms_val,
        "version": data.get("version", 1),
        "raw": data,
    }


def generate_deliverable_content(task_info: dict[str, Any], rpc_url: str) -> str:
    """Generate read-only rebalancing analysis deliverable."""
    try:
        closes = fetch_bnb_closes(hours=25)
        momentum = momentum_24h(closes)
    except Exception as exc:
        logger.warning("Could not fetch BNB closes for deliverable (%s); using 0.0", exc)
        momentum = 0.0

    target = target_weight(momentum)

    w3 = get_web3(rpc_url)
    reserves = get_pair_reserves(w3)
    price = pool_price(reserves["reserve_wbnb"], reserves["reserve_busd"])

    balances = get_wallet_balances(w3, CAMPAIGN_WALLET)
    current = current_weight(balances["wbnb"], balances["busd"], price)
    drift = current - target

    if abs(drift) >= 0.03:
        if drift > 0:
            rec_action = "sell_wbnb"
            rec_reason = (
                f"BNB allocation ({current:.1%}) is {abs(drift):.1%} above target ({target:.1%}). "
                "Recommend rebalancing by selling WBNB into BUSD."
            )
        else:
            rec_action = "buy_wbnb"
            rec_reason = (
                f"BNB allocation ({current:.1%}) is {abs(drift):.1%} below target ({target:.1%}). "
                "Recommend rebalancing by selling BUSD into WBNB."
            )
    else:
        rec_action = "none"
        rec_reason = (
            f"BNB allocation ({current:.1%}) is within tolerance band of target ({target:.1%}). "
            "No rebalancing action required."
        )

    explanation = (
        f"Binance 24h BNB momentum is {momentum:+.2%}. TiltBalance calculates a target weight "
        f"of {target:.1%} BNB. Current portfolio weight is {current:.1%} (drift {drift:+.2%})."
    )

    analysis_payload = {
        "protocol": "erc8183-deliverable",
        "agent": "TiltBalance",
        "category": "rebalancing",
        "mode": "read-only-analysis",
        "market": {
            "source": "Binance Vision API (BNBUSDT 1h)",
            "momentum_24h": round(momentum, 6),
        },
        "portfolio": {
            "pool_price_busd": round(price, 4),
            "target_bnb_weight": round(target, 4),
            "current_bnb_weight": round(current, 4),
            "drift": round(drift, 4),
        },
        "recommendation": {
            "action": rec_action,
            "reason": rec_reason,
            "explanation": explanation,
        },
        "execution_note": "Read-only assessment provided per quality standards. No on-chain funds moved.",
    }

    # Always deliver canonical JSON format (satisfies 'Reply with JSON only')
    return json.dumps(analysis_payload, indent=2, sort_keys=True)


def validate_job_for_execution(job: Job, client: ERC8183Client, our_wallet: str) -> tuple[bool, str]:
    """Validate whether a job qualifies for work by this agent."""
    if job.provider.lower() != our_wallet.lower():
        return False, f"Provider {job.provider} does not match our wallet {our_wallet}"

    if job.status != JobStatus.FUNDED:
        return False, f"Job status is {job.status.name} ({job.status.value}), expected FUNDED (1)"

    now = int(time.time())
    if now >= job.expired_at - 900:
        return False, f"Job expired or too close to expiry (expired_at={job.expired_at}, now={now})"

    if job.budget < MIN_BUDGET_WEI:
        return False, f"Job budget {job.budget} wei is below minimum 0.1 U ({MIN_BUDGET_WEI} wei)"

    try:
        token = client.commerce.job_payment_token(job.id)
        if token.lower() != PAYMENT_TOKEN_U.lower():
            return False, f"Payment token {token} does not match token U {PAYMENT_TOKEN_U}"
    except Exception as exc:
        logger.warning("Could not verify jobPaymentToken on chain: %s", exc)

    return True, "Job is valid for execution"


def scan_funded_jobs(
    w3_logs: Web3,
    from_block: int,
    to_block: int,
    provider: str,
) -> list[int]:
    """Scan JobFunded events in chunks <= 1000 blocks to comply with RPC limitations."""
    commerce_logs = CommerceClient(w3_logs, COMMERCE)
    funded_job_ids: list[int] = []

    curr = from_block
    while curr <= to_block:
        chunk_to = min(curr + 999, to_block)
        try:
            events = commerce_logs.get_job_funded_events(
                from_block=curr,
                to_block=chunk_to,
                provider=provider,
            )
            for ev in events:
                funded_job_ids.append(ev["jobId"])
        except Exception as exc:
            logger.warning("Failed querying JobFunded events in range [%d, %d]: %s", curr, chunk_to, exc)
        curr = chunk_to + 1

    return sorted(list(set(funded_job_ids)))


def create_erc8183_client(
    rpc_url: str,
    private_key: str | None = None,
) -> ERC8183Client:
    """Create ERC8183Client configured for BSC Testnet with use_paymaster=False."""
    cfg = resolve_network("bsc-testnet")
    cfg = dataclasses.replace(cfg, rpc_url=rpc_url, use_paymaster=False)

    wallet = None
    if private_key:
        wallet = EVMWalletProvider(
            password="job-desk-password",
            private_key=private_key,
            persist=False,
        )

    return ERC8183Client(wallet_provider=wallet, network=cfg)


def submit_job_deliverable(
    job: Job,
    client: ERC8183Client,
    content: str,
    storage_key: str | None,
    dry_run: bool = True,
) -> tuple[bool, str, str | None]:
    """Upload manifest to IPFS and call client.submit under TX_LOCK."""
    network_cfg = client.network if isinstance(client.network, NetworkConfig) else resolve_network("bsc-testnet")
    manifest = DeliverableManifest(
        version=1,
        job_id=job.id,
        chain_id=network_cfg.chain_id,
        contracts={
            "commerce": network_cfg.commerce_contract,
            "router": network_cfg.router_contract,
            "policy": network_cfg.policy_contract,
        },
        response={
            "content": content,
            "content_type": "application/json",
        },
        metadata={
            "agent": "TiltBalance",
            "category": "rebalancing",
        },
    )
    manifest_hash = manifest.manifest_hash()

    if dry_run:
        fake_url = f"https://gateway.pinata.cloud/ipfs/QmDryRunMockManifestHashForJob{job.id}"
        logger.info(
            "[DRY-RUN] Would submit job %d with manifest_hash=%s to %s",
            job.id,
            manifest_hash.hex(),
            fake_url,
        )
        return True, "Dry-run deliverable generated successfully", fake_url

    if not storage_key:
        return False, "STORAGE_API_KEY is not configured; cannot upload deliverable to IPFS", None

    storage = IPFSStorageProvider(
        pinning_api_url="https://api.pinata.cloud/pinning/pinJSONToIPFS",
        pinning_api_key=storage_key,
        gateway_url="https://gateway.pinata.cloud/ipfs/",
    )

    try:
        ipfs_url = upload_sync(storage, manifest.to_dict(), filename=f"job-{job.id}-manifest.json")
    except Exception as exc:
        logger.error("Failed uploading deliverable manifest to IPFS: %s", exc)
        return False, f"IPFS upload failed: {exc}", None

    cid = ipfs_url.replace("ipfs://", "").strip()
    deliverable_url = f"https://gateway.pinata.cloud/ipfs/{cid}"

    try:
        with tx_lock():
            client.submit(job.id, manifest_hash, {"deliverable_url": deliverable_url})
        logger.info("Successfully submitted deliverable for job %d: %s", job.id, deliverable_url)
        return True, "Deliverable submitted successfully", deliverable_url
    except Exception as exc:
        logger.error("Failed submitting job %d on-chain: %s", job.id, exc)
        return False, f"On-chain submission failed: {exc}", None


def settle_job(
    job_id: int,
    client: ERC8183Client,
    dry_run: bool = True,
) -> tuple[bool, str]:
    """Call client.settle under TX_LOCK after dispute window."""
    if dry_run:
        logger.info("[DRY-RUN] Would settle job %d", job_id)
        return True, "Dry-run settle simulated"

    try:
        with tx_lock():
            client.settle(job_id)
        logger.info("Successfully settled job %d", job_id)
        return True, "Job settled successfully"
    except Exception as exc:
        logger.error("Failed settling job %d: %s", job_id, exc)
        return False, f"Settlement failed: {exc}"


def process_single_job(
    job_id: int,
    cfg: Settings,
    dry_run: bool = True,
) -> dict[str, Any]:
    """Complete evaluation and processing flow for a single job id."""
    client = create_erc8183_client(cfg.rpc_url, cfg.private_key)

    try:
        job = client.get_job(job_id)
    except Exception as exc:
        msg = f"Failed to fetch job {job_id}: {exc}"
        logger.error(msg)
        return {"id": job_id, "status": "ERROR", "error": msg}

    our_wallet = CAMPAIGN_WALLET
    if cfg.private_key:
        try:
            from eth_account import Account
            our_wallet = Account.from_key(cfg.private_key).address
        except Exception:
            pass

    # Check job in-memory record
    now = int(time.time())
    record = {
        "id": job.id,
        "client": job.client,
        "provider": job.provider,
        "budget": job.budget,
        "budget_u": str(job.budget / 10**18),
        "status": job.status.name,
        "expired_at": job.expired_at,
        "submitted_at": job.submitted_at,
        "deliverable_url": None,
        "error": None,
    }

    # If job is already COMPLETED or EXPIRED or REJECTED
    if job.status == JobStatus.COMPLETED:
        record["status"] = "COMPLETED"
        record_tracked_job(record)
        return record

    # If job is SUBMITTED, check if ready to settle
    if job.status == JobStatus.SUBMITTED:
        record["status"] = "SUBMITTED"
        if job.provider.lower() == our_wallet.lower():
            if now >= job.submitted_at + DISPUTE_WINDOW_SEC:
                logger.info("Job %d dispute window passed; settling...", job.id)
                ok, msg = settle_job(job.id, client, dry_run=dry_run)
                if ok:
                    record["status"] = "COMPLETED"
                else:
                    record["error"] = msg
            else:
                remaining = (job.submitted_at + DISPUTE_WINDOW_SEC) - now
                logger.info("Job %d submitted; waiting %ds for dispute window", job.id, remaining)
        record_tracked_job(record)
        return record

    # If FUNDED, validate and deliver
    if job.status == JobStatus.FUNDED:
        valid, reason = validate_job_for_execution(job, client, our_wallet)
        if not valid:
            logger.info("Skipping job %d: %s", job.id, reason)
            record["error"] = reason
            record_tracked_job(record)
            return record

        task_info = parse_task(job.description)
        deliverable_content = generate_deliverable_content(task_info, cfg.rpc_url)

        ok, msg, deliv_url = submit_job_deliverable(
            job,
            client,
            deliverable_content,
            cfg.storage_api_key,
            dry_run=dry_run,
        )

        if ok:
            record["status"] = "SUBMITTED"
            record["submitted_at"] = now
            record["deliverable_url"] = deliv_url
        else:
            record["error"] = msg

        record_tracked_job(record)
        return record

    record["error"] = f"Job is in state {job.status.name}, no action taken"
    record_tracked_job(record)
    return record


def run_jobs_cycle(cfg: Settings) -> list[dict[str, Any]]:
    """Execute one scan and processing cycle for ERC-8183 jobs."""
    global _LAST_SCANNED_BLOCK
    w3_logs = get_web3(cfg.rpc_logs_url)

    try:
        latest_block = w3_logs.eth.block_number
    except Exception as exc:
        logger.error("Failed to query block number from RPC_LOGS_URL: %s", exc)
        return get_tracked_jobs()

    if _LAST_SCANNED_BLOCK is None:
        if cfg.job_scan_from_block is not None:
            start_block = cfg.job_scan_from_block
        else:
            start_block = max(0, latest_block - 20000)
    else:
        start_block = _LAST_SCANNED_BLOCK + 1

    to_block = latest_block

    if start_block <= to_block:
        logger.info("Scanning JobFunded events from block %d to %d", start_block, to_block)
        our_wallet = CAMPAIGN_WALLET
        if cfg.private_key:
            try:
                from eth_account import Account
                our_wallet = Account.from_key(cfg.private_key).address
            except Exception:
                pass

        found_jobs = scan_funded_jobs(w3_logs, start_block, to_block, our_wallet)
        _LAST_SCANNED_BLOCK = to_block

        for j_id in found_jobs:
            try:
                process_single_job(j_id, cfg, dry_run=False)
            except Exception as exc:
                logger.error("Error processing discovered job %d: %s", j_id, exc)

    # Also review all currently tracked SUBMITTED jobs for settlement
    tracked = get_tracked_jobs()
    now = int(time.time())
    for item in tracked:
        if item.get("status") == "SUBMITTED":
            sub_at = item.get("submitted_at") or 0
            if now >= sub_at + DISPUTE_WINDOW_SEC:
                try:
                    process_single_job(item["id"], cfg, dry_run=False)
                except Exception as exc:
                    logger.error("Error settling tracked job %d: %s", item["id"], exc)

    return get_tracked_jobs()


def _jobs_worker(stop_event: threading.Event) -> None:
    """Worker thread running ERC-8183 jobs cycle every 30 seconds."""
    interval = int(os.getenv("JOBS_INTERVAL_SEC", "30"))
    logger.info("ERC-8183 jobs worker thread started (interval=%ds)", interval)

    while not stop_event.is_set():
        cfg = load_settings()
        try:
            run_jobs_cycle(cfg)
        except Exception as exc:
            logger.error("Error during ERC-8183 jobs cycle: %s", exc, exc_info=True)

        for _ in range(interval):
            if stop_event.is_set():
                break
            time.sleep(1)

    logger.info("ERC-8183 jobs worker thread stopped")


def start_jobs_loop() -> None:
    """Start background ERC-8183 job scanner thread if RUN_LOOPS=1."""
    global _jobs_thread, _stop_jobs_event
    cfg = load_settings()
    if not cfg.run_loops:
        logger.info("Background ERC-8183 jobs loop is disabled (RUN_LOOPS != 1)")
        return

    if _jobs_thread and _jobs_thread.is_alive():
        logger.warning("ERC-8183 jobs loop is already running")
        return

    _stop_jobs_event.clear()
    _jobs_thread = threading.Thread(target=_jobs_worker, args=(_stop_jobs_event,), daemon=True)
    _jobs_thread.start()
    logger.info("Started background ERC-8183 jobs loop thread")


def stop_jobs_loop() -> None:
    """Stop background ERC-8183 job scanner thread."""
    global _stop_jobs_event, _jobs_thread
    _stop_jobs_event.set()
    if _jobs_thread and _jobs_thread.is_alive():
        _jobs_thread.join(timeout=3.0)
    _jobs_thread = None
