"""Fantasy Dynasty Agent command line.

  dynasty-agent league   [LEAGUE_ID]
  dynasty-agent keepers  [LEAGUE_ID]
  dynasty-agent values   [LEAGUE_ID] [--source stats|projections] [--season N] [--out values.json]
  dynasty-agent research "Player Name" [--pos RB --team LV]      (needs your own ANTHROPIC_API_KEY)

LEAGUE_ID defaults to SLEEPER_LEAGUE_ID from .env.
"""
from __future__ import annotations

import argparse
import json
import sys

from . import agent
from .config import MissingKeyError, Settings
from .service import LeagueService


def _league(args, s: Settings) -> str:
    lid = getattr(args, "league_id", None) or s.league_id
    if not lid:
        sys.exit("No league id: pass one or set SLEEPER_LEAGUE_ID in .env")
    return lid


def main(argv: list[str] | None = None) -> None:
    p = argparse.ArgumentParser(prog="dynasty-agent")
    sub = p.add_subparsers(dest="cmd", required=True)
    for name in ("league", "keepers"):
        sub.add_parser(name).add_argument("league_id", nargs="?")
    v = sub.add_parser("values")
    v.add_argument("league_id", nargs="?")
    v.add_argument("--source", choices=["stats", "projections"], default="stats")
    v.add_argument("--season", type=int)
    v.add_argument("--budget", type=int)
    v.add_argument("--out", help="write JSON for web/draft_board.html")
    r = sub.add_parser("research")
    r.add_argument("name")
    r.add_argument("--pos", default="")
    r.add_argument("--team", default="")
    args = p.parse_args(argv)

    s = Settings.load()
    svc = LeagueService(keeper_inflation=s.keeper_inflation)
    if args.cmd == "league":
        out = svc.summary(_league(args, s))
        out.pop("scoring_settings", None)
    elif args.cmd == "keepers":
        out = svc.keepers(_league(args, s))
    elif args.cmd == "values":
        out = svc.values(_league(args, s), args.season, args.source, args.budget or s.budget)
        if args.out:
            with open(args.out, "w") as f:
                json.dump(out, f)
            print(f"wrote {len(out['players'])} players to {args.out}")
            return
    else:
        try:
            out = agent.research_player(args.name, args.pos, args.team, settings=s)
        except MissingKeyError as e:
            sys.exit(str(e))
    print(json.dumps(out, indent=2, default=str))


if __name__ == "__main__":
    main()
