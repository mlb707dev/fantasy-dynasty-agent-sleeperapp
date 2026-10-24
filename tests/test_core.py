import pytest
from fastapi.testclient import TestClient

from dynasty_agent import agent
from dynasty_agent.config import MissingKeyError, Settings
from dynasty_agent.keepers import auction_prices, keeper_cost
from dynasty_agent.scoring import score_line
from dynasty_agent.service import LeagueService
from dynasty_agent.valuation import compute_values, fantasy_pos

from .conftest import DRAFT, LEAGUE, SCORING


def test_score_line_matches_league_rules():
    # 300 pass yd (12) + 2 pass TD (8) + 1 INT (-1) + 30 rush yd (3)
    assert score_line({"pass_yd": 300, "pass_td": 2, "pass_int": 1, "rush_yd": 30}, SCORING) == 22.0
    # 6 rec (6) + 80 yd (8) + 1 TD (6) = 20
    assert score_line({"rec": 6, "rec_yd": 80, "rec_td": 1}, SCORING) == 20.0
    # IDP: 8 solo (16) + 1 sack (6) + 1 TFL (2)
    assert score_line({"idp_tkl_solo": 8, "idp_sack": 1, "idp_tkl_loss": 1}, SCORING) == 24.0


def test_real_2025_prices_and_keeper_cost(prev_picks):
    prices = auction_prices(prev_picks)
    assert prices["12527"] == 53            # Ashton Jeanty went for $53 in 2025
    assert keeper_cost("12527", prices) == (53, 58)
    assert keeper_cost("unknown", prices) == (None, 5)
    assert keeper_cost("12527", prices, inflation=3) == (53, 56)


def test_fantasy_pos_maps_idp():
    assert fantasy_pos({"position": "OLB"}) == "LB"
    assert fantasy_pos({"position": "CB"}) == "DB"
    assert fantasy_pos({"position": "RB"}) == "RB"


def test_values_conserve_budget(client):
    out = LeagueService(client).values(LEAGUE)
    rows = out["players"]
    kept = [r for r in rows if r["kept"]]
    assert {r["player_id"] for r in kept} == {"7569", "12545", "11604"}
    assert all(r["value"] is None for r in kept)
    open_spots = 16 * 14 - len(kept)
    keeper_spend = sum(r["keeper_cost"] for r in kept)
    pool = sorted((r for r in rows if not r["kept"]), key=lambda r: -r["value"])[:open_spots]
    # top open_spots players' values ≈ total auction dollars (rounding tolerance)
    assert abs(sum(r["value"] for r in pool) - (16 * 200 - keeper_spend)) <= len(pool)
    # every positive-VORP player is priced above $1, and Pts/$ is consistent
    for r in pool:
        assert r["pts_per_dollar"] == round(r["pts"] / r["value"], 2)
    assert max(r["value"] for r in pool) < 200


def test_keepers_decode_names_and_costs(client):
    ks = {k["player_id"]: k for k in LeagueService(client).keepers(LEAGUE)}
    assert ks["7569"]["name"] == "Nico Collins" and ks["7569"]["roster_id"] == 9
    assert ks["11604"]["roster_id"] == 3  # picked up from is_keeper draft pick
    for k in ks.values():
        assert k["keeper_cost"] == (k["last_price"] or 0) + 5


def test_live_draft_budget(client):
    live = LeagueService(client).live_draft(DRAFT)
    assert live["status"] == "drafting"


def test_agent_requires_users_own_key(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "your-anthropic-api-key-here")
    s = Settings.load(env_file="/nonexistent")
    assert s.anthropic_api_key is None  # placeholder is treated as "not set"
    with pytest.raises(MissingKeyError, match="YOUR OWN key"):
        agent.research_player("Ashton Jeanty", settings=s)


@pytest.fixture
def api(client, monkeypatch):
    from dynasty_agent.api import app as appmod
    monkeypatch.setenv("DYNASTY_AGENT_API_TOKEN", "test-token-not-real")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "your-anthropic-api-key-here")
    appmod.settings.cache_clear()
    appmod.service.cache_clear()
    monkeypatch.setattr(appmod, "service", lambda: LeagueService(client))
    yield TestClient(appmod.app)
    appmod.settings.cache_clear()


def test_public_routes_need_no_auth(api):
    assert api.get("/health").json()["agent_configured"] is False
    r = api.get(f"/v1/public/league/{LEAGUE}/values")
    assert r.status_code == 200 and len(r.json()["players"]) > 100
    assert api.get(f"/v1/public/league/{LEAGUE}/keepers").status_code == 200


def test_private_routes_require_token(api):
    assert api.post("/v1/private/research/player", json={"name": "x"}).status_code == 401
    bad = {"Authorization": "Bearer wrong"}
    assert api.post("/v1/private/research/player", json={"name": "x"}, headers=bad).status_code == 401
    ok = {"Authorization": "Bearer test-token-not-real"}
    r = api.post("/v1/private/research/player", json={"name": "x"}, headers=ok)
    assert r.status_code == 503 and "YOUR OWN key" in r.json()["detail"]
    r = api.get(f"/v1/private/league/{LEAGUE}/my-keepers?roster_id=9", headers=ok)
    assert r.status_code == 200 and r.json()[0]["keeper_cost"] >= 5


def test_private_disabled_without_token(api, monkeypatch):
    from dynasty_agent.api import app as appmod
    monkeypatch.setenv("DYNASTY_AGENT_API_TOKEN", "your-private-api-token-here")
    appmod.settings.cache_clear()
    r = api.post("/v1/private/ask", json={"question": "x"}, headers={"Authorization": "Bearer your-private-api-token-here"})
    assert r.status_code == 503
