import os
import httpx
from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates

from services.master_registry import master_fleet

master_router = APIRouter()

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
templates = Jinja2Templates(directory=os.path.join(BASE_DIR, "web", "templates"))

@master_router.get("/master", response_class=HTMLResponse)
@master_router.get("/portfolio", response_class=HTMLResponse)
async def master_portfolio_view(request: Request):
    """Unified Multi-Agent Executive Command Center."""
    return templates.TemplateResponse(
        request=request,
        name="master_dashboard.html",
        context={"request": request}
    )

@master_router.get("/api/master/stats")
async def api_master_stats():
    """Aggregated real-time metrics across all registered autonomous agents."""
    data = await master_fleet.get_aggregated_portfolio()
    return JSONResponse(data)

@master_router.get("/api/master/agents")
async def api_master_agents():
    """Lists all registered agents."""
    return JSONResponse(master_fleet.get_registered_agents())

@master_router.post("/api/master/agents/register")
async def api_master_register_agent(request: Request):
    """Dynamically register a new autonomous agent (e.g. Agent 3, 4, 5)."""
    data = await request.json()
    if not data.get("name") or not data.get("local_url"):
        raise HTTPException(status_code=400, detail="Name and Local URL are required")
    
    # Verify connectivity before saving
    url = data["local_url"].rstrip("/")
    health_endpoint = data.get("health_endpoint", "/api/health")
    try:
        async with httpx.AsyncClient(timeout=3.5) as client:
            resp = await client.get(f"{url}{health_endpoint}")
            if resp.status_code != 200:
                raise HTTPException(status_code=400, detail=f"Agent responded with HTTP {resp.status_code}")
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Could not connect to {url}{health_endpoint}: {str(e)}")

    registered = master_fleet.add_agent(data)
    return JSONResponse({"status": "SUCCESS", "agent": registered})

@master_router.post("/api/master/agents/{agent_id}/action")
async def api_master_agent_action(agent_id: str, request: Request):
    """Triggers an action (e.g. prospect-now, followup-now) on a target agent."""
    body = await request.json()
    endpoint = body.get("endpoint", "/api/actions/prospect-now")
    
    agents = master_fleet.get_registered_agents()
    target = next((a for a in agents if a["id"] == agent_id), None)
    if not target:
        raise HTTPException(status_code=404, detail="Agent not found")
        
    url = (target.get("local_url") or target.get("cloud_url", "")).rstrip("/")
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.post(f"{url}{endpoint}")
            return JSONResponse(resp.json())
    except Exception as e:
        return JSONResponse({"status": "ERROR", "message": str(e)}, status_code=500)
