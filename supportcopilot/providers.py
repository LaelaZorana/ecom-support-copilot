"""LLM provider interface with a deterministic offline stub.

Every LLM call in the app goes through :class:`LLMProvider`. In production you set
``ANTHROPIC_API_KEY`` or ``OPENAI_API_KEY`` and a real model answers. With no key set
(CI, tests, local demo) the :class:`StubProvider` produces a grounded answer from the
retrieved context using simple extractive logic, no network, fully reproducible.

The stub is intentionally not a toy: it composes a real answer out of the retrieved
policy/catalog snippets so the end-to-end product (citations, refund decisions,
escalation) is demonstrable with zero paid keys.
"""

from __future__ import annotations

import re
from typing import Protocol, Sequence

from .config import Settings, get_settings


class LLMProvider(Protocol):
    """Minimal surface the app depends on. Easy to swap or mock."""

    name: str

    def answer(self, question: str, context: Sequence[str]) -> str:
        """Answer ``question`` grounded in ``context`` snippets."""
        ...


_SENT_SPLIT = re.compile(r"(?<=[.!?])\s+")
_WORD = re.compile(r"[a-z0-9]+")


def _tokens(text: str) -> list[str]:
    return _WORD.findall(text.lower())


class StubProvider:
    """Deterministic, offline, network-free provider.

    Strategy: rank the sentences inside the retrieved context by lexical overlap
    with the question and stitch the best ones into a concise grounded reply. This
    keeps answers faithful to the knowledge base (no hallucination) which is exactly
    what you want from a support agent.
    """

    name = "stub"

    def answer(self, question: str, context: Sequence[str]) -> str:
        q_terms = set(_tokens(question))
        if not context:
            return (
                "I couldn't find that in our policies or catalog, so I'm escalating "
                "this to a human teammate."
            )

        # Flatten context into candidate sentences. Each is scored by how many query
        # terms it covers (overlap). Trivially short fragments (e.g. a bare section
        # heading like "Shipping.") are skipped so they can't win on a single keyword
        # while carrying no actual answer. Ties prefer the more informative (longer)
        # sentence, then earlier source order, keeping the result deterministic.
        candidates: list[tuple[int, int, int, str]] = []
        for src_idx, block in enumerate(context):
            for sent in _SENT_SPLIT.split(block.strip()):
                sent = sent.strip()
                sent_tokens = _tokens(sent)
                if len(sent_tokens) < 4:
                    continue
                overlap = len(q_terms & set(sent_tokens))
                candidates.append((overlap, len(sent_tokens), -src_idx, sent))

        if not candidates:
            return context[0].strip()

        # Highest overlap first; then longer (more informative); then earlier source.
        candidates.sort(key=lambda c: (c[0], c[1], c[2]), reverse=True)
        if candidates[0][0] == 0:
            # No lexical match. Surface the most relevant retrieved block rather than
            # fabricate. The orchestrator's confidence will be low and it will likely
            # escalate.
            return context[0].strip()

        chosen: list[str] = []
        for overlap, _len, _src, sent in candidates:
            if overlap == 0:
                break
            if sent not in chosen:
                chosen.append(sent)
            if len(chosen) >= 2:
                break
        return " ".join(chosen)


class AnthropicProvider:
    """Real provider backed by the Anthropic Messages API."""

    name = "anthropic"

    def __init__(self, settings: Settings):
        # Imported lazily so the dependency is optional and the offline path never
        # needs it installed.
        import anthropic  # type: ignore

        self._client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
        self._model = settings.anthropic_model

    def answer(self, question: str, context: Sequence[str]) -> str:
        joined = "\n\n".join(f"[doc {i + 1}]\n{c}" for i, c in enumerate(context))
        system = (
            "You are an e-commerce support agent. Answer ONLY from the provided "
            "context. If the answer is not in the context, say you don't know. Be "
            "concise and cite the relevant policy heading or product name."
        )
        msg = self._client.messages.create(
            model=self._model,
            max_tokens=400,
            system=system,
            messages=[
                {
                    "role": "user",
                    "content": f"Context:\n{joined}\n\nCustomer question: {question}",
                }
            ],
        )
        return "".join(block.text for block in msg.content if block.type == "text").strip()


class OpenAIProvider:
    """Real provider backed by the OpenAI Chat Completions API."""

    name = "openai"

    def __init__(self, settings: Settings):
        from openai import OpenAI  # type: ignore

        self._client = OpenAI(api_key=settings.openai_api_key)
        self._model = settings.openai_model

    def answer(self, question: str, context: Sequence[str]) -> str:
        joined = "\n\n".join(f"[doc {i + 1}]\n{c}" for i, c in enumerate(context))
        system = (
            "You are an e-commerce support agent. Answer ONLY from the provided "
            "context. If the answer is not in the context, say you don't know. Be "
            "concise and cite the relevant policy heading or product name."
        )
        resp = self._client.chat.completions.create(
            model=self._model,
            max_tokens=400,
            messages=[
                {"role": "system", "content": system},
                {
                    "role": "user",
                    "content": f"Context:\n{joined}\n\nCustomer question: {question}",
                },
            ],
        )
        return (resp.choices[0].message.content or "").strip()


class SafeProvider:
    """Wrap a real provider so any runtime failure degrades to the offline stub.

    A bad API key, rate limit, or network blip on a live call should never 500 a
    support request, we fall back to a grounded extractive answer instead. The
    reported ``name`` is the wrapped provider's so observability stays accurate.
    """

    def __init__(self, inner: LLMProvider):
        self._inner = inner
        self._fallback = StubProvider()
        self.name = inner.name

    def answer(self, question: str, context: Sequence[str]) -> str:
        try:
            text = self._inner.answer(question, context)
            return text or self._fallback.answer(question, context)
        except Exception:
            return self._fallback.answer(question, context)


def get_provider(settings: Settings | None = None) -> LLMProvider:
    """Resolve a provider from settings.

    ``auto`` (default) uses a real provider only when its key is present, otherwise
    the offline stub. Explicit values (``anthropic``/``openai``/``stub``) are honored.
    Any failure to construct a real provider degrades gracefully to the stub so the
    app never hard-crashes on a missing optional dependency, and any failure at call
    time is caught by :class:`SafeProvider`.
    """
    settings = settings or get_settings()
    choice = settings.llm_provider.lower()

    def _try(builder) -> LLMProvider | None:
        try:
            return SafeProvider(builder(settings))
        except Exception:
            return None

    if choice == "stub":
        return StubProvider()
    if choice == "anthropic" and settings.anthropic_api_key:
        return _try(AnthropicProvider) or StubProvider()
    if choice == "openai" and settings.openai_api_key:
        return _try(OpenAIProvider) or StubProvider()
    if choice == "auto":
        if settings.anthropic_api_key:
            p = _try(AnthropicProvider)
            if p:
                return p
        if settings.openai_api_key:
            p = _try(OpenAIProvider)
            if p:
                return p
    return StubProvider()
