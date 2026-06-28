"""Runtime configuration, resolved from environment variables with safe defaults."""

from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import date
from pathlib import Path

# Repo root and the seed-data directory. Resolved relative to this file so the app
# works the same whether launched from the repo root, a container, or pytest.
ROOT_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = Path(os.getenv("SUPPORTCOPILOT_DATA_DIR", ROOT_DIR / "data"))


@dataclass(frozen=True)
class Settings:
    """All knobs in one place. Read once at startup via :func:`get_settings`."""

    data_dir: Path = DATA_DIR

    # LLM provider selection. "auto" picks a real provider when its key is present,
    # otherwise falls back to the deterministic offline stub so everything runs with
    # zero paid keys.
    llm_provider: str = os.getenv("LLM_PROVIDER", "auto")
    anthropic_api_key: str | None = os.getenv("ANTHROPIC_API_KEY")
    openai_api_key: str | None = os.getenv("OPENAI_API_KEY")
    anthropic_model: str = os.getenv("ANTHROPIC_MODEL", "claude-3-5-haiku-latest")
    openai_model: str = os.getenv("OPENAI_MODEL", "gpt-4o-mini")

    # Retrieval / decision tuning.
    top_k: int = int(os.getenv("SUPPORTCOPILOT_TOP_K", "3"))
    # Below this retrieval/answer confidence the agent escalates to a human instead
    # of answering. Kept conservative on purpose: a wrong refund costs more than a
    # human-handled ticket.
    escalation_threshold: float = float(os.getenv("SUPPORTCOPILOT_ESCALATION_THRESHOLD", "0.12"))

    # The bundled demo orders are a fixed historical snapshot, and refund eligibility
    # is date-relative (the 30-day return window). Evaluate refunds against the
    # dataset's own timeframe rather than the wall clock so the offline demo stays
    # correct indefinitely instead of "expiring" 30 days after the snapshot was taken.
    # Override with SUPPORTCOPILOT_REFERENCE_DATE=YYYY-MM-DD (or pass an explicit
    # ``today`` to the agent) to evaluate against a real date.
    reference_date: date = date.fromisoformat(
        os.getenv("SUPPORTCOPILOT_REFERENCE_DATE", "2026-06-05")
    )


def get_settings() -> Settings:
    """Return a fresh Settings snapshot from the current environment."""
    return Settings()
