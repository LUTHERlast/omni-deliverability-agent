import os
import json
import asyncio
import datetime
from typing import List, Dict, Any, Optional
import httpx

REGISTRY_PATHS = [
    os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "agents_registry.json")),
    os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "data", "agents_registry.json")),
    os.path.abspath("agents_registry.json")
]

def get_registry_file_path() -> str:
    for p in REGISTRY_PATHS:
        if os.path.exists(p):
            return p
    # Default to data directory
    p = REGISTRY_PATHS[1]
    os.makedirs(os.path.dirname(p), exist_ok=True)
    return p

def load_agents_registry() -> List[Dict[str, Any]]:
    path = get_registry_file_path()
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        print(f"[Master Registry Warning] Could not read registry from {path}: {e}")
        return []

def save_agents_registry(agents: List[Dict[str, Any]]) -> bool:
    success = False
    for p in REGISTRY_PATHS[:2]:
        try:
            os.makedirs(os.path.dirname(p), exist_ok=True)
            with open(p, "w", encoding="utf-8") as f:
                json.dump(agents, f, indent=2)
            success = True
        except Exception:
            pass
    return success

class MasterFleetManager:
    """Aggregates real-time KPIs, health, and events across all registered autonomous agents."""

    def __init__(self):
        self.usd_to_aed_rate = 3.6725

    def get_registered_agents(self) -> List[Dict[str, Any]]:
        return load_agents_registry()

    def add_agent(self, agent_data: Dict[str, Any]) -> Dict[str, Any]:
        agents = load_agents_registry()
        # Generate ID if not present
        if not agent_data.get("id"):
            agent_data["id"] = f"agent-{len(agents) + 1}"
        agent_data["created_at"] = datetime.datetime.utcnow().isoformat()
        
        # Ensure default fields
        agent_data.setdefault("status", "RUNNING")
        agent_data.setdefault("stats_endpoint", "/api/stats")
        agent_data.setdefault("health_endpoint", "/api/health")
        agent_data.setdefault("events_endpoint", "/api/events")
        agent_data.setdefault("dashboard_path", "/")
        agent_data.setdefault("currency", "USD")
        agent_data.setdefault("currency_symbol", "$")
        agent_data.setdefault("usd_exchange_rate", 1.0)
        agent_data.setdefault("theme_color", "indigo")
        agent_data.setdefault("icon", "sparkles")

        # Check if already exists by id or code
        existing = next((a for a in agents if a["id"] == agent_data["id"] or a.get("code") == agent_data.get("code")), None)
        if existing:
            existing.update(agent_data)
        else:
            agents.append(agent_data)

        save_agents_registry(agents)
        return agent_data

    async def ping_agent_stats(self, agent: Dict[str, Any]) -> Dict[str, Any]:
        """Pings a single agent's live endpoints and returns enriched metrics."""
        # Try local_url first, fallback to cloud_url
        base_urls = []
        if agent.get("local_url"):
            base_urls.append(agent["local_url"].rstrip("/"))
        if agent.get("cloud_url") and agent.get("cloud_url") not in base_urls:
            base_urls.append(agent["cloud_url"].rstrip("/"))

        stats_path = agent.get("stats_endpoint", "/api/stats")
        health_path = agent.get("health_endpoint", "/api/health")
        events_path = agent.get("events_endpoint", "/api/events")

        agent_result = dict(agent)
        agent_result["is_online"] = False
        agent_result["latency_ms"] = None
        agent_result["live_stats"] = {}
        agent_result["recent_events"] = []

        for base_url in base_urls:
            try:
                start_t = datetime.datetime.utcnow()
                async with httpx.AsyncClient(timeout=3.0) as client:
                    health_resp = await client.get(f"{base_url}{health_path}")
                    if health_resp.status_code == 200:
                        elapsed = (datetime.datetime.utcnow() - start_t).total_seconds() * 1000
                        agent_result["is_online"] = True
                        agent_result["latency_ms"] = round(elapsed, 1)
                        agent_result["active_url"] = base_url

                        # Fetch rich stats
                        stats_resp = await client.get(f"{base_url}{stats_path}")
                        if stats_resp.status_code == 200:
                            agent_result["live_stats"] = stats_resp.json()

                        # Fetch recent events
                        try:
                            events_resp = await client.get(f"{base_url}{events_path}?limit=6")
                            if events_resp.status_code == 200:
                                agent_result["recent_events"] = events_resp.json()
                        except Exception:
                            pass

                        break
            except Exception:
                continue

        return agent_result

    async def get_aggregated_portfolio(self) -> Dict[str, Any]:
        """Queries all registered agents concurrently and computes overall empire performance."""
        agents = load_agents_registry()
        
        # Concurrent pings
        tasks = [self.ping_agent_stats(ag) for ag in agents]
        agent_results = await asyncio.gather(*tasks, return_exceptions=True)

        processed_agents = []
        all_events = []

        total_pipeline_usd = 0.0
        total_pipeline_aed = 0.0
        total_revenue_usd = 0.0
        total_revenue_aed = 0.0
        total_leads = 0
        total_emails = 0
        total_hot_leads = 0
        total_won = 0
        online_count = 0

        for res in agent_results:
            if isinstance(res, Exception):
                continue

            processed_agents.append(res)
            if res.get("is_online"):
                online_count += 1

            stats = res.get("live_stats", {})
            curr = res.get("currency", "USD").upper()
            rate = float(res.get("usd_exchange_rate", 1.0)) # 1 local curr = X USD (or if USD rate = 1.0)
            
            # Raw pipeline & revenue
            raw_pipeline = float(stats.get("pipeline_value") or 0.0)
            raw_revenue = float(stats.get("actual_revenue") or 0.0)
            
            # Normalize to USD and AED
            if curr == "AED":
                pipe_usd = raw_pipeline / self.usd_to_aed_rate
                pipe_aed = raw_pipeline
                rev_usd = raw_revenue / self.usd_to_aed_rate
                rev_aed = raw_revenue
            else: # USD
                pipe_usd = raw_pipeline
                pipe_aed = raw_pipeline * self.usd_to_aed_rate
                rev_usd = raw_revenue
                rev_aed = raw_revenue * self.usd_to_aed_rate

            total_pipeline_usd += pipe_usd
            total_pipeline_aed += pipe_aed
            total_revenue_usd += rev_usd
            total_revenue_aed += rev_aed

            total_leads += int(stats.get("total_leads") or 0)
            total_emails += int(stats.get("total_emails") or 0)
            total_hot_leads += int(stats.get("hot_leads_count") or 0)
            total_won += int(stats.get("won_count") or 0)

            # Collect events with agent provenance
            for ev in res.get("recent_events", []):
                ev_copy = dict(ev)
                ev_copy["agent_id"] = res.get("id")
                ev_copy["agent_name"] = res.get("name")
                ev_copy["theme_color"] = res.get("theme_color", "indigo")
                all_events.append(ev_copy)

        # Sort all events chronologically descending
        all_events.sort(key=lambda x: x.get("timestamp") or "", reverse=True)

        system_status = "ALL_SYSTEMS_OPERATIONAL" if online_count == len(agents) else ("DEGRADED" if online_count > 0 else "OFFLINE")

        return {
            "summary": {
                "total_pipeline_usd": round(total_pipeline_usd, 2),
                "total_pipeline_aed": round(total_pipeline_aed, 2),
                "total_revenue_usd": round(total_revenue_usd, 2),
                "total_revenue_aed": round(total_revenue_aed, 2),
                "total_leads": total_leads,
                "total_emails": total_emails,
                "total_hot_leads": total_hot_leads,
                "total_won": total_won,
                "online_agents": online_count,
                "total_agents": len(agents),
                "system_status": system_status,
                "last_refreshed": datetime.datetime.utcnow().isoformat()
            },
            "agents": processed_agents,
            "recent_events": all_events[:25]
        }

master_fleet = MasterFleetManager()
