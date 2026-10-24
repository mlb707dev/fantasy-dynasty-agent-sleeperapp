"""Fantasy Dynasty Agent HTTP API.

PUBLIC routes  (/v1/public/*)  — no auth. Read-only Sleeper analysis: league
    summary, keepers + keeper costs, auction values, live draft state. Costs
    nothing to run; safe to expose.
PRIVATE routes (/v1/private/*) — require `Authorization: Bearer <DYNASTY_AGENT_API_TOKEN>`.
    Claude research agent (spends the server owner's Anthropic credits) and
    personal "my team" views.

Run:  uvicorn dynasty_agent.api.app:app --reload
"""
from __future__ import annotations

import hmac
from functools import lru_cache

from fastapi import APIRouter, Depends, FastAPI, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from .. import agent
from ..config import MissingKeyError, Settings
from ..keepers import keeper_candidates
from ..service import LeagueService


@lru_cache
def settings() -> Settings:
    return Settings.load()


@lru_cache
def service() -> LeagueService:
    return LeagueService(keeper_inflation=settings().keeper_inflation)


def require_token(authorization: str | None = Header(default=None)) -> None:
    s = settings()
    if not s.api_token:
        raise HTTPException(503, "Private API disabled: set your own DYNASTY_AGENT_API_TOKEN in .env")
    supplied = (authorization or "").removeprefix("Bearer ").strip()
    if not hmac.compare_digest(supplied, s.api_token):
        raise HTTPException(401, "Invalid or missing bearer token")


app = FastAPI(title="Fantasy Dynasty Agent", version="0.1.0",
              description="Sleeper dynasty/keeper auction prep & research agent")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["GET", "POST"],
                   allow_headers=["*"])

public = APIRouter(prefix="/v1/public", tags=["public"])
private = APIRouter(prefix="/v1/private", tags=["private"], dependencies=[Depends(require_token)])


@app.get("/health")
def health():
    s = settings()
    return {"ok": True, "agent_configured": bool(s.anthropic_api_key),
            "private_api_enabled": bool(s.api_token)}


# ── public ──────────────────────────────────────────────────────────────────
@public.get("/league/{league_id}")
def league(league_id: str):
    return service().summary(league_id)


@public.get("/league/{league_id}/keepers")
def keepers(league_id: str):
    return service().keepers(league_id)


@public.get("/league/{league_id}/values")
def values(league_id: str, source: str = "stats", season: int | None = None, budget: int = 200):
    if source not in ("stats", "projections"):
        raise HTTPException(400, "source must be 'stats' or 'projections'")
    return service().values(league_id, season, source, budget)


@public.get("/draft/{draft_id}/live")
def live(draft_id: str):
    return service().live_draft(draft_id)


# ── private ─────────────────────────────────────────────────────────────────
class ResearchIn(BaseModel):
    name: str
    pos: str = ""
    team: str = ""
    season: int | None = None
    context: str = ""


class AskIn(BaseModel):
    question: str
    league_id: str | None = None
    include_values: bool = False


def _agent_call(fn, *a, **kw):
    try:
        return fn(*a, settings=settings(), **kw)
    except MissingKeyError as e:
        raise HTTPException(503, str(e))


@private.post("/research/player")
def research(body: ResearchIn):
    return _agent_call(agent.research_player, body.name, body.pos, body.team,
                       body.season or "", body.context)


@private.post("/ask")
def ask(body: AskIn):
    ctx = None
    if body.league_id and body.include_values:
        v = service().values(body.league_id)
        ctx = {"values_top150": v["players"][:150]}
    return _agent_call(agent.ask, body.question, ctx)


@private.get("/league/{league_id}/my-keepers")
def my_keepers(league_id: str, roster_id: int | None = None):
    s = settings()
    rid = roster_id or s.my_roster_id
    if not rid:
        raise HTTPException(400, "Pass roster_id or set SLEEPER_MY_ROSTER_ID in .env")
    svc = service()
    roster = next((t for t in svc.summary(league_id)["teams"] if t["roster_id"] == rid), None)
    if not roster:
        raise HTTPException(404, f"roster {rid} not found")
    vals = {r["player_id"]: r["value"] or 0 for r in svc.values(league_id)["players"]}
    return keeper_candidates(roster, svc.sc.players(), svc.last_auction_prices(league_id),
                             vals, s.keeper_inflation)


app.include_router(public)
app.include_router(private)
