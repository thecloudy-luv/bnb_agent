# my-agent

AI Agent participating in the **BNB Chain "Set and Earn"** campaign on BSC Testnet (Chain ID 97), featuring ERC-8004 identity registration and ERC-8183 job commerce negotiation.

## Tech Stack

- **Language & Runtime:** Python 3.11 with [`uv`](https://docs.astral.sh/uv/)
- **Framework:** [FastAPI](https://fastapi.tiangolo.com/) & [Uvicorn](https://www.uvicorn.org/)
- **SDK:** Official [BNBAgent SDK](https://github.com/bnb-chain/bnbagent-sdk) (`bnbagent==0.5.0`)
- **Testing:** [pytest](https://docs.pytest.org/)

## Project Structure

```text
.
├── src/
│   └── agent/
│       ├── __init__.py
│       ├── a2a.py          # A2A JSON-RPC handler (ERC-8183 quote + job status)
│       ├── card.py         # Agent card (/.well-known/agent-card.json)
│       ├── config.py       # Configuration and safe env loading
│       ├── profile.py      # Agent name, category, price
│       └── server.py       # FastAPI application and endpoints
├── tests/
│   ├── test_a2a.py         # A2A protocol and ERC-8183 skills
│   ├── test_card.py        # Agent card
│   ├── test_config.py      # Unit tests for settings
│   └── test_server.py      # Integration tests for API endpoints
├── .env.example            # Sample environment variables
├── .python-version         # Pinned Python version (3.11)
├── pyproject.toml          # Project configuration and dependencies
└── uv.lock                 # Pinned lockfile
```

## Local Development

### 1. Prerequisites

Ensure `git`, `uv`, and Python 3.11 are installed:

```powershell
uv python install 3.11
```

### 2. Install Dependencies

Sync the environment using `uv`:

```powershell
uv sync
```

### 3. Run Tests

Execute test suite:

```powershell
uv run pytest -q
```

### 4. Run Server Locally

Start the development server:

```powershell
uv run uvicorn agent.server:app --app-dir src --port 8000
```

Check the health endpoint:

```text
http://localhost:8000/health
```

Expected output:

```json
{"status":"ok","chain_id":97,"loops_enabled":false}
```
