"""Settings loaded from environment / .env. No secrets are ever hard-coded here."""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

PLACEHOLDER_PREFIX = "your-"


class MissingKeyError(RuntimeError):
    """Raised when a feature needs a key the user hasn't supplied."""


def _load_dotenv(path: Path) -> None:
    """Minimal .env loader (no dependency). Existing env vars win."""
    if not path.exists():
        return
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


def _is_real(value: str | None) -> bool:
    return bool(value) and not value.startswith(PLACEHOLDER_PREFIX)


@dataclass
class Settings:
    league_id: str | None
    my_roster_id: int | None
    anthropic_api_key: str | None
    model: str
    api_token: str | None
    budget: int
    keeper_inflation: int
    max_keepers: int

    @classmethod
    def load(cls, env_file: str | Path = ".env") -> "Settings":
        _load_dotenv(Path(env_file))
        g = os.environ.get
        league = g("SLEEPER_LEAGUE_ID")
        roster = g("SLEEPER_MY_ROSTER_ID")
        return cls(
            league_id=league if _is_real(league) else None,
            my_roster_id=int(roster) if roster and roster.isdigit() else None,
            anthropic_api_key=g("ANTHROPIC_API_KEY") if _is_real(g("ANTHROPIC_API_KEY")) else None,
            model=g("DYNASTY_AGENT_MODEL", "claude-sonnet-5-5"),
            api_token=g("DYNASTY_AGENT_API_TOKEN") if _is_real(g("DYNASTY_AGENT_API_TOKEN")) else None,
            budget=int(g("DYNASTY_AGENT_BUDGET", "200")),
            keeper_inflation=int(g("DYNASTY_AGENT_KEEPER_INFLATION", "5")),
            max_keepers=int(g("DYNASTY_AGENT_MAX_KEEPERS", "2")),
        )

    def require_anthropic_key(self) -> str:
        if not self.anthropic_api_key:
            raise MissingKeyError(
                "No Anthropic API key configured. The research agent needs YOUR OWN key: "
                "create one at https://console.anthropic.com/ and set ANTHROPIC_API_KEY in "
                "your .env (copy .env.example). Never commit it."
            )
        return self.anthropic_api_key

    def require_api_token(self) -> str:
        if not self.api_token:
            raise MissingKeyError(
                "DYNASTY_AGENT_API_TOKEN is not set, so private routes are disabled. Set your own "
                "random token in .env to enable them."
            )
        return self.api_token
