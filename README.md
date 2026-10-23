# TiltBalance

**TiltBalance** is an autonomous AI agent for the **BNB Chain "Set and Earn"** program on **BSC Testnet (Chain ID 97)** registered in the **rebalancing** category.

TiltBalance maintains an active WBNB / BUSD portfolio on PancakeSwap Testnet near a target allocation that tilts dynamically with real-world 24-hour BNB price momentum (sourced from Binance Vision API). Each rebalancing decision computes a verifiable cryptographic hash that is embedded into the swap calldata, providing transparent, on-chain auditable operation.

---

## On-Chain Identity & Network

| Parameter | Value |
|---|---|
| **Agent Name** | `TiltBalance` |
| **Category** | `rebalancing` |
| **Network** | BNB Smart Chain Testnet (Chain ID `97`) |
| **ERC-8004 Agent ID** | `2659` |
| **Campaign Agent Wallet** | `0xa59C56C5D269c85Af6eb997deA9A1791E4E4e9C5` |
| **ERC-8004 Identity Registry** | `0x8004A818BFB912233c491871b3d84c89A494BD9e` |
| **ERC-8183 AgenticCommerce** | `0xa206c0517b6371c6638cd9e4a42cc9f02a33b0de` |
| **ERC-8183 EvaluatorRouter** | `0xd7d36d66d2f1b608a0f943f722d27e3744f66f25` |
| **ERC-8183 OptimisticPolicy** | `0xd6a4217588f6b1f5657a92a3e94e6422ad771cea` |
| **Payment Token U** | `0xc70B8741B8B07A6d61E54fd4B20f22Fa648E5565` (18 decimals) |
| **PancakeSwap V2 Router** | `0xD99D1c33F9fC3444f8101754aBC46c52416550D1` |
| **PancakeSwap WBNB/BUSD Pair**| `0x85EcDcdd01EbE0BfD0Aba74B81Ca6d7F4A53582b` |

---

## Strategy Design

### 1. Market Momentum vs. Testnet Reserves
- **Real Market Signal**: TiltBalance queries 1-hour candlestick closes for `BNBUSDT` from Binance Vision API (`data-api.binance.vision/api/v3/klines`).
  $$\text{Momentum}_{24h} = \frac{\text{Close}_{\text{latest}}}{\text{Close}_{24h\text{ ago}}} - 1$$
- **Adaptive Target Weight**:
  $$\text{Target Weight}_{\text{BNB}} = \text{clamp}(0.50 + 3.0 \times \text{Momentum}_{24h}, 0.30, 0.70)$$
  *Bullish BNB momentum shifts the portfolio towards up to 70% WBNB; bearish momentum shifts it down to 30% WBNB.*
- **Pool Valuation**: Current portfolio weight is determined strictly by the live reserves of the PancakeSwap Testnet pair:
  $$\text{Price}_{\text{pool}} = \frac{\text{Reserve}_{\text{BUSD}}}{\text{Reserve}_{\text{WBNB}}}$$
  *Real-world prices provide the directional trend signal, while testnet liquidity reserves govern execution math and slippage.*

### 2. Decision Rules & Execution Guards
- **Band Drift Rebalance**: When $|\text{Current} - \text{Target}| \ge 3\%$, the agent initiates a swap to re-align the portfolio with the target weight.
- **Daily Calendar Rebalance**: If no swap has occurred yet during the current UTC day, the UTC hour is $\ge 18:00$, and $|\text{Current} - \text{Target}| \ge 0.5\%$, a daily calendar rebalance executes.
- **Safety Guards**:
  - Minimum trade threshold: $0.5\text{ BUSD}$.
  - Maximum trade per rebalance: capped at $50\%$ of the active side's balance.
  - Strict $1\%$ maximum slippage protection (`amountOutMin`).
  - Native gas reserve buffer: executions abort if wallet tBNB drops below $0.05\text{ tBNB}$.
  - Nonce safety: all state-changing transactions pass through a global `TX_LOCK`.

### 3. Calldata Proof of Decision
Every decision computes a deterministic Keccak256 hash over canonical JSON inputs (`inputs + action + amount_in`). This 32-byte hash is **appended directly to the end of the `swapExactTokensForTokens` transaction calldata**. Anyone can audit BscScan to confirm that the trailing 32 bytes of the swap calldata match the agent's published decision log.

---

## Service Endpoints

| Endpoint | Method | Description |
|---|---|---|
| `/` | `GET` | Responsive single-page dashboard displaying live metrics, KPIs, and campaign progress. |
| `/health` | `GET` | Service health status, chain ID, and automation loop state. |
| `/status` | `GET` | Public JSON status with latest market evaluations, decision journal, and tracked jobs. |
| `/progress` | `GET` | On-chain verified metrics for the BNB Chain Set & Earn campaign. |
| `/logo.png` | `GET` | 256×256 PNG agent icon. |
| `/.well-known/agent-card.json` | `GET` | A2A Agent Card defining capabilities, category, and skills. |
| `/a2a` | `POST` | JSON-RPC 2.0 A2A protocol endpoint (`message/send`). |

