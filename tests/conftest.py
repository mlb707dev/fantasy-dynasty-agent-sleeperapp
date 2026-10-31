"""Offline Sleeper mock built from real 2025 draft data (Real Fantasy League 2026) + real player records.

Season stats are synthetic (deterministic) — only used to exercise the math.
"""
import gzip
import json
from pathlib import Path

import httpx
import pytest

from dynasty_agent.sleeper import SleeperClient

FX = Path(__file__).parent / "fixtures"
LEAGUE, PREV, DRAFT, PREV_DRAFT = "L2026", "PREV2025", "D2026", "PREVDRAFT2025"

SCORING = {"pass_yd": 0.04, "pass_td": 4, "pass_int": -1, "rush_yd": 0.1, "rush_td": 6,
           "rec": 1, "rec_yd": 0.1, "rec_td": 6, "fum_lost": -2,
           "idp_tkl_solo": 2, "idp_tkl_ast": 1, "idp_tkl_loss": 2, "idp_sack": 6, "idp_int": 6,
           "fgm": 3, "xpm": 1}
ROSTER_POS = ["QB", "RB", "RB", "WR", "WR", "TE", "FLEX", "K", "IDP_FLEX"] + ["BN"] * 5


def synthetic_stats(players: dict) -> dict:
    out = {}
    for pid, p in players.items():
        r = p.get("search_rank") or 9999
        if r > 600 or not p.get("active"):
            continue
        base = max(0.0, 600 - r)
        pos = p.get("position")
        s = {"gp": 17}
        if pos == "QB":
            s.update(pass_yd=base * 8, pass_td=base / 22, pass_int=5, rush_yd=base / 3)
        elif pos in ("RB", "WR", "TE"):
            s.update(rec=base / 8, rec_yd=base * 1.6, rec_td=base / 120, rush_yd=base if pos == "RB" else 0)
        elif pos == "K":
            s.update(fgm=base / 20, xpm=base / 15)
        elif pos in ("LB", "DL", "DB", "DE", "DT", "CB", "S"):
            s.update(idp_tkl_solo=base / 6, idp_tkl_ast=base / 12, idp_sack=base / 150)
        else:
            continue
        out[pid] = s
    return out


@pytest.fixture(scope="session")
def players():
    return json.loads(gzip.decompress((FX / "players_subset.json.gz").read_bytes()))


@pytest.fixture(scope="session")
def prev_picks():
    return json.loads(gzip.decompress((FX / "draft_picks_2025.json.gz").read_bytes()))


@pytest.fixture
def client(tmp_path, players, prev_picks):
    users = [{"user_id": f"u{i}", "display_name": f"owner{i}", "metadata": {"team_name": f"Team {i}"}}
             for i in range(1, 17)]
    rosters = [{"roster_id": i, "owner_id": f"u{i}", "players": [], "keepers": []} for i in range(1, 17)]
    rosters[8]["players"] = ["7569", "12545", "12527"]
    rosters[8]["keepers"] = ["7569", "12545"]  # Collins, Shough on roster 9
    current_picks = [{"roster_id": 3, "player_id": "11604", "is_keeper": True, "metadata": {}}]
    routes = {
        f"/v1/league/{LEAGUE}": {"name": "Test League", "season": "2026", "status": "pre_draft",
                                 "previous_league_id": PREV, "draft_id": DRAFT,
                                 "settings": {"num_teams": 16}, "roster_positions": ROSTER_POS,
                                 "scoring_settings": SCORING},
        f"/v1/league/{PREV}": {"previous_league_id": None},
        f"/v1/league/{LEAGUE}/users": users,
        f"/v1/league/{LEAGUE}/rosters": rosters,
        f"/v1/league/{PREV}/drafts": [{"draft_id": PREV_DRAFT, "type": "auction"}],
        f"/v1/draft/{PREV_DRAFT}/picks": prev_picks,
        f"/v1/draft/{DRAFT}/picks": current_picks,
        f"/v1/draft/{DRAFT}": {"status": "drafting", "settings": {"budget": 200}},
        "/v1/players/nfl": players,
        "/v1/stats/nfl/regular/2025": synthetic_stats(players),
    }

    def handler(req: httpx.Request):
        if req.url.path in routes:
            return httpx.Response(200, json=routes[req.url.path])
        return httpx.Response(404, json={"path": req.url.path})

    return SleeperClient(cache_dir=tmp_path, transport=httpx.MockTransport(handler))
