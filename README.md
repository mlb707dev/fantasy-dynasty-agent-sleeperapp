# Fantasy Dynasty Agent — Sleeper

**Dynasty / keeper league prep & research agent for the Sleeper app, built for auction drafts.**

Fantasy Dynasty Agent pulls your league straight from Sleeper, scores every player with *your league's own scoring settings* (custom PPR, IDP, anything), decodes every team's keepers and keeper costs, and prices the whole player pool in auction dollars for your exact team count, roster and budget. An optional Claude-powered research agent checks injuries, arrests/suspensions, depth charts and role news with cited sources.

| Piece | What it does |
|---|---|
| `dynasty_agent/sleeper.py` | Client for Sleeper's public, keyless API (league, rosters, users, drafts, picks, players, stats, projections) |
| `dynasty_agent/scoring.py` | Scores raw stat lines with the league's `scoring_settings` — reproduces custom/IDP scoring exactly |
| `dynasty_agent/keepers.py` | Last-year auction prices, keeper cost (`last price + $5` by default), league-wide keeper decoding, keeper surplus ranking |
| `dynasty_agent/valuation.py` | League-wide starter fill → replacement level → VORP → auction dollars (net of keeper spend and one-dollar minimums) → points per dollar |
| `dynasty_agent/agent.py` | Claude research agent with web search (needs **your own** Anthropic key) |
| `dynasty_agent/api/app.py` | HTTP API with **public** and **private** routes |
| `web/draft_board.html` | Live auction board: sortable (rank, player, pos, est. value, pts, PPG, VORP, points per dollar), sticky header, mark drafted with price → My team / Other team, auto-filling roster board, budget left & max bid |

---

## API keys — bring your own

**This repo contains no API keys and never should.** Every key in `.env.example` is a placeholder.

| Key | Needed for | Where to get it |
|---|---|---|
| *(none)* | League data, keepers, values, draft board | Sleeper's API is public and keyless |
| `ANTHROPIC_API_KEY` | Research agent only (`/v1/private/research/player`, `/v1/private/ask`, `dynasty-agent research`) | Your own key: https://console.anthropic.com/ → Settings → API Keys |
| `DYNASTY_AGENT_API_TOKEN` | Unlocks the private API routes | Make one up: `python -c "import secrets; print(secrets.token_urlsafe(32))"` |

If a key is missing or still a placeholder, Fantasy Dynasty Agent doesn't fail silently — the agent and private routes return a message asking you to set your own key.

> **Using this project? Ask for — and use — your own keys.** Don't share keys, don't paste them into issues or code, and never commit `.env` (it's already in `.gitignore`).

---

## Quick start

```bash
git clone https://github.com/mlb707dev/fantasy-dynasty-agent-sleeperapp.git && cd fantasy-dynasty-agent-sleeperapp
python -m venv .venv && source .venv/bin/activate
pip install -e ".[api,agent]"
cp .env.example .env          # then edit .env with YOUR league id (and your own keys if using the agent)
```

### CLI

```bash
dynasty-agent league                          # league summary (uses SLEEPER_LEAGUE_ID from .env)
dynasty-agent keepers                         # every team's keepers + keeper cost
dynasty-agent values --out values.json        # auction values from last season's actual stats
dynasty-agent values --source projections     # ...or from Sleeper's current-season projections
dynasty-agent research "Ashton Jeanty" --pos RB --team LV   # needs your ANTHROPIC_API_KEY
```

### API

```bash
uvicorn dynasty_agent.api.app:app --reload    # http://localhost:8000/docs for interactive docs
```

**Public routes** — no auth, read-only, free to run:

| Method | Route | Returns |
|---|---|---|
| GET | `/health` | Whether the agent and private API are configured |
| GET | `/v1/public/league/{league_id}` | League summary, teams, roster slots, scoring |
| GET | `/v1/public/league/{league_id}/keepers` | All keepers with last price and keeper cost |
| GET | `/v1/public/league/{league_id}/values?source=stats\|projections&budget=200` | Full priced player pool |
| GET | `/v1/public/draft/{draft_id}/live` | Live auction picks and each team's budget left |

**Private routes** — require `Authorization: Bearer <DYNASTY_AGENT_API_TOKEN>`:

| Method | Route | Returns |
|---|---|---|
| POST | `/v1/private/research/player` `{"name","pos","team"}` | Cited risk report: injury, legal, role, outlook |
| POST | `/v1/private/ask` `{"question","league_id","include_values"}` | Strategy answer with league values as context |
| GET | `/v1/private/league/{league_id}/my-keepers?roster_id=9` | Your roster ranked by keeper surplus (auction value − keeper cost) |

Private routes are gated because the agent spends the server owner's Anthropic credits.

### Draft board

Open `web/draft_board.html` in a browser, then either:
- enter your API URL (e.g. `http://localhost:8000`) + league ID and click **Load**, or
- click **Open values.json** and pick the file from `dynasty-agent values --out values.json`.

Click any player to mark them drafted with the price → **My team** or **Other team**. Your roster board fills automatically and shows budget left and max bid. Draft state is saved in your browser.

---

## How values are calculated

1. Fill every team's starting lineup league-wide — dedicated slots first, then FLEX / IDP_FLEX / SUPER_FLEX from the best remaining eligible players.
2. **Replacement level** per position = best player who didn't make a starting lineup. **VORP** = points − replacement.
3. **Auction dollars** = teams × budget − all keeper spend. Each open roster spot costs at least $1; the rest is split by VORP. Kept players fill starting slots but are removed from the auction pool.
4. **Pts/$** = points ÷ value.

Values reflect one season of stats or projections. They don't account for injuries, suspensions, age curves or dynasty value — that's what the research agent and your own judgment are for.

## Public vs private

- **This repo (public-safe):** generic code, no league-specific data, no keys.
- **`private/`** (git-ignored): your own boards, notes and exports stay local.
- **`.env`** (git-ignored): your league ID and your keys.

## Tests

```bash
pip install -e ".[dev]" && pytest
```

Tests run offline against a mocked Sleeper API built from real 2025 auction picks and real player records; season stat lines in the tests are synthetic.

## Data sources

- Sleeper API docs: https://docs.sleeper.com/ — `/projections` is undocumented and may change.
- Anthropic web search tool: https://platform.claude.com/docs/en/agents-and-tools/tool-use/web-search-tool