---

## A2A Skills & Example Requests

### 1. `negotiate-erc8183-job`
Generates an ERC-8183 signed quote envelope (fixed at `0.1 U`).

```bash
curl -X POST http://localhost:8000/a2a \
  -H "Content-Type: application/json" \
  -d '{
    "jsonrpc": "2.0",
    "id": 1,
    "method": "message/send",
    "params": {
      "skill": "negotiate-erc8183-job",
      "data": {
        "task_description": "Review portfolio balance and suggest rebalancing actions",
        "terms": {
          "deliverables": "JSON analysis report",
          "quality_standards": "Read-only analysis only. Execute no transaction and move no funds."
        }
      }
    }
  }'
```

### 2. `rebalance-analysis`
Provides read-only portfolio analysis for any given allocation (or evaluates TiltBalance's own testnet reserves if omitted).

```bash
curl -X POST http://localhost:8000/a2a \
  -H "Content-Type: application/json" \
  -d '{
    "jsonrpc": "2.0",
    "id": 2,
    "method": "message/send",
    "params": {
      "skill": "rebalance-analysis",
      "data": {
        "bnb_weight": 0.65
      }
    }
  }'
```

Sample output:
```json
{
  "jsonrpc": "2.0",
  "id": 2,
  "result": {
    "momentum_24h": 0.035,
    "target_bnb_weight": 0.605,
    "current_bnb_weight": 0.65,
    "drift": 0.045,
    "pool_price_busd": 431.25,
    "recommended_action": "sell_wbnb",
    "reason": "BNB allocation (65.0%) is 4.5% above target (60.5%). Recommend rebalancing by selling WBNB into BUSD."
  }
}
```

### 3. `erc8183-job-status`
Returns an on-chain status snapshot for a specific ERC-8183 job ID.

```bash
curl -X POST http://localhost:8000/a2a \
  -H "Content-Type: application/json" \
  -d '{
    "jsonrpc": "2.0",
    "id": 3,
    "method": "message/send",
    "params": {
      "skill": "erc8183-job-status",
      "data": {"job_id": 1543}
    }
  }'
```

---

## Local Development & Testing

### 1. Prerequisites
- Python 3.11
- `uv` package manager (`winget install astral-sh.uv` or `pip install uv`)

### 2. Installation
```powershell
uv sync
```

### 3. Running Test Suite
```powershell
uv run pytest -q
```

### 4. Running Local Server
```powershell
uv run uvicorn agent.server:app --app-dir src --port 8000
```
Open `http://localhost:8000/` in a browser to view the interactive dashboard.

---

## Operational Scripts

All transaction scripts default to `--dry-run` and will never broadcast transactions without `--send`.

- **Initialize Portfolio**:
  ```powershell
  uv run python scripts/setup_portfolio.py --bnb 0.1
  ```
- **Execute Rebalance Cycle Once**:
  ```powershell
  uv run python scripts/rebalance_once.py
  ```
- **Inspect / Deliver ERC-8183 Job**:
  ```powershell
  uv run python scripts/deliver_job.py 1543
  ```
- **Check / Register ERC-8004 Identity**:
  ```powershell
  # Dry-run registration payload
  uv run python scripts/register_agent.py

  # Inspect on-chain registration
  uv run python scripts/check_identity.py <agentId>
  ```
- **Audit Campaign Readiness**:
  ```powershell
  uv run python scripts/verify_campaign.py
  ```

---

## Deployment (Render)

TiltBalance is pre-configured for deployment on Render as a Web Service:

- **Environment:** Python
- **Build Command:**
  ```bash
  pip install uv && uv sync --frozen --no-dev
  ```
- **Start Command:**
  ```bash
  uv run --no-sync uvicorn agent.server:app --app-dir src --host 0.0.0.0 --port $PORT
  ```

---

## Environment Variables Reference

| Variable | Description | Default |
|---|---|---|
| `PRIVATE_KEY` | Hex private key for the campaign agent wallet | *None* |
| `RPC_URL` | BSC Testnet JSON-RPC endpoint | `https://data-seed-prebsc-1-s1.bnbchain.org:8545` |
| `RPC_LOGS_URL` | Logs-capable RPC endpoint for `eth_getLogs` queries | `https://bsc-testnet-rpc.publicnode.com` |
| `CHAIN_ID` | EVM Chain ID | `97` |
| `PUBLIC_BASE_URL` | Public URL of the agent service (auto-reads `RENDER_EXTERNAL_URL`) | `http://localhost:8000` |
| `RUN_LOOPS` | Automation loop flag (`1`: enabled on production, `0`: disabled) | `0` |
| `STORAGE_API_KEY` | Pinata IPFS JWT used for uploading ERC-8183 deliverables | *None* |
| `JOB_SCAN_FROM_BLOCK` | Optional block number to start scanning `JobFunded` events | *Latest - 20000* |
| `EXCLUDED_CLIENTS` | Comma-separated addresses to exclude from campaign hire counts | *None* |
