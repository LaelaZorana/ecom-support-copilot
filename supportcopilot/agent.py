"""The support agent: intent routing, RAG answers, order lookup, refunds, escalation.

This is the brain. Given a customer message (and optional order id / email) it:

1. classifies intent (order status, refund/return, or general question);
2. gathers grounded context (mock orders API and/or KB retrieval);
3. produces an answer via the LLM provider, with citations;
4. decides whether to auto-resolve or escalate to a human, with a confidence score.

Determinism note: intent routing, refund logic, and the escalation decision are
rule-based so behaviour is testable and reproducible. The provider only phrases the
final natural-language answer, and the offline stub keeps even that deterministic.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date
from typing import Sequence

from .config import Settings, get_settings
from .knowledge import Document, load_knowledge_base
from .orders import Order, OrdersService
from .providers import LLMProvider, get_provider
from .refunds import RefundDecision, decide_refund
from .retrieval import RetrievalResult, Retriever

# Intent keyword cues. Order/refund intents are detected before falling back to a
# general knowledge-base answer.
_ORDER_TERMS = re.compile(
    r"\b(where.s my order|order status|status of (my |the )?order|status of my|"
    r"tracking|track my|shipped|deliver(ed|y)?|cancel(led|lation)?|"
    r"did my .* (ship|cancel))\b",
    re.IGNORECASE,
)
_REFUND_TERMS = re.compile(
    r"\b(refund|return|money back|send .* back|exchange|warranty|defect|broke|broken|"
    r"snapped|replacement)\b",
    re.IGNORECASE,
)
_ORDER_ID = re.compile(r"\bNW-\d{3,}\b", re.IGNORECASE)
_EMAIL = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")

# Phrases that should always reach a human regardless of confidence (frustration,
# legal/financial risk, manager requests).
_HARD_ESCALATION = re.compile(
    r"\b(speak to a manager|talk to a human|lawyer|legal|charged twice|double charge|"
    r"double charged|fraud|chargeback|compensation|unacceptable|ruined|complaint)\b",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class Citation:
    source_id: str
    title: str
    kind: str  # "policy" | "product" | "order"
    snippet: str


@dataclass(frozen=True)
class AgentResponse:
    intent: str
    answer: str
    citations: list[Citation] = field(default_factory=list)
    confidence: float = 0.0
    escalated: bool = False
    auto_resolved: bool = False
    refund: RefundDecision | None = None
    order: Order | None = None

    def to_dict(self) -> dict:
        return {
            "intent": self.intent,
            "answer": self.answer,
            "confidence": round(self.confidence, 3),
            "escalated": self.escalated,
            "auto_resolved": self.auto_resolved,
            "citations": [c.__dict__ for c in self.citations],
            "refund": self.refund.__dict__ if self.refund else None,
            "order": {
                "order_id": self.order.order_id,
                "status": self.order.human_status(),
            }
            if self.order
            else None,
        }


def classify_intent(message: str) -> str:
    """Return one of ``order_status`` | ``refund`` | ``general``."""
    if _REFUND_TERMS.search(message):
        return "refund"
    if _ORDER_TERMS.search(message):
        return "order_status"
    return "general"


def _snippet(text: str, limit: int = 220) -> str:
    text = " ".join(text.split())
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"


class SupportAgent:
    """Stateless support agent. Construct once, call :meth:`handle` per ticket."""

    def __init__(
        self,
        settings: Settings | None = None,
        documents: Sequence[Document] | None = None,
        orders: OrdersService | None = None,
        provider: LLMProvider | None = None,
    ):
        self.settings = settings or get_settings()
        docs = list(documents) if documents is not None else load_knowledge_base(self.settings.data_dir)
        self.retriever = Retriever(docs)
        self.orders = orders or OrdersService(self.settings.data_dir / "orders.json")
        self.provider = provider or get_provider(self.settings)

    # -- public API ---------------------------------------------------------------

    def handle(
        self,
        message: str,
        order_id: str | None = None,
        email: str | None = None,
        today: date | None = None,
    ) -> AgentResponse:
        """Process one customer message and return a structured response."""
        order_id = order_id or self._extract_order_id(message)
        email = email or self._extract_email(message)
        intent = classify_intent(message)

        # Hard escalations short-circuit everything: frustration / legal / billing.
        if _HARD_ESCALATION.search(message):
            return AgentResponse(
                intent=intent,
                answer=(
                    "I want to make sure this is handled properly, so I'm connecting "
                    "you with a human support specialist who can help right away."
                ),
                confidence=0.0,
                escalated=True,
                auto_resolved=False,
            )

        if intent == "order_status":
            return self._handle_order_status(message, order_id, email)
        if intent == "refund":
            return self._handle_refund(message, order_id, email, today)
        return self._handle_general(message)

    # -- intent handlers ----------------------------------------------------------

    def _handle_order_status(
        self, message: str, order_id: str | None, email: str | None
    ) -> AgentResponse:
        if not order_id:
            return self._escalate_for_info(
                "order_status",
                "I can look that up right away, could you share your order number "
                "(it looks like NW-1234)?",
            )
        order = self.orders.get(order_id, email)
        if order is None:
            return self._escalate_for_info(
                "order_status",
                f"I couldn't find an order matching {order_id}. A teammate will help "
                "you verify the details.",
            )
        answer = f"Order {order.order_id} is currently {order.human_status()}."
        if order.status == "processing":
            answer += " It hasn't shipped yet; you'll get tracking by email once it does."
        elif order.status == "cancelled":
            answer += " No charge is collected for cancelled orders."
        citation = Citation(
            source_id=order.order_id,
            title=f"Order {order.order_id}",
            kind="order",
            snippet=_snippet(
                f"Status {order.status}; "
                + ", ".join(f"{i['qty']}x {i['name']}" for i in order.items)
            ),
        )
        return AgentResponse(
            intent="order_status",
            answer=answer,
            citations=[citation],
            confidence=0.95,
            escalated=False,
            auto_resolved=True,
            order=order,
        )

    def _handle_refund(
        self,
        message: str,
        order_id: str | None,
        email: str | None,
        today: date | None,
    ) -> AgentResponse:
        if not order_id:
            # Refund questions with no order id are usually policy questions
            # ("what's your return policy?"), answer from the KB instead of stalling.
            return self._handle_general(message, force_intent="refund")
        order = self.orders.get(order_id, email)
        if order is None:
            return self._escalate_for_info(
                "refund",
                f"I couldn't find order {order_id} to process a return. A teammate "
                "will verify your details and help.",
            )

        decision = decide_refund(order, message=message, today=today)
        policy_ctx = self.retriever.search(decision.policy_citation, top_k=1)
        citations = [
            Citation(
                source_id=order.order_id,
                title=f"Order {order.order_id}",
                kind="order",
                snippet=_snippet(f"Total ${order.total:.2f}; status {order.status}"),
            )
        ]
        for r in policy_ctx:
            citations.append(
                Citation(
                    source_id=r.document.doc_id,
                    title=r.document.title,
                    kind=r.document.kind,
                    snippet=_snippet(r.document.text),
                )
            )

        if decision.outcome == "approve":
            answer = (
                f"Good news, your return for order {order.order_id} is approved. "
                f"{decision.reason} You'll be refunded ${decision.refund_amount:.2f} "
                "to your original payment method within 5 business days once we receive "
                "the item."
            )
        elif decision.outcome == "deny":
            answer = f"I looked into your return for order {order.order_id}. {decision.reason}"
        else:  # escalate
            answer = (
                f"Thanks for flagging this on order {order.order_id}. {decision.reason} "
                "I've routed this to a specialist who will follow up shortly."
            )

        escalated = decision.outcome == "escalate"
        return AgentResponse(
            intent="refund",
            answer=answer,
            citations=citations,
            confidence=0.4 if escalated else 0.9,
            escalated=escalated,
            auto_resolved=not escalated,
            refund=decision,
            order=order,
        )

    def _handle_general(self, message: str, force_intent: str | None = None) -> AgentResponse:
        results = self.retriever.search(message, top_k=self.settings.top_k)
        confidence = self._confidence(results)
        intent = force_intent or "general"

        if confidence < self.settings.escalation_threshold:
            return AgentResponse(
                intent=intent,
                answer=(
                    "I'm not fully confident I can answer that accurately, so I'm "
                    "passing you to a human teammate who can help."
                ),
                citations=[],
                confidence=confidence,
                escalated=True,
                auto_resolved=False,
            )

        context = [r.document.text for r in results]
        answer = self.provider.answer(message, context)
        citations = [
            Citation(
                source_id=r.document.doc_id,
                title=r.document.title,
                kind=r.document.kind,
                snippet=_snippet(r.document.text),
            )
            for r in results
        ]
        return AgentResponse(
            intent=intent,
            answer=answer,
            citations=citations,
            confidence=confidence,
            escalated=False,
            auto_resolved=True,
        )

    # -- helpers ------------------------------------------------------------------

    def _confidence(self, results: Sequence[RetrievalResult]) -> float:
        """Confidence = top retrieval score, lightly boosted by margin over #2.

        A clear winner (high top score, big gap to the runner-up) is more trustworthy
        than a flat distribution of weak matches.
        """
        if not results:
            return 0.0
        top = results[0].score
        margin = top - (results[1].score if len(results) > 1 else 0.0)
        return float(min(1.0, top + 0.25 * margin))

    def _escalate_for_info(self, intent: str, answer: str) -> AgentResponse:
        return AgentResponse(
            intent=intent,
            answer=answer,
            confidence=0.0,
            escalated=True,
            auto_resolved=False,
        )

    @staticmethod
    def _extract_order_id(message: str) -> str | None:
        m = _ORDER_ID.search(message)
        return m.group(0).upper() if m else None

    @staticmethod
    def _extract_email(message: str) -> str | None:
        m = _EMAIL.search(message)
        return m.group(0) if m else None
