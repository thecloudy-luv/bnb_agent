"""Tests for ERC-8183 Job Desk module."""

import json
import time
from unittest.mock import MagicMock, patch
from web3 import Web3

from bnbagent.config import NetworkConfig
from bnbagent.erc8183 import Job, JobStatus
from agent.addresses import CAMPAIGN_WALLET, PAYMENT_TOKEN_U
from agent.config import Settings
from agent.jobs import (
    create_erc8183_client,
    generate_deliverable_content,
    get_tracked_jobs,
    parse_task,
    process_single_job,
    record_tracked_job,
    settle_job,
    submit_job_deliverable,
    validate_job_for_execution,
)


def test_parse_task_sdk_format() -> None:
    raw = json.dumps({
        "version": 1,
        "task": "Analyse the proposed BNB trading range.",
        "terms": {
            "deliverables": "A JSON assessment.",
            "quality_standards": "Read-only analysis only. Execute no transaction and move no funds.",
        },
    })
    parsed = parse_task(raw)
    assert parsed["task"] == "Analyse the proposed BNB trading range."
    assert parsed["terms"]["deliverables"] == "A JSON assessment."
    assert "Read-only" in parsed["terms"]["quality_standards"]


def test_parse_task_pokter_format_nested_json() -> None:
    raw = json.dumps({
        "protocol": "pokter-job",
        "task": json.dumps({"task": "Evaluate portfolio weights with 60% BNB"}),
        "terms": {"quality_standards": "Reply with JSON only"},
    })
    parsed = parse_task(raw)
    assert parsed["protocol"] == "pokter-job"
    assert "Evaluate portfolio weights" in parsed["task"]
    assert parsed["terms"]["quality_standards"] == "Reply with JSON only"


def test_parse_task_pokter_format_plain_task() -> None:
    raw = json.dumps({
        "protocol": "pokter-job",
        "task": "Plain Pokter task description",
    })
    parsed = parse_task(raw)
    assert parsed["protocol"] == "pokter-job"
    assert parsed["task"] == "Plain Pokter task description"


def test_parse_task_raw_string_fallback() -> None:
    raw = "Not a json string at all, just human words"
    parsed = parse_task(raw)
    assert parsed["task"] == raw
    assert "quality_standards" in parsed["terms"]


def test_validate_job_branches() -> None:
    now = int(time.time())
    client_mock = MagicMock()
    client_mock.commerce.job_payment_token.return_value = PAYMENT_TOKEN_U

    # Valid job
    good_job = Job(
        id=100,
        client="0x1111111111111111111111111111111111111111",
        provider=CAMPAIGN_WALLET,
        evaluator="0x2222222222222222222222222222222222222222",
        description="valid job",
        budget=100000000000000000,
        expired_at=now + 3600,
        status=JobStatus.FUNDED,
        hook="0x0000000000000000000000000000000000000000",
    )
    ok, reason = validate_job_for_execution(good_job, client_mock, CAMPAIGN_WALLET)
    assert ok is True

    # Wrong provider
    wrong_prov = Job(
        id=101,
        client=good_job.client,
        provider="0x9999999999999999999999999999999999999999",
        evaluator=good_job.evaluator,
        description="wrong prov",
        budget=good_job.budget,
        expired_at=good_job.expired_at,
        status=JobStatus.FUNDED,
        hook=good_job.hook,
    )
    ok, reason = validate_job_for_execution(wrong_prov, client_mock, CAMPAIGN_WALLET)
    assert ok is False
    assert "Provider" in reason

    # Wrong status (COMPLETED)
    wrong_status = Job(
        id=102,
        client=good_job.client,
        provider=CAMPAIGN_WALLET,
        evaluator=good_job.evaluator,
        description="completed job",
        budget=good_job.budget,
        expired_at=good_job.expired_at,
        status=JobStatus.COMPLETED,
        hook=good_job.hook,
    )
    ok, reason = validate_job_for_execution(wrong_status, client_mock, CAMPAIGN_WALLET)
    assert ok is False
    assert "status" in reason

    # Expired
    expired_job = Job(
        id=103,
        client=good_job.client,
        provider=CAMPAIGN_WALLET,
        evaluator=good_job.evaluator,
        description="expired job",
        budget=good_job.budget,
        expired_at=now + 500,  # less than 900s left
        status=JobStatus.FUNDED,
        hook=good_job.hook,
    )
    ok, reason = validate_job_for_execution(expired_job, client_mock, CAMPAIGN_WALLET)
    assert ok is False
    assert "expired" in reason.lower()

    # Budget too low
    low_budget = Job(
        id=104,
        client=good_job.client,
        provider=CAMPAIGN_WALLET,
        evaluator=good_job.evaluator,
        description="low budget",
        budget=50000000000000000,  # 0.05 U
        expired_at=good_job.expired_at,
        status=JobStatus.FUNDED,
        hook=good_job.hook,
    )
    ok, reason = validate_job_for_execution(low_budget, client_mock, CAMPAIGN_WALLET)
    assert ok is False
    assert "budget" in reason.lower()

    # Wrong payment token
    client_mock.commerce.job_payment_token.return_value = "0x0000000000000000000000000000000000000001"
    ok, reason = validate_job_for_execution(good_job, client_mock, CAMPAIGN_WALLET)
    assert ok is False
    assert "Payment token" in reason


