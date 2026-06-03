"""Provider selection and resilience (offline stub by default, safe fallback)."""

from __future__ import annotations

from supportcopilot.config import Settings
from supportcopilot.providers import (
    SafeProvider,
    StubProvider,
    get_provider,
)


def test_stub_answers_from_context_only():
    stub = StubProvider()
    ctx = [
        "Returns. Unused items may be returned within 30 days of delivery for a full refund.",
        "Shipping. Standard delivery takes 3 to 7 business days.",
    ]
    ans = stub.answer("return window for unused items refund", ctx)
    assert "30 days" in ans
    # The stub never invents facts outside the provided context.
    assert "warranty" not in ans.lower()


def test_stub_handles_empty_context():
    stub = StubProvider()
    ans = stub.answer("anything", [])
    assert "escalat" in ans.lower()


def test_auto_without_keys_is_stub():
    s = Settings(llm_provider="auto", anthropic_api_key=None, openai_api_key=None)
    assert get_provider(s).name == "stub"


def test_explicit_stub_choice():
    s = Settings(llm_provider="stub", anthropic_api_key="sk-whatever")
    assert get_provider(s).name == "stub"


def test_safe_provider_falls_back_on_error():
    class Boom:
        name = "boom"

        def answer(self, question, context):
            raise RuntimeError("API exploded")

    safe = SafeProvider(Boom())
    # Reports the wrapped provider's name for observability...
    assert safe.name == "boom"
    # ...but never propagates the failure; it returns a grounded fallback answer.
    out = safe.answer(
        "return window?",
        ["Returns. Items may be returned within 30 days of delivery."],
    )
    assert "30 days" in out


def test_safe_provider_falls_back_on_empty_answer():
    class Empty:
        name = "empty"

        def answer(self, question, context):
            return ""

    safe = SafeProvider(Empty())
    out = safe.answer(
        "shipping delivery business days",
        ["Shipping. Delivery takes 3 to 7 business days."],
    )
    assert "business days" in out
