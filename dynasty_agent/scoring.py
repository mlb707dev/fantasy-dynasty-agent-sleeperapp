"""Score raw Sleeper stat lines with a league's own scoring_settings.

Sleeper stat keys (pass_yd, rec, idp_tkl_solo, ...) are the same keys used in
league["scoring_settings"], so fantasy points = sum(stat * weight) over the
shared keys. This reproduces custom/IDP scoring exactly, which generic
pts_ppr does not.
"""
from __future__ import annotations


def score_line(stats: dict[str, float], scoring: dict[str, float]) -> float:
    total = 0.0
    for key, weight in scoring.items():
        v = stats.get(key)
        if v:
            total += float(v) * float(weight)
    return round(total, 2)


def score_all(stats_by_player: dict[str, dict], scoring: dict[str, float]) -> dict[str, dict]:
    """Return {player_id: {"pts": float, "gp": int, "ppg": float}}."""
    out = {}
    for pid, line in stats_by_player.items():
        if not line:
            continue
        pts = score_line(line, scoring)
        gp = int(line.get("gp") or line.get("gms_active") or 0)
        out[pid] = {"pts": pts, "gp": gp, "ppg": round(pts / gp, 2) if gp else 0.0}
    return out
