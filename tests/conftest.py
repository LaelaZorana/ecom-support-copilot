"""Shared pytest fixtures. Force the offline stub so the suite is hermetic."""

from __future__ import annotations

import os

import pytest

# Ensure tests never reach a paid API even if a key/provider is set in the
# environment. We force (not setdefault) the stub so the suite is always hermetic.
os.environ["LLM_PROVIDER"] = "stub"
os.environ.pop("ANTHROPIC_API_KEY", None)
os.environ.pop("OPENAI_API_KEY", None)


@pytest.fixture(scope="session")
def agent():
    from supportcopilot.agent import SupportAgent

    return SupportAgent()


@pytest.fixture(scope="session")
def retriever():
    from supportcopilot.knowledge import load_knowledge_base
    from supportcopilot.retrieval import Retriever

    return Retriever(load_knowledge_base())


@pytest.fixture(scope="session")
def orders():
    from supportcopilot.orders import OrdersService

    return OrdersService()
