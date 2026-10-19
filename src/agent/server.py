"""HTTP server exposing agent endpoints."""

import json
from typing import Any
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from agent.a2a import process_a2a_request
from agent.card import build_agent_card
from agent.config import load_settings

app = FastAPI(title="BNB Chain AI Agent")


@app.get("/health")
def health() -> dict[str, Any]:
    """Health check endpoint reflecting current configuration."""
    cfg = load_settings()
    return {
        "status": "ok",
        "chain_id": cfg.chain_id,
        "loops_enabled": cfg.run_loops,
    }


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
    return JSONResponse(status_code=200, content=response_content)
