"""Keeper decoding and keeper-cost math for auction keeper leagues.

Rule supported out of the box: keeper cost = last auction price + inflation
(default +$5). Players acquired off waivers (no auction price) use
`undrafted_base` (default $0, so they cost $0 + inflation).
"""
from __future__ import annotations

from dataclasses import dataclass, asdict


@dataclass
class Keeper:
    roster_id: int
    player_id: str
    name: str
    position: str
    team: str | None
    last_price: int | None
    keeper_cost: int

    def to_dict(self) -> dict:
        return asdict(self)


def auction_prices(picks: list[dict]) -> dict[str, int]:
    """{player_id: price} from a completed auction draft's picks."""
    prices = {}
    for p in picks:
        amt = (p.get("metadata") or {}).get("amount")
        if amt not in (None, ""):
            prices[str(p["player_id"])] = int(amt)
    return prices


def keeper_cost(player_id: str, last_prices: dict[str, int], inflation: int = 5,
                undrafted_base: int = 0) -> tuple[int | None, int]:
    last = last_prices.get(str(player_id))
    return last, (last if last is not None else undrafted_base) + inflation


def current_keepers(rosters: list[dict], current_picks: list[dict] | None = None) -> dict[int, list[str]]:
    """Keepers per roster_id.

    Sources, merged: each roster's `keepers` list (set when owners submit
    keepers in Sleeper) and any pick flagged is_keeper in the current draft.
    """
    out: dict[int, set[str]] = {}
    for r in rosters:
        for pid in r.get("keepers") or []:
            out.setdefault(int(r["roster_id"]), set()).add(str(pid))
    for p in current_picks or []:
        if p.get("is_keeper"):
            out.setdefault(int(p["roster_id"]), set()).add(str(p["player_id"]))
    return {k: sorted(v) for k, v in out.items()}


def decode_keepers(keepers_by_roster: dict[int, list[str]], players: dict[str, dict],
                   last_prices: dict[str, int], inflation: int = 5) -> list[Keeper]:
    out = []
    for rid, pids in sorted(keepers_by_roster.items()):
        for pid in pids:
            pl = players.get(pid, {})
            last, cost = keeper_cost(pid, last_prices, inflation)
            out.append(Keeper(rid, pid, pl.get("full_name") or pid, pl.get("position") or "?",
                              pl.get("team"), last, cost))
    return out


def keeper_candidates(roster: dict, players: dict[str, dict], last_prices: dict[str, int],
                      auction_values: dict[str, float], inflation: int = 5) -> list[dict]:
    """Rank a roster's players by keeper surplus = projected auction value - keeper cost."""
    rows = []
    for pid in roster.get("players") or []:
        pid = str(pid)
        pl = players.get(pid, {})
        last, cost = keeper_cost(pid, last_prices, inflation)
        val = float(auction_values.get(pid, 0))
        rows.append({
            "player_id": pid, "name": pl.get("full_name") or pid, "position": pl.get("position"),
            "team": pl.get("team"), "last_price": last, "keeper_cost": cost,
            "auction_value": round(val, 1), "surplus": round(val - cost, 1),
        })
    return sorted(rows, key=lambda r: r["surplus"], reverse=True)
