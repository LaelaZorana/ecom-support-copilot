"""Refund-decision logic respects the store policy."""

from __future__ import annotations

from datetime import date

import pytest

from supportcopilot.orders import OrdersService
from supportcopilot.refunds import (
    RETURN_SHIPPING_FEE,
    RETURN_WINDOW_DAYS,
    decide_refund,
)


@pytest.fixture(scope="module")
def svc():
    return OrdersService()


def test_unused_within_window_is_approved_with_fee(svc):
    order = svc.get("NW-1001")  # tent, delivered 2026-05-15, total 289
    d = decide_refund(order, message="unused with tags, want a refund", today=date(2026, 5, 20))
    assert d.outcome == "approve"
    assert d.fee_applied == RETURN_SHIPPING_FEE
    assert d.refund_amount == pytest.approx(289.0 - RETURN_SHIPPING_FEE, abs=1e-6)
    assert d.policy_citation == "Returns policy"


def test_our_error_waives_return_fee(svc):
    order = svc.get("NW-1001")
    d = decide_refund(order, message="wrong item sent", today=date(2026, 5, 20), our_error=True)
    assert d.outcome == "approve"
    assert d.fee_applied == 0.0
    assert d.refund_amount == pytest.approx(289.0, abs=1e-6)


def test_final_sale_is_denied(svc):
    order = svc.get("NW-1005")  # water filters, final_sale = True
    d = decide_refund(order, message="please refund me", today=date(2026, 5, 25))
    assert d.outcome == "deny"
    assert d.refund_amount == 0.0
    assert d.policy_citation == "Final Sale policy"


def test_worn_item_is_denied(svc):
    order = svc.get("NW-1004")  # boots, delivered 2026-04-04
    d = decide_refund(
        order, message="I wore them on three hikes and changed my mind", today=date(2026, 4, 10)
    )
    assert d.outcome == "deny"
    assert "worn_or_used" in d.notes


def test_defect_claim_is_escalated(svc):
    order = svc.get("NW-1004")
    d = decide_refund(order, message="the sole split on first wear, it's defective")
    assert d.outcome == "escalate"
    assert d.requires_human is True
    assert d.policy_citation == "Warranty policy"


def test_outside_return_window_is_denied(svc):
    order = svc.get("NW-1004")  # delivered 2026-04-04
    too_late = date(2026, 4, 4) + __import__("datetime").timedelta(days=RETURN_WINDOW_DAYS + 5)
    d = decide_refund(order, message="want to return, unused", today=too_late)
    assert d.outcome == "deny"
    assert "outside_window" in d.notes


def test_not_yet_delivered_is_still_eligible(svc):
    order = svc.get("NW-1003")  # processing, delivered_at is None
    d = decide_refund(order, message="unused, please refund", today=date(2026, 6, 3))
    assert d.outcome == "approve"
