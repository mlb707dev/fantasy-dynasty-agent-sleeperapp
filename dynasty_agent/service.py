"""High-level league report: everything the API, CLI and draft board use."""
from __future__ import annotations

from .keepers import auction_prices, current_keepers, decode_keepers
from .scoring import score_all
from .sleeper import SleeperClient
from .valuation import compute_values


class LeagueService:
    def __init__(self, client: SleeperClient | None = None, keeper_inflation: int = 5):
        self.sc = client or SleeperClient()
        self.inflation = keeper_inflation

    def summary(self, league_id: str) -> dict:
        lg = self.sc.league(league_id)
        users = {u["user_id"]: u for u in self.sc.users(league_id)}
        teams = []
        for r in self.sc.rosters(league_id):
            u = users.get(r.get("owner_id") or "", {})
            teams.append({
                "roster_id": r["roster_id"],
                "owner": u.get("display_name"),
                "team_name": (u.get("metadata") or {}).get("team_name") or u.get("display_name"),
                "players": r.get("players") or [],
                "keepers": r.get("keepers") or [],
            })
        s = lg.get("settings") or {}
        return {
            "league_id": league_id, "name": lg.get("name"), "season": lg.get("season"),
            "status": lg.get("status"), "num_teams": s.get("num_teams") or len(teams),
            "roster_positions": lg.get("roster_positions") or [],
            "scoring_settings": lg.get("scoring_settings") or {},
            "previous_league_id": lg.get("previous_league_id"),
            "draft_id": lg.get("draft_id"), "teams": teams,
        }

    def last_auction_prices(self, league_id: str) -> dict[str, int]:
        """Prices from the most recent completed auction in the previous season."""
        prev = self.sc.league(league_id).get("previous_league_id")
        if not prev or prev == "0":
            return {}
        prices: dict[str, int] = {}
        for d in self.sc.drafts(prev):
            if d.get("type") == "auction":
                prices.update(auction_prices(self.sc.draft_picks(d["draft_id"])))
        return prices

    def keepers(self, league_id: str) -> list[dict]:
        summ = self.summary(league_id)
        picks = self.sc.draft_picks(summ["draft_id"]) if summ.get("draft_id") else []
        rosters = [{"roster_id": t["roster_id"], "keepers": t["keepers"]} for t in summ["teams"]]
        by_roster = current_keepers(rosters, picks)
        names = {t["roster_id"]: t["team_name"] for t in summ["teams"]}
        decoded = decode_keepers(by_roster, self.sc.players(), self.last_auction_prices(league_id),
                                 self.inflation)
        return [{**k.to_dict(), "team_name": names.get(k.roster_id)} for k in decoded]

    def values(self, league_id: str, season: int | None = None, source: str = "stats",
               budget: int = 200) -> dict:
        """source='stats' → last season's actual stats; 'projections' → Sleeper projections."""
        summ = self.summary(league_id)
        season = season or (int(summ["season"]) - 1 if source == "stats" else int(summ["season"]))
        raw = (self.sc.season_stats(season) if source == "stats"
               else self.sc.season_projections(season))
        pts = score_all(raw, summ["scoring_settings"])
        kept = {k["player_id"]: k["keeper_cost"] for k in self.keepers(league_id)}
        rows = compute_values(self.sc.players(), pts, summ["roster_positions"],
                              summ["num_teams"], budget, kept)
        return {"league_id": league_id, "season": season, "source": source,
                "budget": budget, "num_teams": summ["num_teams"],
                "roster_positions": summ["roster_positions"], "players": rows}

    def live_draft(self, draft_id: str) -> dict:
        """Current state of a live auction: who bought whom, for how much, budget left."""
        d = self.sc.draft(draft_id)
        picks = self.sc.draft_picks(draft_id)
        budget = int((d.get("settings") or {}).get("budget") or 200)
        spent: dict[int, int] = {}
        for p in picks:
            amt = int((p.get("metadata") or {}).get("amount") or 0)
            spent[p["roster_id"]] = spent.get(p["roster_id"], 0) + amt
        return {"draft_id": draft_id, "status": d.get("status"), "picks": picks,
                "budget_left": {rid: budget - s for rid, s in spent.items()}}
