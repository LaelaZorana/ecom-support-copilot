"""Agent intent routing, order lookup, citations, and escalation behaviour."""

from __future__ import annotations


def test_general_question_is_answered_with_citations(agent):
    resp = agent.handle("How long does standard shipping take and is it free?")
    assert resp.intent == "general"
    assert resp.auto_resolved is True
    assert resp.escalated is False
    assert resp.citations, "expected at least one citation"
    # Answer should be grounded — mention a concrete shipping fact from the policy.
    assert any(tok in resp.answer.lower() for tok in ["business day", "$75", "free", "6.95"])


def test_order_status_lookup(agent):
    resp = agent.handle("What's the status of my order?", order_id="NW-1002", email="jordan@example.com")
    assert resp.intent == "order_status"
    assert resp.auto_resolved is True
    assert resp.order is not None
    assert resp.order.order_id == "NW-1002"
    assert "shipped" in resp.answer.lower()


def test_order_status_email_mismatch_is_not_leaked(agent):
    # Wrong email must not return the order; the agent should ask/escalate instead.
    resp = agent.handle("status?", order_id="NW-1002", email="not-the-owner@example.com")
    assert resp.order is None
    assert resp.escalated is True


def test_refund_request_flows_through_decision_engine(agent):
    resp = agent.handle(
        "I'd like to return my tent, it's unused with tags.",
        order_id="NW-1001",
        email="alex@example.com",
    )
    assert resp.intent == "refund"
    assert resp.refund is not None
    assert resp.refund.outcome == "approve"
    assert resp.auto_resolved is True


def test_defect_claim_escalates(agent):
    resp = agent.handle(
        "My tent pole snapped on its first trip, I think it's defective.",
        order_id="NW-1001",
        email="alex@example.com",
    )
    assert resp.escalated is True
    assert resp.refund is not None
    assert resp.refund.outcome == "escalate"


def test_hard_escalation_on_manager_demand(agent):
    resp = agent.handle("I demand to speak to a manager right now, this is unacceptable.")
    assert resp.escalated is True
    assert resp.auto_resolved is False


def test_billing_dispute_escalates(agent):
    resp = agent.handle("I think I was double charged, please investigate my account.")
    assert resp.escalated is True


def test_offtopic_question_escalates(agent):
    resp = agent.handle("Can you help me file my taxes this year?")
    assert resp.escalated is True
    assert resp.auto_resolved is False


def test_order_id_extracted_from_message(agent):
    # No explicit order_id passed; it should be parsed out of the text.
    resp = agent.handle("what is the status of order NW-1004?")
    assert resp.intent == "order_status"
    assert resp.order is not None
    assert resp.order.order_id == "NW-1004"


def test_response_serializes_to_dict(agent):
    resp = agent.handle("Do you have an ultralight 2-person tent?")
    d = resp.to_dict()
    assert set(["intent", "answer", "confidence", "escalated", "citations"]).issubset(d)
    assert isinstance(d["citations"], list)