@patch("agent.jobs.get_web3")
@patch("agent.jobs.fetch_bnb_closes")
@patch("agent.jobs.get_pair_reserves")
@patch("agent.jobs.get_wallet_balances")
def test_generate_deliverable_content_json_only(
    mock_balances: MagicMock,
    mock_reserves: MagicMock,
    mock_closes: MagicMock,
    mock_w3: MagicMock,
) -> None:
    mock_closes.return_value = [600.0] * 24 + [630.0]  # +5% momentum
    mock_reserves.return_value = {"reserve_wbnb": 10.0, "reserve_busd": 6000.0}
    mock_balances.return_value = {"wbnb": 1.0, "busd": 600.0, "tbnb": 0.5}

    task_info = {
        "task": "Please assess BNB allocation. Reply with JSON only.",
        "terms": {"quality_standards": "Read-only analysis only."},
    }
    content = generate_deliverable_content(task_info, "https://mock-rpc")
    parsed = json.loads(content)

    assert parsed["protocol"] == "erc8183-deliverable"
    assert parsed["agent"] == "TiltBalance"
    assert parsed["category"] == "rebalancing"
    assert parsed["mode"] == "read-only-analysis"
    assert "recommendation" in parsed
    assert "No on-chain funds moved" in parsed["execution_note"]


@patch("bnbagent.erc8183.client.create_web3")
def test_create_erc8183_client_disables_paymaster(mock_create_w3: MagicMock) -> None:
    mock_w3 = MagicMock()
    mock_w3.eth.chain_id = 97
    mock_create_w3.return_value = mock_w3

    client = create_erc8183_client("https://mock-rpc")
    assert isinstance(client.network, NetworkConfig)
    assert client.network.use_paymaster is False



def test_submit_job_deliverable_dry_run() -> None:
    job = Job(
        id=77,
        client="0x1111111111111111111111111111111111111111",
        provider=CAMPAIGN_WALLET,
        evaluator="0x2222222222222222222222222222222222222222",
        description="sample",
        budget=100000000000000000,
        expired_at=int(time.time()) + 3600,
        status=JobStatus.FUNDED,
        hook="0x0000000000000000000000000000000000000000",
    )
    client_mock = MagicMock()
    client_mock.network = NetworkConfig(
        name="bsc-testnet",
        chain_id=97,
        rpc_url="https://mock",
        paymaster_url="https://mock",
        use_paymaster=False,
        registry_contract="0x8004A818BFB912233c491871b3d84c89A494BD9e",
        commerce_contract="0xa206c0517b6371c6638cd9e4a42cc9f02a33b0de",
        router_contract="0xd7d36d66d2f1b608a0f943f722d27e3744f66f25",
        policy_contract="0xd6a4217588f6b1f5657a92a3e94e6422ad771cea",
    )
    ok, msg, url = submit_job_deliverable(
        job,
        client_mock,
        content='{"test": 1}',
        storage_key=None,
        dry_run=True,
    )
    assert ok is True
    assert "dry-run" in msg.lower()
    assert url is not None
    client_mock.submit.assert_not_called()


def test_settle_job_dry_run() -> None:
    client_mock = MagicMock()
    ok, msg = settle_job(88, client_mock, dry_run=True)
    assert ok is True
    assert "dry-run" in msg.lower()
    client_mock.settle.assert_not_called()


def test_tracked_jobs_memory_store() -> None:
    record = {
        "id": 999,
        "client": "0xabc",
        "provider": CAMPAIGN_WALLET,
        "budget": 100000000000000000,
        "budget_u": "0.1",
        "status": "FUNDED",
        "expired_at": int(time.time()) + 1800,
        "submitted_at": None,
        "deliverable_url": None,
        "error": None,
    }
    record_tracked_job(record)
    tracked = get_tracked_jobs()
    matched = [j for j in tracked if j["id"] == 999]
    assert len(matched) == 1
    assert matched[0]["status"] == "FUNDED"
    assert matched[0]["time_remaining_sec"] > 0
