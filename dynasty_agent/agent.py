"""Claude-powered research agent (optional).

Requires the USER'S OWN Anthropic API key in ANTHROPIC_API_KEY. If it's
missing, every call raises MissingKeyError with instructions — nothing is
ever hard-coded or shared.

Uses Anthropic's server-side web search tool so findings are current and
cited. Docs: https://platform.claude.com/docs/en/agents-and-tools/tool-use/web-search-tool
"""
from __future__ import annotations

import json
import re

from .config import Settings

WEB_SEARCH_TOOL = {"type": "web_search_20250305", "name": "web_search", "max_uses": 8}

SYSTEM = """You are Fantasy Dynasty Agent, a fantasy football research analyst for Sleeper dynasty/keeper \
AUCTION leagues. Accuracy is the priority: only state facts you found in sources during \
this session, cite every claim, check more than one source, and say plainly when you \
could not verify something. Never invent stats, injuries, arrests, or depth-chart roles."""

PLAYER_PROMPT = """Research {name} ({pos}, {team}) for a {season} fantasy auction.
Cover, with dates: current injury status and history; any arrests, suspensions or \
pending league discipline; depth-chart role and competition; coaching/scheme or team \
changes; contract situation (keeper/dynasty relevance).
League context: {context}

Reply with ONLY a JSON object:
{{"player": str, "risk_level": "low"|"medium"|"high", "injury": str, "legal": str,
  "role": str, "outlook": str, "auction_note": str,
  "sources": [{{"title": str, "url": str}}], "unverified": [str]}}"""


def _client(settings: Settings):
    import anthropic  # imported lazily so the rest of Fantasy Dynasty Agent works without it
    return anthropic.Anthropic(api_key=settings.require_anthropic_key())


def _text(resp) -> str:
    return "".join(b.text for b in resp.content if getattr(b, "type", "") == "text")


def _citations(resp) -> list[dict]:
    seen, out = set(), []
    for b in resp.content:
        for c in getattr(b, "citations", None) or []:
            url = getattr(c, "url", None)
            if url and url not in seen:
                seen.add(url)
                out.append({"title": getattr(c, "title", url), "url": url})
    return out


def _parse_json(text: str) -> dict | None:
    m = re.search(r"\{.*\}", text, re.S)
    if not m:
        return None
    try:
        return json.loads(m.group(0))
    except json.JSONDecodeError:
        return None


def research_player(name: str, pos: str = "", team: str = "", season: int | str = "",
                    context: str = "", settings: Settings | None = None) -> dict:
    s = settings or Settings.load()
    resp = _client(s).messages.create(
        model=s.model, max_tokens=4000, system=SYSTEM, tools=[WEB_SEARCH_TOOL],
        messages=[{"role": "user", "content": PLAYER_PROMPT.format(
            name=name, pos=pos or "?", team=team or "?", season=season or "upcoming",
            context=context or "16-team PPR keeper auction, $200 budget")}],
    )
    text = _text(resp)
    data = _parse_json(text) or {"player": name, "raw": text}
    cites = _citations(resp)
    if cites:
        known = {x.get("url") for x in data.get("sources", [])}
        data.setdefault("sources", []).extend(c for c in cites if c["url"] not in known)
    return data


def ask(question: str, context: dict | None = None, settings: Settings | None = None) -> dict:
    """Free-form strategy question with optional league context (values, roster, budget)."""
    s = settings or Settings.load()
    content = question
    if context:
        content += "\n\nLeague context (JSON):\n" + json.dumps(context)[:60000]
    resp = _client(s).messages.create(
        model=s.model, max_tokens=4000, system=SYSTEM, tools=[WEB_SEARCH_TOOL],
        messages=[{"role": "user", "content": content}],
    )
    return {"answer": _text(resp), "sources": _citations(resp)}
