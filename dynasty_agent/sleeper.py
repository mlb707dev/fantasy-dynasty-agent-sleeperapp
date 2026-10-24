"""Thin client for Sleeper's public, keyless, read-only API.

Docs: https://docs.sleeper.com/
The full player dump (/players/nfl, ~5 MB) is cached to disk; Sleeper asks
callers to fetch it at most once per day.
"""
from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

import httpx

BASE = "https://api.sleeper.app/v1"
PLAYERS_TTL = 24 * 3600


class SleeperClient:
    def __init__(self, cache_dir: str | Path = ".dynasty_agent_cache", timeout: float = 30.0,
                 transport: httpx.BaseTransport | None = None):
        self.cache = Path(cache_dir)
        self.cache.mkdir(parents=True, exist_ok=True)
        self._http = httpx.Client(base_url=BASE, timeout=timeout, transport=transport)

    def _get(self, path: str) -> Any:
        r = self._http.get(path)
        r.raise_for_status()
        return r.json()

    # ── league ──────────────────────────────────────────────────────────────
    def league(self, league_id: str) -> dict:
        return self._get(f"/league/{league_id}")

    def rosters(self, league_id: str) -> list[dict]:
        return self._get(f"/league/{league_id}/rosters")

    def users(self, league_id: str) -> list[dict]:
        return self._get(f"/league/{league_id}/users")

    def drafts(self, league_id: str) -> list[dict]:
        return self._get(f"/league/{league_id}/drafts")

    def draft(self, draft_id: str) -> dict:
        return self._get(f"/draft/{draft_id}")

    def draft_picks(self, draft_id: str) -> list[dict]:
        return self._get(f"/draft/{draft_id}/picks")

    def traded_picks(self, league_id: str) -> list[dict]:
        return self._get(f"/league/{league_id}/traded_picks")

    def league_history(self, league_id: str, depth: int = 5) -> list[dict]:
        """Current league followed by previous seasons via previous_league_id."""
        out, lid = [], league_id
        while lid and lid != "0" and len(out) < depth:
            lg = self.league(lid)
            out.append(lg)
            lid = lg.get("previous_league_id")
        return out

    # ── players & stats ─────────────────────────────────────────────────────
    def players(self, force: bool = False) -> dict[str, dict]:
        f = self.cache / "players_nfl.json"
        if not force and f.exists() and time.time() - f.stat().st_mtime < PLAYERS_TTL:
            return json.loads(f.read_text())
        data = self._get("/players/nfl")
        f.write_text(json.dumps(data))
        return data

    def season_stats(self, season: int, season_type: str = "regular") -> dict[str, dict]:
        return self._get(f"/stats/nfl/{season_type}/{season}")

    def season_projections(self, season: int, season_type: str = "regular") -> dict[str, dict]:
        """Undocumented but long-standing endpoint; may change without notice."""
        return self._get(f"/projections/nfl/{season_type}/{season}")

    def state(self) -> dict:
        return self._get("/state/nfl")
