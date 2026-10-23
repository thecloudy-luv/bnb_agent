"""HTTP server exposing agent endpoints."""

from contextlib import asynccontextmanager
import json
import time
from pathlib import Path
from typing import Any, AsyncGenerator
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from agent.a2a import process_a2a_request
from agent.addresses import CAMPAIGN_WALLET
from agent.card import build_agent_card
from agent.config import load_settings
from agent.dashboard import DASHBOARD_HTML
from agent.jobs import get_tracked_jobs, start_jobs_loop, stop_jobs_loop
from agent.loop import get_last_check, get_recent_logs, start_strategy_loop, stop_strategy_loop
from agent.progress import get_campaign_progress

LOGO_PATH = Path(__file__).resolve().parent / "static" / "logo.png"


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """FastAPI lifespan to manage background automation loops."""
    start_strategy_loop()
    start_jobs_loop()
    try:
        yield
    finally:
        stop_jobs_loop()
        stop_strategy_loop()


app = FastAPI(title="TiltBalance AI Agent", lifespan=lifespan)


@app.get("/", response_class=HTMLResponse)
def index() -> str:
    """Return responsive single-page monitoring dashboard."""
    return DASHBOARD_HTML


@app.get("/progress")
def progress() -> dict[str, Any]:
    """Return on-chain verified campaign progress and target metrics."""
    return get_campaign_progress()


@app.get("/health")
def health() -> dict[str, Any]:
    """Health check endpoint reflecting current configuration."""
    cfg = load_settings()
    return {
        "status": "ok",
        "chain_id": cfg.chain_id,
        "loops_enabled": cfg.run_loops,
    }


_A2A_LOGS: list[dict[str, Any]] = []


@app.get("/status")
def status() -> dict[str, Any]:
    """Public read-only status, recent rebalancing journal, and ERC-8183 jobs."""
    cfg = load_settings()
    last_check = get_last_check()
    recent = get_recent_logs(limit=20)
    jobs = get_tracked_jobs()

    target_weight_val = last_check["target_weight"] if last_check else 0.5
    current_weight_val = last_check["current_weight"] if last_check else 0.5
    drift_val = last_check["drift"] if last_check else 0.0

    return {
        "status": "online",
        "wallet": CAMPAIGN_WALLET,
        "loops_enabled": cfg.run_loops,
        "last_check": last_check,
        "target_weight": target_weight_val,
        "current_weight": current_weight_val,
        "drift": drift_val,
        "recent_logs": recent,
        "jobs": jobs,
        "a2a_logs": _A2A_LOGS[-10:],
    }


@app.get("/logo.png")
def get_logo() -> FileResponse:
    """Return the agent PNG logo."""
    if not LOGO_PATH.exists():
        raise HTTPException(status_code=404, detail="Logo not found")
    return FileResponse(LOGO_PATH, media_type="image/png")


@app.get("/.well-known/agent-card.json")
def agent_card(request: Request) -> dict[str, Any]:
    """Return the A2A agent card describing identity and skills."""
    cfg = load_settings()
    base_url = cfg.public_base_url or str(request.base_url).rstrip("/")
    return build_agent_card(base_url)


@app.post("/a2a")
async def a2a_endpoint(request: Request) -> JSONResponse:
    """Handle incoming A2A JSON-RPC 2.0 requests."""
    client_ip = request.client.host if request.client else "127.0.0.1"

    # Check for body parse error
    try:
        body = await request.body()
        if not body:
            return JSONResponse(
                status_code=200,
                content={
                    "jsonrpc": "2.0",
                    "id": None,
                    "error": {"code": -32700, "message": "Parse error"},
                },
            )
        payload = json.loads(body.decode("utf-8"))
    except Exception:
        return JSONResponse(
            status_code=200,
            content={
                "jsonrpc": "2.0",
                "id": None,
                "error": {"code": -32700, "message": "Parse error"},
            },
        )

    response_content = process_a2a_request(payload, client_ip)
    _A2A_LOGS.append({
        "timestamp": time.time(),
        "client_ip": client_ip,
        "request": payload,
        "response": response_content,
    })
    if len(_A2A_LOGS) > 20:
        _A2A_LOGS.pop(0)
    return JSONResponse(status_code=200, content=response_content)
