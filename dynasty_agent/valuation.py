"""VORP and auction-dollar values calibrated to a specific league.

Method
1. Fill every team's starting lineup league-wide (dedicated slots first, then
   flex slots from the best remaining eligible players).
2. Replacement level per position = best player at that position who did NOT
   make a starting lineup. VORP = points - replacement (floored at 0).
3. Auction dollars = teams x budget - keeper spend. Every open roster spot
   costs at least $1; the remaining surplus is split across non-kept players
   in proportion to VORP.  value = $1 + surplus x VORP / sum(VORP).
4. Pts/$ = points / value.

Kept players occupy starting slots (they are real starters) but are excluded
from the auction pool and from the dollar split.
"""
from __future__ import annotations

from collections import Counter

SLOT_ELIGIBILITY: dict[str, set[str]] = {
    "QB": {"QB"}, "RB": {"RB"}, "WR": {"WR"}, "TE": {"TE"}, "K": {"K"}, "DEF": {"DEF"},
    "DL": {"DL"}, "LB": {"LB"}, "DB": {"DB"},
    "FLEX": {"RB", "WR", "TE"}, "WRRB_FLEX": {"RB", "WR"}, "REC_FLEX": {"WR", "TE"},
    "SUPER_FLEX": {"QB", "RB", "WR", "TE"}, "IDP_FLEX": {"DL", "LB", "DB"},
}
NON_STARTING = {"BN", "IR", "TAXI"}
IDP_MAP = {"DE": "DL", "DT": "DL", "NT": "DL", "ILB": "LB", "OLB": "LB", "MLB": "LB",
           "CB": "DB", "S": "DB", "SS": "DB", "FS": "DB"}


def fantasy_pos(player: dict) -> str | None:
    fps = player.get("fantasy_positions") or []
    pos = player.get("position")
    for cand in [pos, *fps]:
        if not cand:
            continue
        cand = IDP_MAP.get(cand, cand)
        if cand in {"QB", "RB", "WR", "TE", "K", "DEF", "DL", "LB", "DB"}:
            return cand
    return None


def starters_by_slot(roster_positions: list[str]) -> Counter:
    return Counter(s for s in roster_positions if s not in NON_STARTING)


def compute_values(
    players: dict[str, dict],
    points: dict[str, dict],
    roster_positions: list[str],
    num_teams: int,
    budget: int = 200,
    kept: dict[str, int] | None = None,
) -> list[dict]:
    """Return one row per scored player, sorted by auction value.

    points: {player_id: {"pts", "gp", "ppg"}} (see scoring.score_all)
    kept:   {player_id: keeper_cost} for every keeper in the league
    """
    kept = {str(k): v for k, v in (kept or {}).items()}
    pool = []
    for pid, sc in points.items():
        pl = players.get(pid)
        if not pl or sc.get("pts", 0) <= 0:
            continue
        pos = fantasy_pos(pl)
        if pos:
            pool.append((pid, pos, float(sc["pts"])))
    pool.sort(key=lambda x: x[2], reverse=True)

    slots = starters_by_slot(roster_positions)
    used: set[str] = set()
    # dedicated slots first, then flex slots from most to least restrictive
    order = sorted(slots, key=lambda s: len(SLOT_ELIGIBILITY.get(s, {s})))
    for slot in order:
        elig = SLOT_ELIGIBILITY.get(slot, {slot})
        need = slots[slot] * num_teams
        for pid, pos, _ in pool:
            if need == 0:
                break
            if pid not in used and pos in elig:
                used.add(pid)
                need -= 1

    replacement: dict[str, float] = {}
    for pid, pos, pts in pool:
        if pid not in used and pos not in replacement:
            replacement[pos] = pts

    rows = []
    for pid, pos, pts in pool:
        vorp = max(0.0, pts - replacement.get(pos, 0.0))
        rows.append({"player_id": pid, "pos": pos, "pts": pts, "vorp": round(vorp, 1),
                     "starter": pid in used, "kept": pid in kept})

    roster_size = len(roster_positions)
    keeper_spend = sum(kept.values())
    open_spots = num_teams * roster_size - len(kept)
    surplus = max(0, num_teams * budget - keeper_spend - open_spots)
    vorp_pool = sum(r["vorp"] for r in rows if not r["kept"])

    for r in rows:
        pl, sc = players[r["player_id"]], points[r["player_id"]]
        r.update(name=pl.get("full_name") or f'{pl.get("first_name","")} {pl.get("last_name","")}'.strip(),
                 team=pl.get("team"), age=pl.get("age"), injury_status=pl.get("injury_status"),
                 gp=sc.get("gp", 0), ppg=sc.get("ppg", 0.0))
        if r["kept"]:
            r["value"] = None
            r["keeper_cost"] = kept[r["player_id"]]
        else:
            share = r["vorp"] / vorp_pool if vorp_pool else 0
            r["value"] = round(1 + surplus * share) if r["vorp"] > 0 else 1
        r["pts_per_dollar"] = round(r["pts"] / r["value"], 2) if r["value"] else None

    rows.sort(key=lambda r: (r["kept"], -(r["value"] or 0), -r["pts"]))
    for i, r in enumerate(rows, 1):
        r["rank"] = i
    return rows


def replacement_levels(rows: list[dict]) -> dict[str, float]:
    """Recover replacement points per position from computed rows."""
    out: dict[str, float] = {}
    for r in rows:
        if r["vorp"] > 0:
            out[r["pos"]] = r["pts"] - r["vorp"]
    return out
